"""Staff action log. Never pass passwords, card numbers, or reset tokens."""

from __future__ import annotations

from sqlalchemy.orm import Session
from starlette.requests import Request

from liquid.config import Settings
from liquid.models import AuditEvent
from liquid.security import client_ip
from liquid.textutil import one_line


def audit(db: Session, request: Request, settings: Settings, actor: str, action: str, target: str = "", detail: str = "") -> None:
    db.add(
        AuditEvent(
            actor_email=one_line(actor, 255),
            action=one_line(action, 80),
            target=one_line(target, 180),
            ip=client_ip(request, settings),
            detail=one_line(detail, 500),
        )
    )
