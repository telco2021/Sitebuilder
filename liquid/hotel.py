"""Room inventory. A stay occupies the nights from check-in up to, but not including, check-out."""

from __future__ import annotations

import secrets
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from liquid.constants import MAX_GUESTS, MAX_ROOMS, MAX_STAY_NIGHTS
from liquid.models import Reservation, RoomType, utcnow
from liquid.textutil import FormError, one_line


def parse_date(value: object, label: str) -> date:
    text = one_line(value, 10)
    try:
        year, month, day = (int(part) for part in text.split("-"))
        return date(year, month, day)
    except (TypeError, ValueError):
        raise FormError(f"Enter a valid {label}.") from None


def parse_stay(form) -> dict:
    check_in = parse_date(form.get("check_in"), "arrival date")
    check_out = parse_date(form.get("check_out"), "departure date")
    today = date.today()
    if check_in < today:
        raise FormError("Arrival cannot be in the past.")
    if check_in > today + timedelta(days=365):
        raise FormError("Arrival must be within the next year.")
    nights = (check_out - check_in).days
    if nights < 1:
        raise FormError("Departure must be after arrival.")
    if nights > MAX_STAY_NIGHTS:
        raise FormError(f"Stays are limited to {MAX_STAY_NIGHTS} nights.")
    try:
        rooms = int(form.get("rooms", "1"))
        adults = int(form.get("adults", "1"))
        children = int(form.get("children", "0"))
    except (TypeError, ValueError):
        raise FormError("Guest counts must be numbers.") from None
    if not 1 <= rooms <= MAX_ROOMS:
        raise FormError(f"Choose between 1 and {MAX_ROOMS} rooms.")
    if not 1 <= adults <= MAX_GUESTS or not 0 <= children <= MAX_GUESTS:
        raise FormError("Check the number of adults and children.")
    if adults + children > MAX_GUESTS:
        raise FormError(f"A search can include up to {MAX_GUESTS} guests.")
    return {
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "rooms": rooms,
        "adults": adults,
        "children": children,
    }


def stay_dates(stay: dict) -> tuple[date, date, int]:
    check_in = date.fromisoformat(stay["check_in"])
    check_out = date.fromisoformat(stay["check_out"])
    return check_in, check_out, (check_out - check_in).days


def rooms_booked(db: Session, room_id: int, check_in: date, check_out: date) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(Reservation.rooms), 0)).where(
            Reservation.room_type_id == room_id,
            Reservation.status == "confirmed",
            Reservation.check_in < check_out,
            Reservation.check_out > check_in,
        )
    )
    return int(total or 0)


def rooms_available(db: Session, room: RoomType, check_in: date, check_out: date) -> int:
    return max(0, room.inventory - rooms_booked(db, room.id, check_in, check_out))


def fits_capacity(room: RoomType, rooms: int, adults: int, children: int) -> bool:
    return adults + children <= room.capacity * rooms


def quote(room: RoomType, nights: int, rooms: int) -> int:
    return room.nightly_rate_cents * nights * rooms


def confirmation_code(slug: str) -> str:
    letters = "".join(character for character in slug.upper() if character.isalpha())[:4] or "LS"
    return f"{letters}-{secrets.token_hex(4).upper()}"


def cancel_reservation(db: Session, reservation: Reservation, actor: str) -> None:
    from liquid.models import CancellationLog

    if reservation.status != "confirmed":
        raise FormError("That reservation is already cancelled.")
    reservation.status = "cancelled"
    reservation.cancelled_by = actor[:120]
    reservation.cancelled_at = utcnow()
    db.add(
        CancellationLog(
            reservation_id=reservation.id,
            admin_name=actor[:120],
            check_in=reservation.check_in,
            check_out=reservation.check_out,
        )
    )
