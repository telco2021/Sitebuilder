"""Staff session, roles, and form fields."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.requests import Request

from liquid.models import Site, User
from liquid.security import assert_csrf
from liquid.textutil import one_line, plain


class LoginRequired(Exception):
    """Raised when an admin route is opened without a staff session."""


def require_user(request: Request, db: Session) -> User:
    user_id = request.state.session.get("uid")
    user = db.get(User, user_id) if isinstance(user_id, int) else None
    if user is None or not user.is_active:
        request.state.session.pop("uid", None)
        raise LoginRequired()
    request.state.user = user
    return user


def require_role(user: User, *roles: str) -> None:
    if user.role != "owner" and user.role not in roles:
        raise HTTPException(status_code=403, detail="You do not have access to that.")


def site_or_404(db: Session, site_id: int) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="That site does not exist.")
    return site


async def posted(request: Request):
    form = await request.form()
    assert_csrf(request, form.get("csrf"))
    return form


def field(form, name: str, limit: int = 200) -> str:
    value = form.get(name)
    return one_line(value, limit) if isinstance(value, str) else ""


def block(form, name: str, limit: int = 20000) -> str:
    value = form.get(name)
    return plain(value, limit) if isinstance(value, str) else ""


def integer(form, name: str, default: int, low: int, high: int, label: str) -> int:
    raw = form.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{label} must be a whole number.") from None
    if not low <= value <= high:
        raise HTTPException(status_code=400, detail=f"{label} is out of range.")
    return value
