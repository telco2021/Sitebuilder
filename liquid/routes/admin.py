"""Sitebuilder, the staff interface that assembles and generates sites."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse

from liquid.access import LoginRequired, block, field, integer, posted, require_role, require_user, site_or_404
from liquid.audit import audit
from liquid.constants import COUNTRIES, FEATURES, RESERVED_PAGE_SLUGS
from liquid.db import get_db
from liquid.files import media_path, store_upload
from liquid.generator import generate_site
from liquid.guide import article, grouped_guides, related_guides
from liquid.hotel import cancel_reservation
from liquid.mailer import queue_mail
from liquid.models import (
    AuditEvent,
    CancellationLog,
    Category,
    FormDef,
    FormSubmission,
    HelpArticle,
    HotelProperty,
    MailOutbox,
    Media,
    Page,
    PasswordReset,
    Product,
    Reservation,
    RoomType,
    Site,
    User,
    utcnow,
)
from liquid.render import flash, redirect, render
from liquid.security import (
    account_locked,
    client_ip,
    dummy_for,
    hash_password,
    hash_token,
    new_token,
    rate_limit,
    register_failure,
    rotate_session,
    validate_password,
    verify_password,
)
from liquid.sites import apply_profile, apply_theme, clean_features, delete_site, unique_slug
from liquid.textutil import FormError, parse_email, redact_secrets, sanitize_html, slugify

router = APIRouter()
_USERNAME = re.compile(r"^[A-Za-z0-9_.]{3,32}$")
_FIELD = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_ROLES = {"owner", "publisher", "editor", "hotel"}


def _sections(site: Site, user: User) -> list[tuple[str, str]]:
    features = site.features or {}
    catalog = [
        ("Pages", f"/admin/sites/{site.id}/pages", "cms", {"publisher", "editor"}),
        ("Files", f"/admin/sites/{site.id}/files", "files", {"publisher", "editor"}),
        ("Hotel", f"/admin/sites/{site.id}/hotel", "hotel", {"publisher", "hotel"}),
        ("Catalog", f"/admin/sites/{site.id}/catalog", "catalog", {"publisher"}),
        ("Forms", f"/admin/sites/{site.id}/forms", "forms", {"publisher", "editor"}),
        ("Help", f"/admin/sites/{site.id}/help", "help", {"publisher", "editor"}),
        ("News", f"/admin/sites/{site.id}/news", "news", {"publisher", "editor"}),
        ("Banners", f"/admin/sites/{site.id}/banners", "banners", {"publisher", "editor"}),
        ("Calendar", f"/admin/sites/{site.id}/calendar", "calendar", {"publisher", "editor"}),
        ("Services", f"/admin/sites/{site.id}/services", "services", {"publisher", "editor"}),
        ("Gallery", f"/admin/sites/{site.id}/gallery", "gallery", {"publisher", "editor"}),
        ("Courses", f"/admin/sites/{site.id}/learn", "lms", {"publisher", "editor"}),
        ("Coaches", f"/admin/sites/{site.id}/coaches", "rv", {"publisher", "editor"}),
        ("Coupons", f"/admin/sites/{site.id}/coupons", "coupons", {"publisher", "editor"}),
        ("Messages", f"/admin/sites/{site.id}/messages", "sms", {"publisher"}),
        ("Settings", f"/admin/sites/{site.id}/settings", None, {"publisher"}),
        ("Generate", f"/admin/sites/{site.id}/generate", None, {"publisher"}),
    ]
    visible = []
    for label, path, feature, roles in catalog:
        if feature and not features.get(feature):
            continue
        if user.role != "owner" and user.role not in roles:
            continue
        visible.append((label, path))
    return visible


def _guard(request: Request, db: Session, *roles: str) -> User:
    user = require_user(request, db)
    if roles:
        require_role(user, *roles)
    return user


@router.get("/admin/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    if request.state.session.get("uid"):
        return redirect("/admin")
    return render(request, "admin/login.html")


@router.post("/admin/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    settings = request.app.state.settings
    if not rate_limit(f"login:{client_ip(request, settings)}", 20, 600):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait and try again.")
    form = await posted(request)
    email = field(form, "email", 255).lower()
    password = form.get("password") if isinstance(form.get("password"), str) else ""
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(password, dummy_for(settings.env), settings.env)
        flash(request, "error", "Invalid email or password.")
        return redirect("/admin/login")
    if not user.is_active or account_locked(user) or not verify_password(password, user.password_hash, settings.env):
        if user.is_active and not account_locked(user):
            register_failure(user, settings)
            db.commit()
        flash(request, "error", "Invalid email or password.")
        return redirect("/admin/login")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit(db, request, settings, user.email, "staff.login", user.email, "")
    db.commit()
    rotate_session(request, uid=user.id)
    return redirect("/admin")


@router.post("/admin/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    await posted(request)
    rotate_session(request)
    flash(request, "ok", "Signed out.")
    return redirect("/admin/login")


@router.get("/admin/forgot")
def forgot_form(request: Request):
    return render(request, "admin/forgot.html")


@router.post("/admin/forgot")
async def forgot_submit(request: Request, db: Session = Depends(get_db)):
    settings = request.app.state.settings
    if not rate_limit(f"forgot:{client_ip(request, settings)}", 5, 3600):
        raise HTTPException(status_code=429, detail="Too many reset requests. Wait and try again.")
    form = await posted(request)
    try:
        email = parse_email(field(form, "email", 255))
    except FormError:
        email = ""
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True))) if email else None
    if user is not None:
        db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=utcnow()))
        token = new_token()
        from datetime import timedelta

        db.add(PasswordReset(user_id=user.id, token_hash=hash_token(token), expires_at=utcnow() + timedelta(minutes=30)))
        queue_mail(
            db,
            user.email,
            "Reset your Sitebuilder password",
            f"Open /admin/reset/{token} within 30 minutes. If you did not ask for this, ignore it.",
        )
        audit(db, request, settings, user.email, "staff.reset_request", user.email, "")
        db.commit()
    flash(request, "ok", "If that account exists, a reset link was placed in the operator mail outbox.")
    return redirect("/admin/login")


@router.get("/admin/reset/{token}")
def reset_form(token: str, request: Request, db: Session = Depends(get_db)):
    _reset_row(db, token)
    return render(request, "admin/reset.html", token=token)


@router.post("/admin/reset/{token}")
async def reset_submit(token: str, request: Request, db: Session = Depends(get_db)):
    form = await posted(request)
    row, user = _reset_row(db, token)
    password = form.get("password") if isinstance(form.get("password"), str) else ""
    confirm = form.get("confirmation") if isinstance(form.get("confirmation"), str) else ""
    try:
        validate_password(password)
        if password != confirm:
            raise FormError("The passwords do not match.")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/reset/{token}")
    user.password_hash = hash_password(password, request.app.state.settings.env)
    user.failed_logins = 0
    user.locked_until = None
    row.used_at = utcnow()
    audit(db, request, request.app.state.settings, user.email, "staff.reset", user.email, "")
    db.commit()
    rotate_session(request)
    flash(request, "ok", "Password updated. Sign in with it.")
    return redirect("/admin/login")


@router.get("/admin/guide")
def guide_index(request: Request, db: Session = Depends(get_db)):
    _guard(request, db)
    return render(request, "admin/guide_index.html", groups=grouped_guides())


@router.get("/admin/guide/{slug}")
def guide_page(slug: str, request: Request, db: Session = Depends(get_db)):
    _guard(request, db)
    guide = article(slug)
    if guide is None:
        raise HTTPException(status_code=404, detail="No help article for that feature.")
    return render(request, "admin/guide.html", article=guide, related=related_guides(guide))


@router.get("/admin")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db)
    sites = db.scalars(select(Site).order_by(Site.name)).all()
    cards = [(site, _sections(site, user)) for site in sites]
    return render(request, "admin/dashboard.html", cards=cards)


@router.get("/admin/sites/new")
def new_site_form(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    return render(request, "admin/site_form.html", features=FEATURES, user=user)


@router.post("/admin/sites/new")
async def new_site(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    form = await posted(request)
    name = field(form, "name", 80)
    if not name:
        flash(request, "error", "A site needs a name.")
        return redirect("/admin/sites/new")
    site = Site(name=name, slug=unique_slug(db, name), features=_feature_flags(form) if user.role == "owner" else clean_features({"cms": True, "menus": True, "search": True}))
    apply_profile(site, form)
    site.name = name
    db.add(site)
    audit(db, request, request.app.state.settings, user.email, "site.create", site.slug, "")
    db.commit()
    flash(request, "ok", "Site created.")
    return redirect(f"/admin/sites/{site.id}/settings")


@router.get("/admin/sites/{site_id:int}/settings")
def settings_form(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = site_or_404(db, site_id)
    return render(request, "admin/settings.html", site=site, sections=_sections(site, user), features=FEATURES)


@router.post("/admin/sites/{site_id:int}/settings")
async def settings_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = site_or_404(db, site_id)
    form = await posted(request)
    apply_profile(site, form)
    apply_theme(site, form)
    if user.role == "owner":
        site.features = _feature_flags(form)
    site.updated_at = utcnow()
    audit(db, request, request.app.state.settings, user.email, "site.update", site.slug, "")
    db.commit()
    flash(request, "ok", "Settings saved.")
    return redirect(f"/admin/sites/{site.id}/settings")


@router.post("/admin/sites/{site_id:int}/delete")
async def site_delete(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db)
    require_role(user, "owner")
    site = site_or_404(db, site_id)
    form = await posted(request)
    if form.get("confirm") != "yes":
        flash(request, "error", "Confirm the deletion.")
        return redirect(f"/admin/sites/{site.id}/settings")
    slug = site.slug
    delete_site(db, site, Path(request.app.state.settings.upload_dir))
    audit(db, request, request.app.state.settings, user.email, "site.delete", slug, "")
    db.commit()
    flash(request, "ok", "Site deleted.")
    return redirect("/admin")


@router.get("/admin/sites/{site_id:int}/pages")
def pages(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "cms")
    rows = db.scalars(select(Page).where(Page.site_id == site.id).order_by(Page.nav_order, Page.id)).all()
    return render(request, "admin/pages.html", site=site, sections=_sections(site, user), pages=rows)


@router.get("/admin/sites/{site_id:int}/pages/new")
def page_new(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "cms")
    parents = db.scalars(select(Page).where(Page.site_id == site.id).order_by(Page.nav_order)).all()
    return render(request, "admin/page_form.html", site=site, sections=_sections(site, user), page=None, parents=parents)


@router.get("/admin/sites/{site_id:int}/pages/{page_id:int}")
def page_edit(site_id: int, page_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "cms")
    page = _page(db, site, page_id)
    parents = db.scalars(select(Page).where(Page.site_id == site.id, Page.id != page.id).order_by(Page.nav_order)).all()
    return render(request, "admin/page_form.html", site=site, sections=_sections(site, user), page=page, parents=parents)


@router.post("/admin/sites/{site_id:int}/pages")
@router.post("/admin/sites/{site_id:int}/pages/{page_id:int}")
async def page_save(site_id: int, request: Request, db: Session = Depends(get_db), page_id: int | None = None):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "cms")
    form = await posted(request)
    action = field(form, "action", 20) or "save"
    page = _page(db, site, page_id) if page_id else None
    if action in {"publish", "revert"} and user.role == "editor":
        raise HTTPException(status_code=403, detail="Editors can save drafts. A publisher has to publish them.")
    if action == "delete":
        if page is None:
            raise HTTPException(status_code=404, detail="That page does not exist.")
        if page.is_published and user.role == "editor":
            raise HTTPException(status_code=403, detail="Editors cannot delete a published page.")
        db.execute(update(Page).where(Page.parent_id == page.id).values(parent_id=None))
        db.delete(page)
        audit(db, request, request.app.state.settings, user.email, "page.delete", f"{site.slug}/{page.slug}", "")
        db.commit()
        flash(request, "ok", "Page deleted.")
        return redirect(f"/admin/sites/{site.id}/pages")
    if action == "revert":
        if page is None or not page.is_published:
            flash(request, "error", "There is no live version to restore.")
            return redirect(f"/admin/sites/{site.id}/pages/{page.id}" if page else f"/admin/sites/{site.id}/pages")
        page.draft_title = page.live_title
        page.draft_body = page.live_body
        page.draft_keywords = page.live_keywords
        page.draft_description = page.live_description
        page.updated_by_id = user.id
        audit(db, request, request.app.state.settings, user.email, "page.revert", f"{site.slug}/{page.slug}", "")
        db.commit()
        flash(request, "ok", "Draft restored from the live page.")
        return redirect(f"/admin/sites/{site.id}/pages/{page.id}")
    try:
        title = field(form, "title", 160)
        if not title:
            raise FormError("A page needs a title.")
        slug = slugify(field(form, "slug", 60) or title)
        if slug in RESERVED_PAGE_SLUGS:
            raise FormError("That address is reserved.")
        taken = db.scalar(select(Page).where(Page.site_id == site.id, Page.slug == slug))
        if taken is not None and (page is None or taken.id != page.id):
            raise FormError("Another page already uses that address.")
        parent_id = _optional_parent(db, site, form.get("parent_id"), page.id if page else None)
    except FormError as exc:
        flash(request, "error", str(exc))
        target = f"/admin/sites/{site.id}/pages/{page.id}" if page else f"/admin/sites/{site.id}/pages/new"
        return redirect(target)
    if page is None:
        page = Page(site_id=site.id, slug=slug)
        db.add(page)
    page.slug = slug
    page.parent_id = parent_id
    page.nav_order = integer(form, "nav_order", 0, 0, 999, "Menu order")
    page.show_in_nav = form.get("show_in_nav") == "yes"
    page.draft_title = title
    page.draft_body = sanitize_html(block(form, "body", 100000))
    page.draft_keywords = field(form, "keywords", 300)
    page.draft_description = field(form, "description", 300)
    page.updated_by_id = user.id
    if action == "publish":
        _publish(page)
        audit(db, request, request.app.state.settings, user.email, "page.publish", f"{site.slug}/{page.slug}", "")
        message = "Page published."
    else:
        audit(db, request, request.app.state.settings, user.email, "page.save", f"{site.slug}/{page.slug}", "")
        message = "Draft saved."
    db.commit()
    flash(request, "ok", message)
    return redirect(f"/admin/sites/{site.id}/pages/{page.id}")


@router.get("/admin/sites/{site_id:int}/files")
def files(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "files")
    rows = db.scalars(select(Media).where(Media.site_id == site.id).order_by(Media.created_at.desc())).all()
    return render(request, "admin/files.html", site=site, sections=_sections(site, user), media=rows)


@router.post("/admin/sites/{site_id:int}/files")
async def files_upload(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "files")
    form = await posted(request)
    upload = form.get("upload")
    if upload is None or not hasattr(upload, "read"):
        flash(request, "error", "Choose a file to upload.")
        return redirect(f"/admin/sites/{site.id}/files")
    payload = await upload.read()
    try:
        stored, content_type, original = store_upload(
            Path(request.app.state.settings.upload_dir),
            site.id,
            getattr(upload, "filename", ""),
            payload,
            request.app.state.settings.max_upload_bytes,
        )
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/files")
    item = Media(site_id=site.id, original_name=original or stored, stored_name=stored, content_type=content_type, size_bytes=len(payload))
    db.add(item)
    db.flush()
    audit(db, request, request.app.state.settings, user.email, "file.upload", f"{site.slug}/{item.id}", content_type)
    db.commit()
    flash(request, "ok", f"Uploaded. Use /media/{item.id} in a page.")
    return redirect(f"/admin/sites/{site.id}/files")


@router.post("/admin/sites/{site_id:int}/files/{media_id:int}/delete")
async def files_delete(site_id: int, media_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "files")
    await posted(request)
    item = db.get(Media, media_id)
    if item is None or item.site_id != site.id:
        raise HTTPException(status_code=404, detail="That file does not exist.")
    root = Path(request.app.state.settings.upload_dir)
    try:
        media_path(root, site.id, item.stored_name).unlink()
    except FileNotFoundError:
        pass
    db.delete(item)
    audit(db, request, request.app.state.settings, user.email, "file.delete", f"{site.slug}/{media_id}", "")
    db.commit()
    flash(request, "ok", "File deleted.")
    return redirect(f"/admin/sites/{site.id}/files")


@router.get("/admin/sites/{site_id:int}/hotel")
def hotel_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "hotel")
    site = _featured(db, site_id, "hotel")
    property_row = db.scalar(select(HotelProperty).where(HotelProperty.site_id == site.id))
    rooms = db.scalars(select(RoomType).where(RoomType.site_id == site.id).order_by(RoomType.name)).all()
    reservations = db.scalars(select(Reservation).where(Reservation.site_id == site.id).order_by(Reservation.created_at.desc())).all()
    return render(
        request,
        "admin/hotel.html",
        site=site,
        sections=_sections(site, user),
        property_row=property_row,
        rooms=rooms,
        reservations=reservations,
        countries=COUNTRIES,
    )


@router.post("/admin/sites/{site_id:int}/hotel/property")
async def hotel_property(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "hotel")
    site = _featured(db, site_id, "hotel")
    form = await posted(request)
    row = db.scalar(select(HotelProperty).where(HotelProperty.site_id == site.id)) or HotelProperty(site_id=site.id)
    row.name = field(form, "name", 80) or site.name
    row.language = field(form, "language", 12) or "en"
    row.address1 = field(form, "address1", 120)
    row.address2 = field(form, "address2", 120)
    row.city = field(form, "city", 80)
    row.postcode = field(form, "postcode", 20)
    row.state = field(form, "state", 80)
    row.country = field(form, "country", 80)
    row.phone = field(form, "phone", 40)
    row.fax = field(form, "fax", 40)
    try:
        row.email = parse_email(field(form, "email", 255)) if field(form, "email", 255) else ""
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/hotel")
    row.policies = block(form, "policies", 5000)
    row.currency = site.currency
    db.add(row)
    audit(db, request, request.app.state.settings, user.email, "hotel.property", site.slug, "")
    db.commit()
    flash(request, "ok", "Hotel details saved.")
    return redirect(f"/admin/sites/{site.id}/hotel")


@router.post("/admin/sites/{site_id:int}/hotel/rooms")
async def room_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "hotel")
    site = _featured(db, site_id, "hotel")
    form = await posted(request)
    name = field(form, "name", 80)
    if not name:
        flash(request, "error", "A room type needs a name.")
        return redirect(f"/admin/sites/{site.id}/hotel")
    rate = integer(form, "nightly_rate", 0, 0, 100000, "Nightly rate")
    capacity = integer(form, "capacity", 1, 1, 30, "Capacity")
    inventory = integer(form, "inventory", 1, 0, 500, "Inventory")
    room_id = integer(form, "room_id", 0, 0, 10_000_000, "Room")
    room = db.get(RoomType, room_id) if room_id else None
    if room is not None and room.site_id != site.id:
        raise HTTPException(status_code=404, detail="That room does not exist.")
    taken = db.scalar(select(RoomType).where(RoomType.site_id == site.id, RoomType.name == name))
    if taken is not None and (room is None or taken.id != room.id):
        flash(request, "error", "That room type already exists.")
        return redirect(f"/admin/sites/{site.id}/hotel")
    if room is None:
        room = RoomType(site_id=site.id, name=name, nightly_rate_cents=rate * 100, capacity=capacity, inventory=inventory)
        db.add(room)
    else:
        room.name = name
        room.nightly_rate_cents = rate * 100
        room.capacity = capacity
        room.inventory = inventory
    room.description = block(form, "description", 2000)
    audit(db, request, request.app.state.settings, user.email, "hotel.room", f"{site.slug}/{name}", "")
    db.commit()
    flash(request, "ok", "Room type saved.")
    return redirect(f"/admin/sites/{site.id}/hotel")


@router.post("/admin/sites/{site_id:int}/hotel/rooms/{room_id:int}/delete")
async def room_delete(site_id: int, room_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "hotel")
    site = _featured(db, site_id, "hotel")
    await posted(request)
    room = db.get(RoomType, room_id)
    if room is None or room.site_id != site.id:
        raise HTTPException(status_code=404, detail="That room does not exist.")
    active = db.scalar(select(Reservation.id).where(Reservation.room_type_id == room.id, Reservation.status == "confirmed"))
    if active:
        flash(request, "error", "Cancel confirmed reservations before deleting this room type.")
        return redirect(f"/admin/sites/{site.id}/hotel")
    db.delete(room)
    audit(db, request, request.app.state.settings, user.email, "hotel.room_delete", f"{site.slug}/{room.name}", "")
    db.commit()
    flash(request, "ok", "Room type deleted.")
    return redirect(f"/admin/sites/{site.id}/hotel")


@router.post("/admin/sites/{site_id:int}/hotel/reservations/{reservation_id:int}")
async def reservation_update(site_id: int, reservation_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "hotel")
    site = _featured(db, site_id, "hotel")
    form = await posted(request)
    reservation = db.get(Reservation, reservation_id)
    if reservation is None or reservation.site_id != site.id:
        raise HTTPException(status_code=404, detail="That reservation does not exist.")
    if field(form, "action", 20) == "cancel":
        try:
            cancel_reservation(db, reservation, user.display_name)
        except FormError as exc:
            flash(request, "error", str(exc))
            return redirect(f"/admin/sites/{site.id}/hotel")
        audit(db, request, request.app.state.settings, user.email, "reservation.cancel", reservation.confirmation_code, "staff")
        db.commit()
        flash(request, "ok", "Reservation cancelled.")
        return redirect(f"/admin/sites/{site.id}/hotel")
    reservation.first_name = field(form, "first_name", 80) or reservation.first_name
    reservation.last_name = field(form, "last_name", 80) or reservation.last_name
    try:
        reservation.email = parse_email(field(form, "email", 255))
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/hotel")
    reservation.phone = field(form, "phone", 40)
    reservation.address = field(form, "address", 160)
    reservation.city = field(form, "city", 80)
    reservation.comments = redact_secrets(block(form, "comments", 2000))
    audit(db, request, request.app.state.settings, user.email, "reservation.update", reservation.confirmation_code, "")
    db.commit()
    flash(request, "ok", "Guest details updated.")
    return redirect(f"/admin/sites/{site.id}/hotel")


@router.get("/admin/sites/{site_id:int}/catalog")
def catalog(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = _featured(db, site_id, "catalog")
    categories = db.scalars(select(Category).where(Category.site_id == site.id).order_by(Category.name)).all()
    products = db.scalars(select(Product).where(Product.site_id == site.id).order_by(Product.name)).all()
    return render(request, "admin/catalog.html", site=site, sections=_sections(site, user), categories=categories, products=products)


@router.post("/admin/sites/{site_id:int}/catalog")
async def catalog_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = _featured(db, site_id, "catalog")
    form = await posted(request)
    if field(form, "action", 20) == "category":
        name = field(form, "category_name", 80)
        if not name:
            flash(request, "error", "A category needs a name.")
            return redirect(f"/admin/sites/{site.id}/catalog")
        slug = unique_child_slug(db, Category, site.id, slugify(name))
        db.add(Category(site_id=site.id, name=name, slug=slug))
        db.commit()
        flash(request, "ok", "Category added.")
        return redirect(f"/admin/sites/{site.id}/catalog")
    name = field(form, "name", 120)
    if not name:
        flash(request, "error", "A product needs a name.")
        return redirect(f"/admin/sites/{site.id}/catalog")
    price = integer(form, "price", 0, 0, 100000, "Price")
    stock = integer(form, "stock", 0, 0, 100000, "Stock")
    product_id = integer(form, "product_id", 0, 0, 10_000_000, "Product")
    product = db.get(Product, product_id) if product_id else None
    if product is not None and product.site_id != site.id:
        raise HTTPException(status_code=404, detail="That product does not exist.")
    category_id = integer(form, "category_id", 0, 0, 10_000_000, "Category")
    category = db.get(Category, category_id) if category_id else None
    if category is not None and category.site_id != site.id:
        category = None
    if product is None:
        product = Product(site_id=site.id, name=name, slug=unique_child_slug(db, Product, site.id, slugify(name)), price_cents=price * 100, stock=stock)
        db.add(product)
    else:
        product.name = name
        product.price_cents = price * 100
        product.stock = stock
    product.category_id = category.id if category else None
    product.description = block(form, "description", 4000)
    product.active = form.get("active") == "yes"
    audit(db, request, request.app.state.settings, user.email, "catalog.product", f"{site.slug}/{product.slug}", "")
    db.commit()
    flash(request, "ok", "Product saved.")
    return redirect(f"/admin/sites/{site.id}/catalog")


@router.get("/admin/sites/{site_id:int}/forms")
def forms_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "forms")
    forms = db.scalars(select(FormDef).where(FormDef.site_id == site.id).order_by(FormDef.name)).all()
    return render(request, "admin/forms.html", site=site, sections=_sections(site, user), forms=forms)


@router.post("/admin/sites/{site_id:int}/forms")
async def forms_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "forms")
    form = await posted(request)
    name = field(form, "name", 80)
    try:
        fields = _form_fields(block(form, "fields", 4000))
        if not name:
            raise FormError("A form needs a name.")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/forms")
    slug = unique_child_slug(db, FormDef, site.id, slugify(name))
    db.add(FormDef(site_id=site.id, name=name, slug=slug, description=field(form, "description", 300), fields=fields))
    audit(db, request, request.app.state.settings, user.email, "form.create", f"{site.slug}/{slug}", "")
    db.commit()
    flash(request, "ok", "Form created.")
    return redirect(f"/admin/sites/{site.id}/forms")


@router.get("/admin/sites/{site_id:int}/forms/{form_id:int}")
def form_submissions(site_id: int, form_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "forms")
    form_def = db.get(FormDef, form_id)
    if form_def is None or form_def.site_id != site.id:
        raise HTTPException(status_code=404, detail="That form does not exist.")
    rows = db.scalars(select(FormSubmission).where(FormSubmission.form_id == form_def.id).order_by(FormSubmission.created_at.desc())).all()
    return render(request, "admin/submissions.html", site=site, sections=_sections(site, user), form_def=form_def, submissions=rows)


@router.get("/admin/sites/{site_id:int}/help")
def help_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "help")
    articles = db.scalars(select(HelpArticle).where(HelpArticle.site_id == site.id).order_by(HelpArticle.id)).all()
    return render(request, "admin/help.html", site=site, sections=_sections(site, user), articles=articles)


@router.post("/admin/sites/{site_id:int}/help")
async def help_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "help")
    form = await posted(request)
    title = field(form, "title", 160)
    if not title:
        flash(request, "error", "A help article needs a title.")
        return redirect(f"/admin/sites/{site.id}/help")
    audience = "staff" if field(form, "audience", 16) == "staff" else "public"
    db.add(HelpArticle(site_id=site.id, title=title, body=block(form, "body", 8000), audience=audience))
    audit(db, request, request.app.state.settings, user.email, "help.create", f"{site.slug}/{title}", audience)
    db.commit()
    flash(request, "ok", "Help article saved.")
    return redirect(f"/admin/sites/{site.id}/help")


@router.get("/admin/sites/{site_id:int}/generate")
def generate_form(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = site_or_404(db, site_id)
    archive = Path(request.app.state.settings.generated_dir) / f"{site.slug}.zip"
    return render(request, "admin/generate.html", site=site, sections=_sections(site, user), ready=archive.is_file())


@router.post("/admin/sites/{site_id:int}/generate")
async def generate_submit(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = site_or_404(db, site_id)
    await posted(request)
    settings = request.app.state.settings
    folder, archive = generate_site(db, site, Path(settings.upload_dir), Path(settings.generated_dir))
    audit(db, request, settings, user.email, "site.generate", site.slug, archive.name)
    db.commit()
    flash(request, "ok", f"Generated {folder.name}. Download the zip and deploy that folder.")
    return redirect(f"/admin/sites/{site.id}/generate")


@router.get("/admin/sites/{site_id:int}/download")
def download(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = site_or_404(db, site_id)
    root = Path(request.app.state.settings.generated_dir).resolve()
    archive = (root / f"{site.slug}.zip").resolve()
    if not archive.is_relative_to(root) or not archive.is_file():
        raise HTTPException(status_code=404, detail="Generate the site before downloading it.")
    return FileResponse(archive, media_type="application/zip", filename=f"{site.slug}.zip")


@router.get("/admin/users")
def users(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db)
    require_role(user, "owner")
    rows = db.scalars(select(User).order_by(User.email)).all()
    return render(request, "admin/users.html", users=rows, roles=sorted(_ROLES))


@router.post("/admin/users")
async def users_save(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db)
    require_role(user, "owner")
    form = await posted(request)
    action = field(form, "action", 20)
    if action == "deactivate":
        target = db.get(User, integer(form, "user_id", 0, 1, 10_000_000, "User"))
        if target is None:
            raise HTTPException(status_code=404, detail="That account does not exist.")
        if target.id == user.id:
            flash(request, "error", "You cannot deactivate your own account.")
            return redirect("/admin/users")
        if target.role == "owner" and _owners(db) <= 1:
            flash(request, "error", "Keep at least one owner.")
            return redirect("/admin/users")
        target.is_active = not target.is_active
        audit(db, request, request.app.state.settings, user.email, "staff.active", target.email, str(target.is_active))
        db.commit()
        return redirect("/admin/users")
    try:
        email = parse_email(field(form, "email", 255))
        username = field(form, "username", 32)
        role = field(form, "role", 20)
        password = form.get("password") if isinstance(form.get("password"), str) else ""
        if not _USERNAME.fullmatch(username):
            raise FormError("Usernames are 3 to 32 letters, digits, dots, or underscores.")
        if role not in _ROLES:
            raise FormError("Choose a valid role.")
        validate_password(password)
        if db.scalar(select(User).where((User.email == email) | (User.username == username))):
            raise FormError("That email or username is already in use.")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect("/admin/users")
    db.add(
        User(
            email=email,
            username=username,
            password_hash=hash_password(password, request.app.state.settings.env),
            first_name=field(form, "first_name", 80),
            last_name=field(form, "last_name", 80),
            role=role,
        )
    )
    audit(db, request, request.app.state.settings, user.email, "staff.create", email, role)
    db.commit()
    flash(request, "ok", "Staff account created. Share the password through a channel you trust.")
    return redirect("/admin/users")


@router.get("/admin/account")
def account(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db)
    return render(request, "admin/account.html")


@router.post("/admin/account")
async def account_save(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db)
    form = await posted(request)
    current = form.get("current") if isinstance(form.get("current"), str) else ""
    password = form.get("password") if isinstance(form.get("password"), str) else ""
    confirm = form.get("confirmation") if isinstance(form.get("confirmation"), str) else ""
    settings = request.app.state.settings
    if not verify_password(current, user.password_hash, settings.env):
        flash(request, "error", "The current password is wrong.")
        return redirect("/admin/account")
    try:
        validate_password(password)
        if password != confirm:
            raise FormError("The passwords do not match.")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect("/admin/account")
    user.password_hash = hash_password(password, settings.env)
    audit(db, request, settings, user.email, "staff.password", user.email, "")
    db.commit()
    flash(request, "ok", "Password changed.")
    return redirect("/admin/account")


@router.get("/admin/audit")
def audit_page(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200)).all()
    return render(request, "admin/audit.html", events=rows)


@router.get("/admin/outbox")
def outbox(request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db)
    require_role(user, "owner")
    rows = db.scalars(select(MailOutbox).order_by(MailOutbox.created_at.desc()).limit(100)).all()
    return render(request, "admin/outbox.html", messages=rows, show_body=request.app.state.settings.env != "production")


def _featured(db: Session, site_id: int, feature: str) -> Site:
    site = site_or_404(db, site_id)
    if not (site.features or {}).get(feature):
        raise HTTPException(status_code=404, detail="Turn that feature on in site settings first.")
    return site


def _page(db: Session, site: Site, page_id: int) -> Page:
    page = db.get(Page, page_id)
    if page is None or page.site_id != site.id:
        raise HTTPException(status_code=404, detail="That page does not exist.")
    return page


def _publish(page: Page) -> None:
    page.live_title = page.draft_title
    page.live_body = page.draft_body
    page.live_keywords = page.draft_keywords
    page.live_description = page.draft_description
    page.is_published = True


def _optional_parent(db: Session, site: Site, raw, page_id: int | None) -> int | None:
    if raw in (None, "", "0"):
        return None
    try:
        parent_id = int(raw)
    except (TypeError, ValueError):
        raise FormError("Choose a valid parent page.") from None
    parent = db.get(Page, parent_id)
    if parent is None or parent.site_id != site.id or parent.id == page_id or parent.parent_id is not None:
        raise FormError("Parent pages are one level deep and must belong to this site.")
    return parent.id


def _feature_flags(form) -> dict:
    return clean_features({key: form.get(f"feature_{key}") == "yes" for key, *_rest in FEATURES})


def _form_fields(text: str) -> list[dict]:
    fields = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            raise FormError("Each field is name | label | type | required.")
        name, label, kind = parts[0], parts[1], parts[2]
        if not _FIELD.fullmatch(name):
            raise FormError("Field names start with a letter and use lower-case letters, digits, or underscores.")
        if kind not in {"text", "email", "textarea", "tel"}:
            raise FormError("Field types are text, email, textarea, or tel.")
        fields.append({"name": name, "label": label[:80] or name, "type": kind, "required": len(parts) > 3 and parts[3].lower() in {"y", "yes", "true", "1"}})
    if not fields:
        raise FormError("Add at least one field.")
    return fields[:20]


def unique_child_slug(db: Session, model, site_id: int, base: str) -> str:
    slug = base or "item"
    number = 2
    while db.scalar(select(model).where(model.site_id == site_id, model.slug == slug)):
        slug = f"{base[:50]}-{number}"
        number += 1
    return slug


def _owners(db: Session) -> int:
    return len(db.scalars(select(User.id).where(User.role == "owner", User.is_active.is_(True))).all())


def _reset_row(db: Session, token: str):
    from liquid.security import aware

    row = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hash_token(token)))
    if row is None or row.used_at is not None:
        raise HTTPException(status_code=400, detail="That reset link is not valid.")
    expires = aware(row.expires_at)
    if expires is None or expires < utcnow():
        raise HTTPException(status_code=400, detail="That reset link has expired.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="That reset link is not valid.")
    return row, user


def _logs(db: Session, site: Site):
    return db.scalars(
        select(CancellationLog)
        .join(Reservation, Reservation.id == CancellationLog.reservation_id)
        .where(Reservation.site_id == site.id)
        .order_by(CancellationLog.created_at.desc())
    ).all()
