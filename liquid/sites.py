"""Site lifecycle helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from liquid.constants import FEATURE_KEYS
from liquid.models import (
    CancellationLog,
    Category,
    Customer,
    FormDef,
    FormSubmission,
    HelpArticle,
    HotelProperty,
    Media,
    Order,
    OrderLine,
    Page,
    Product,
    Reservation,
    RoomType,
    Site,
)
from liquid.textutil import hex_color, one_line, slugify


def clean_features(raw: dict | None) -> dict[str, bool]:
    source = raw or {}
    return {key: bool(source.get(key)) for key in FEATURE_KEYS}


def apply_theme(site: Site, form) -> None:
    site.color_ink = hex_color(form.get("color_ink"), site.color_ink)
    site.color_paper = hex_color(form.get("color_paper"), site.color_paper)
    site.color_accent = hex_color(form.get("color_accent"), site.color_accent)
    site.color_header = hex_color(form.get("color_header"), site.color_header)
    site.color_text = hex_color(form.get("color_text"), site.color_text)


def apply_profile(site: Site, form) -> None:
    site.name = one_line(form.get("name"), 80) or site.name
    site.company_name = one_line(form.get("company_name"), 80)
    site.domain = one_line(form.get("domain"), 255)
    site.language = one_line(form.get("language"), 12) or "en"
    site.tagline = one_line(form.get("tagline"), 180)
    currency = one_line(form.get("currency"), 3).upper()
    if len(currency) == 3 and currency.isalpha():
        site.currency = currency
    try:
        shipping = int(form.get("shipping_cents", site.shipping_cents))
    except (TypeError, ValueError):
        shipping = site.shipping_cents
    site.shipping_cents = min(max(shipping, 0), 1_000_000)


def unique_slug(db: Session, name: str, current_id: int | None = None) -> str:
    base = slugify(name, "site")
    if base in {"admin", "api", "static", "media", "health", "s"}:
        base = f"{base}-site"
    slug = base
    number = 2
    while True:
        existing = db.scalar(select(Site).where(Site.slug == slug))
        if existing is None or existing.id == current_id:
            return slug
        slug = f"{base[:50]}-{number}"
        number += 1


def delete_site(db: Session, site: Site, upload_root: Path) -> None:
    reservation_ids = select(Reservation.id).where(Reservation.site_id == site.id)
    order_ids = select(Order.id).where(Order.site_id == site.id)
    form_ids = select(FormDef.id).where(FormDef.site_id == site.id)
    db.execute(delete(CancellationLog).where(CancellationLog.reservation_id.in_(reservation_ids)))
    db.execute(delete(Reservation).where(Reservation.site_id == site.id))
    db.execute(delete(OrderLine).where(OrderLine.order_id.in_(order_ids)))
    db.execute(delete(Order).where(Order.site_id == site.id))
    db.execute(delete(FormSubmission).where(FormSubmission.form_id.in_(form_ids)))
    for model in (FormDef, HelpArticle, Media, Product, Category, RoomType, HotelProperty, Customer):
        db.execute(delete(model).where(model.site_id == site.id))
    db.execute(update(Page).where(Page.site_id == site.id).values(parent_id=None))
    db.execute(delete(Page).where(Page.site_id == site.id))
    folder = (upload_root / str(site.id)).resolve()
    if folder.is_dir() and folder.is_relative_to(upload_root.resolve()):
        for child in folder.iterdir():
            if child.is_file():
                child.unlink()
        folder.rmdir()
    db.delete(site)
