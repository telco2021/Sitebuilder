"""Local mail queue. A production host can drain this table into a real SMTP service."""

from __future__ import annotations

from sqlalchemy.orm import Session

from liquid.models import MailOutbox
from liquid.textutil import one_line


def queue_mail(db: Session, recipient: str, subject: str, body: str) -> None:
    db.add(
        MailOutbox(
            recipient=one_line(recipient, 255),
            subject=one_line(subject, 180),
            body=body[:20000],
        )
    )


def reservation_messages(property_name: str, guest_email: str, staff_email: str, summary: str) -> list[tuple[str, str, str]]:
    guest = (
        guest_email,
        f"Your reservation at {property_name}",
        summary,
    )
    messages = [guest]
    if staff_email:
        messages.append((staff_email, f"New reservation at {property_name}", summary))
    return messages
