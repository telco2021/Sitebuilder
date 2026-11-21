"""News, banners, calendar, services, gallery, courses, coaches, coupons, and the local message queue.

These are the Sitebuilder modules that were still only in the ASP.NET source.
Passwords are hashed, card numbers are not stored, and messages stay on this server.
"""

from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends
from markupsafe import Markup
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.requests import Request

from liquid.access import block, field, integer, posted
from liquid.audit import audit
from liquid.db import get_db
from liquid.mailer import queue_mail
from liquid.models import (
    Banner,
    CalendarEvent,
    Coupon,
    CouponCategory,
    Course,
    CourseQuestion,
    Enrollment,
    GalleryAlbum,
    GalleryDesk,
    GalleryImage,
    Media,
    Merchant,
    NewsPost,
    QuizAttempt,
    RvAccount,
    RvCategory,
    RvFavorite,
    RvModel,
    RvOffer,
    ServiceOffer,
    Site,
    SmsMessage,
    Student,
)
from liquid.render import flash, redirect, render
from liquid.routes.admin import _featured, _guard, _sections
from liquid.routes.public import _context, _feature, _site
from liquid.security import (
    account_locked,
    client_ip,
    dummy_for,
    hash_password,
    rate_limit,
    register_failure,
    validate_password,
    verify_password,
)
from liquid.textutil import FormError, hex_color, http_url, parse_email, plain, redact_secrets, sanitize_html, slugify

router = APIRouter()
_PHONE = re.compile(r"\+?[0-9]{8,15}")
_POSTAL = re.compile(r"[A-Za-z0-9]{3,12}")


def _slug_for(db: Session, model, site_id: int, text: str) -> str:
    base = slugify(text, "item")
    slug = base
    number = 2
    while db.scalar(select(model.id).where(model.site_id == site_id, model.slug == slug)):
        slug = f"{base[:50]}-{number}"
        number += 1
    return slug


def _day(value: str, label: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise FormError(f"Enter a valid {label}.") from None


def _owned(db: Session, model, row_id: int, site_id: int):
    row = db.get(model, row_id)
    if row is None or row.site_id != site_id:
        raise HTTPException(status_code=404, detail="That record does not exist.")
    return row


def _session_id(request: Request, key: str, site_id: int) -> int | None:
    box = request.state.session.get(key) or {}
    value = box.get(str(site_id))
    return value if isinstance(value, int) else None


def _remember(request: Request, key: str, site_id: int, row_id: int) -> None:
    request.state.session.setdefault(key, {})[str(site_id)] = row_id


def _forget(request: Request, key: str, site_id: int) -> None:
    (request.state.session.get(key) or {}).pop(str(site_id), None)


def _optional_int(form, name: str) -> int:
    raw = form.get(name, "")
    if raw in (None, ""):
        return 0
    return integer(form, name, 0, 0, 10_000_000, name)


def _password_ok(settings, account, password: str) -> bool:
    if account is None:
        verify_password(password, dummy_for(settings.env), settings.env)
        return False
    if not account.is_active or account_locked(account):
        verify_password(password, account.password_hash, settings.env)
        return False
    if not verify_password(password, account.password_hash, settings.env):
        register_failure(account, settings)
        return False
    account.failed_logins = 0
    account.locked_until = None
    return True


def _html(value: str) -> Markup:
    return Markup(sanitize_html(value))


# --- News ---


@router.get("/admin/sites/{site_id:int}/news")
def news_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "news")
    rows = db.scalars(select(NewsPost).where(NewsPost.site_id == site.id).order_by(NewsPost.id.desc())).all()
    return render(request, "admin/stack_news.html", site=site, sections=_sections(site, user), posts=rows)


@router.post("/admin/sites/{site_id:int}/news")
async def news_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "news")
    form = await posted(request)
    if field(form, "action", 20) == "delete":
        db.delete(_owned(db, NewsPost, integer(form, "id", 0, 1, 10_000_000, "Article"), site.id))
        db.commit()
        return redirect(f"/admin/sites/{site.id}/news")
    try:
        title = field(form, "title", 160)
        if not title:
            raise FormError("An article needs a title.")
        tag = slugify(field(form, "tag", 40), "") or None
        if tag == "item":
            tag = None
        if tag and db.scalar(select(NewsPost.id).where(NewsPost.site_id == site.id, NewsPost.tag == tag)):
            raise FormError("That tag is already used.")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/news")
    db.add(
        NewsPost(
            site_id=site.id,
            title=title,
            slug=_slug_for(db, NewsPost, site.id, field(form, "slug", 60) or title),
            tag=tag,
            body=sanitize_html(block(form, "body", 20000)),
            is_published=form.get("publish") == "yes" and user.role != "editor",
        )
    )
    audit(db, request, request.app.state.settings, user.email, "news.create", f"{site.slug}/{title}", "")
    db.commit()
    flash(request, "ok", "Article saved.")
    return redirect(f"/admin/sites/{site.id}/news")


@router.get("/s/{slug}/news")
def news_list(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "news")
    rows = db.scalars(select(NewsPost).where(NewsPost.site_id == site.id, NewsPost.is_published.is_(True)).order_by(NewsPost.id.desc())).all()
    items = [{"title": row.title, "href": f"/s/{site.slug}/news/{row.slug}", "meta": row.tag or "", "html": _html(row.body)} for row in rows]
    return render(request, "public/stack_list.html", heading="News", items=items, **_context(request, db, site))


@router.get("/s/{slug}/news/{item_slug}")
def news_one(slug: str, item_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "news")
    row = db.scalar(select(NewsPost).where(NewsPost.site_id == site.id, NewsPost.slug == item_slug, NewsPost.is_published.is_(True)))
    if row is None:
        raise HTTPException(status_code=404, detail="That article is not published.")
    return render(request, "public/stack_list.html", heading=row.title, items=[{"title": row.title, "html": _html(row.body)}], **_context(request, db, site))


# --- Banners ---


@router.get("/admin/sites/{site_id:int}/banners")
def banners_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "banners")
    rows = db.scalars(select(Banner).where(Banner.site_id == site.id).order_by(Banner.sort_order, Banner.id)).all()
    return render(request, "admin/stack_banners.html", site=site, sections=_sections(site, user), banners=rows)


@router.post("/admin/sites/{site_id:int}/banners")
async def banners_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "banners")
    form = await posted(request)
    if field(form, "action", 20) == "delete":
        db.delete(_owned(db, Banner, integer(form, "id", 0, 1, 10_000_000, "Banner"), site.id))
        db.commit()
        return redirect(f"/admin/sites/{site.id}/banners")
    try:
        name = field(form, "name", 120)
        if not name:
            raise FormError("A banner needs a name.")
        target = http_url(field(form, "target_url", 300))
        starts = _day(field(form, "starts_on", 10), "start date")
        ends = _day(field(form, "ends_on", 10), "end date")
        if starts and ends and ends < starts:
            raise FormError("The end date is before the start date.")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/banners")
    image_id = _optional_int(form, "image_id")
    if image_id:
        media = db.get(Media, image_id)
        if media is None or media.site_id != site.id:
            flash(request, "error", "That image is not in this site.")
            return redirect(f"/admin/sites/{site.id}/banners")
    db.add(
        Banner(
            site_id=site.id,
            name=name,
            target_url=target,
            image_id=image_id or None,
            starts_on=starts,
            ends_on=ends,
            active=form.get("active") == "yes",
            sort_order=integer(form, "sort_order", 0, 0, 999, "Order"),
        )
    )
    audit(db, request, request.app.state.settings, user.email, "banner.create", f"{site.slug}/{name}", "")
    db.commit()
    flash(request, "ok", "Banner saved.")
    return redirect(f"/admin/sites/{site.id}/banners")


def _banner_live(row: Banner, today: date) -> bool:
    if not row.active:
        return False
    if row.starts_on and row.starts_on > today:
        return False
    if row.ends_on and row.ends_on < today:
        return False
    return True


@router.get("/s/{slug}/banners")
def banners_public(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "banners")
    today = date.today()
    rows = [row for row in db.scalars(select(Banner).where(Banner.site_id == site.id).order_by(Banner.sort_order, Banner.id)).all() if _banner_live(row, today)]
    items = []
    for row in rows:
        image = f'<p><img src="/media/{row.image_id}" alt=""></p>' if row.image_id else ""
        items.append({"title": row.name, "href": row.target_url, "html": Markup(image)})
    return render(request, "public/stack_list.html", heading="Banners", items=items, **_context(request, db, site))


# --- Calendar ---


@router.get("/admin/sites/{site_id:int}/calendar")
def calendar_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "calendar")
    rows = db.scalars(select(CalendarEvent).where(CalendarEvent.site_id == site.id).order_by(CalendarEvent.starts_on)).all()
    return render(request, "admin/stack_calendar.html", site=site, sections=_sections(site, user), events=rows)


@router.post("/admin/sites/{site_id:int}/calendar")
async def calendar_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "calendar")
    form = await posted(request)
    if field(form, "action", 20) == "delete":
        db.delete(_owned(db, CalendarEvent, integer(form, "id", 0, 1, 10_000_000, "Event"), site.id))
        db.commit()
        return redirect(f"/admin/sites/{site.id}/calendar")
    try:
        title = field(form, "title", 160)
        starts = _day(field(form, "starts_on", 10), "start date")
        ends = _day(field(form, "ends_on", 10), "end date") or starts
        if not title or starts is None or ends is None:
            raise FormError("An event needs a title and a start date.")
        if ends < starts:
            raise FormError("The end date is before the start date.")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/calendar")
    db.add(CalendarEvent(site_id=site.id, title=title, starts_on=starts, ends_on=ends, location=field(form, "location", 160), body=sanitize_html(block(form, "body", 8000))))
    audit(db, request, request.app.state.settings, user.email, "calendar.create", f"{site.slug}/{title}", "")
    db.commit()
    flash(request, "ok", "Event saved.")
    return redirect(f"/admin/sites/{site.id}/calendar")


@router.get("/s/{slug}/calendar")
def calendar_public(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "calendar")
    rows = db.scalars(select(CalendarEvent).where(CalendarEvent.site_id == site.id).order_by(CalendarEvent.starts_on)).all()
    items = [{"title": row.title, "meta": f"{row.starts_on.isoformat()} to {row.ends_on.isoformat()} {row.location}", "html": _html(row.body)} for row in rows]
    return render(request, "public/stack_list.html", heading="Calendar", items=items, **_context(request, db, site))


# --- Services ---


@router.get("/admin/sites/{site_id:int}/services")
def services_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "services")
    rows = db.scalars(select(ServiceOffer).where(ServiceOffer.site_id == site.id).order_by(ServiceOffer.name)).all()
    return render(request, "admin/stack_services.html", site=site, sections=_sections(site, user), services=rows)


@router.post("/admin/sites/{site_id:int}/services")
async def services_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "services")
    form = await posted(request)
    if field(form, "action", 20) == "delete":
        db.delete(_owned(db, ServiceOffer, integer(form, "id", 0, 1, 10_000_000, "Service"), site.id))
        db.commit()
        return redirect(f"/admin/sites/{site.id}/services")
    name = field(form, "name", 120)
    codes = []
    for part in field(form, "postal_codes", 400).replace(";", ",").split(","):
        token = part.strip().upper()
        if token and _POSTAL.fullmatch(token):
            codes.append(token)
    if not name or not codes:
        flash(request, "error", "A service needs a name and at least one postal code.")
        return redirect(f"/admin/sites/{site.id}/services")
    db.add(ServiceOffer(site_id=site.id, name=name, details=sanitize_html(block(form, "details", 4000)), postal_codes=codes[:40]))
    db.commit()
    flash(request, "ok", "Service saved.")
    return redirect(f"/admin/sites/{site.id}/services")


@router.get("/s/{slug}/services")
def services_public(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "services")
    query = field({"q": request.query_params.get("q", "")}, "q", 12).upper()
    rows = db.scalars(select(ServiceOffer).where(ServiceOffer.site_id == site.id).order_by(ServiceOffer.name)).all()
    if query:
        rows = [row for row in rows if query in {code.upper() for code in row.postal_codes}]
    items = [{"title": row.name, "meta": ", ".join(row.postal_codes), "html": _html(row.details)} for row in rows]
    return render(
        request,
        "public/stack_list.html",
        heading="Services",
        items=items,
        search_action=f"/s/{site.slug}/services",
        search_label="Postal code",
        query=query,
        **_context(request, db, site),
    )


# --- Messages (local only) ---


@router.get("/admin/sites/{site_id:int}/messages")
def messages_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = _featured(db, site_id, "sms")
    rows = db.scalars(select(SmsMessage).where(SmsMessage.site_id == site.id).order_by(SmsMessage.id.desc())).all()
    return render(request, "admin/stack_sms.html", site=site, sections=_sections(site, user), messages=rows)


@router.post("/admin/sites/{site_id:int}/messages")
async def messages_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher")
    site = _featured(db, site_id, "sms")
    settings = request.app.state.settings
    if not rate_limit(f"sms:{client_ip(request, settings)}", 30, 3600):
        raise HTTPException(status_code=429, detail="Too many messages. Wait and try again.")
    form = await posted(request)
    phone = field(form, "phone", 16).replace(" ", "").replace("-", "")
    body = plain(form.get("body"), 140)
    if not _PHONE.fullmatch(phone) or not body:
        flash(request, "error", "Enter a phone number and a message of 140 characters or fewer.")
        return redirect(f"/admin/sites/{site.id}/messages")
    db.add(SmsMessage(site_id=site.id, phone=phone, body=redact_secrets(body), status="queued"))
    audit(db, request, settings, user.email, "sms.queue", site.slug, "")
    db.commit()
    flash(request, "ok", "Queued on this server. It is not sent to a phone network.")
    return redirect(f"/admin/sites/{site.id}/messages")


# --- Courses ---


@router.get("/admin/sites/{site_id:int}/learn")
def learn_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "lms")
    courses = db.scalars(select(Course).where(Course.site_id == site.id).order_by(Course.title)).all()
    students = db.scalars(select(Student).where(Student.site_id == site.id).order_by(Student.email)).all()
    return render(request, "admin/stack_learn.html", site=site, sections=_sections(site, user), courses=courses, students=students)


@router.post("/admin/sites/{site_id:int}/learn")
async def learn_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "lms")
    form = await posted(request)
    action = field(form, "action", 20) or "course"
    settings = request.app.state.settings
    try:
        if action == "delete-course":
            course = _owned(db, Course, integer(form, "id", 0, 1, 10_000_000, "Course"), site.id)
            enrollment_ids = select(Enrollment.id).where(Enrollment.course_id == course.id)
            db.execute(delete(QuizAttempt).where(QuizAttempt.enrollment_id.in_(enrollment_ids)))
            db.execute(delete(Enrollment).where(Enrollment.course_id == course.id))
            db.execute(delete(CourseQuestion).where(CourseQuestion.course_id == course.id))
            db.delete(course)
        elif action == "question":
            if user.role == "editor":
                raise FormError("A publisher adds quiz questions.")
            course = _owned(db, Course, integer(form, "course_id", 0, 1, 10_000_000, "Course"), site.id)
            prompt = field(form, "prompt", 500)
            kind = field(form, "kind", 8)
            if kind == "tf":
                choices = ["True", "False"]
            else:
                choices = [line.strip() for line in block(form, "choices", 2000).splitlines() if line.strip()][:6]
                kind = "mcq"
            if not prompt or len(choices) < 2:
                raise FormError("A question needs a prompt and at least two choices.")
            correct = integer(form, "correct", 1, 1, len(choices), "Correct choice") - 1
            db.add(CourseQuestion(course_id=course.id, prompt=prompt, kind=kind, choices=choices, correct_index=correct))
        elif action == "student":
            if user.role == "editor":
                raise FormError("A publisher creates student accounts.")
            email = parse_email(field(form, "email", 255))
            password = form.get("password") if isinstance(form.get("password"), str) else ""
            validate_password(password)
            if db.scalar(select(Student).where(Student.site_id == site.id, Student.email == email)):
                raise FormError("That student already exists.")
            student = Student(site_id=site.id, email=email, name=field(form, "name", 120), password_hash=hash_password(password, settings.env))
            db.add(student)
            db.flush()
            course_id = _optional_int(form, "course_id")
            if course_id:
                course = _owned(db, Course, course_id, site.id)
                db.add(Enrollment(student_id=student.id, course_id=course.id))
        else:
            title = field(form, "title", 160)
            if not title:
                raise FormError("A course needs a title.")
            db.add(
                Course(
                    site_id=site.id,
                    title=title,
                    slug=_slug_for(db, Course, site.id, title),
                    summary=sanitize_html(block(form, "summary", 4000)),
                    is_published=form.get("publish") == "yes" and user.role != "editor",
                )
            )
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/learn")
    audit(db, request, settings, user.email, f"lms.{action}", site.slug, "")
    db.commit()
    flash(request, "ok", "Saved.")
    return redirect(f"/admin/sites/{site.id}/learn")


def _student(request: Request, db: Session, site: Site) -> Student | None:
    row_id = _session_id(request, "students", site.id)
    row = db.get(Student, row_id) if row_id else None
    if row is None or row.site_id != site.id or not row.is_active:
        return None
    return row


@router.get("/s/{slug}/learn/login")
def learn_login_form(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "lms")
    return render(request, "public/stack_account.html", heading="Course sign in", mode="login", action=f"/s/{site.slug}/learn/login", **_context(request, db, site))


@router.post("/s/{slug}/learn/login")
async def learn_login(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "lms")
    settings = request.app.state.settings
    if not rate_limit(f"learn:{client_ip(request, settings)}", 20, 600):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait and try again.")
    form = await posted(request)
    email = field(form, "email", 255).lower()
    password = form.get("password") if isinstance(form.get("password"), str) else ""
    student = db.scalar(select(Student).where(Student.site_id == site.id, Student.email == email))
    if not _password_ok(settings, student, password):
        db.commit()
        flash(request, "error", "Invalid email or password.")
        return redirect(f"/s/{site.slug}/learn/login")
    db.commit()
    _remember(request, "students", site.id, student.id)
    return redirect(f"/s/{site.slug}/learn")


@router.post("/s/{slug}/learn/logout")
async def learn_logout(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    await posted(request)
    _forget(request, "students", site.id)
    return redirect(f"/s/{site.slug}/learn/login")


@router.get("/s/{slug}/learn")
def learn_home(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "lms")
    student = _student(request, db, site)
    if student is None:
        return redirect(f"/s/{site.slug}/learn/login")
    enrolled = db.scalars(
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.student_id == student.id, Course.is_published.is_(True))
    ).all()
    items = [{"title": course.title, "href": f"/s/{site.slug}/learn/{course.slug}", "html": _html(course.summary)} for course in enrolled]
    return render(request, "public/stack_list.html", heading=f"Courses for {student.name or student.email}", items=items, **_context(request, db, site))


@router.get("/s/{slug}/learn/{course_slug}")
def learn_course(slug: str, course_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "lms")
    student = _student(request, db, site)
    if student is None:
        return redirect(f"/s/{site.slug}/learn/login")
    course = db.scalar(select(Course).where(Course.site_id == site.id, Course.slug == course_slug, Course.is_published.is_(True)))
    enrollment = None
    if course is not None:
        enrollment = db.scalar(select(Enrollment).where(Enrollment.student_id == student.id, Enrollment.course_id == course.id))
    if course is None or enrollment is None:
        raise HTTPException(status_code=404, detail="That course is not on your list.")
    questions = db.scalars(select(CourseQuestion).where(CourseQuestion.course_id == course.id).order_by(CourseQuestion.sort_order, CourseQuestion.id)).all()
    return render(request, "public/learn_quiz.html", course=course, summary=_html(course.summary), questions=questions, **_context(request, db, site))


@router.post("/s/{slug}/learn/{course_slug}")
async def learn_grade(slug: str, course_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "lms")
    student = _student(request, db, site)
    if student is None:
        return redirect(f"/s/{site.slug}/learn/login")
    course = db.scalar(select(Course).where(Course.site_id == site.id, Course.slug == course_slug, Course.is_published.is_(True)))
    enrollment = None
    if course is not None:
        enrollment = db.scalar(select(Enrollment).where(Enrollment.student_id == student.id, Enrollment.course_id == course.id))
    if course is None or enrollment is None:
        raise HTTPException(status_code=404, detail="That course is not on your list.")
    form = await posted(request)
    questions = db.scalars(select(CourseQuestion).where(CourseQuestion.course_id == course.id)).all()
    score = 0
    for question in questions:
        try:
            choice = int(form.get(f"q_{question.id}", -1))
        except (TypeError, ValueError):
            choice = -1
        if choice == question.correct_index:
            score += 1
    db.add(QuizAttempt(enrollment_id=enrollment.id, score=score, total=len(questions)))
    db.commit()
    flash(request, "ok", f"Score {score} of {len(questions)}.")
    return redirect(f"/s/{site.slug}/learn/{course.slug}")


# --- RV coaches ---


@router.get("/admin/sites/{site_id:int}/coaches")
def coaches_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "rv")
    categories = db.scalars(select(RvCategory).where(RvCategory.site_id == site.id).order_by(RvCategory.sort_order, RvCategory.name)).all()
    models = db.scalars(select(RvModel).where(RvModel.site_id == site.id).order_by(RvModel.name)).all()
    offers = db.scalars(select(RvOffer).join(RvModel, RvModel.id == RvOffer.model_id).where(RvModel.site_id == site.id).order_by(RvOffer.id.desc())).all()
    return render(request, "admin/stack_coaches.html", site=site, sections=_sections(site, user), categories=categories, models=models, offers=offers)


@router.post("/admin/sites/{site_id:int}/coaches")
async def coaches_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "rv")
    form = await posted(request)
    action = field(form, "action", 20) or "model"
    try:
        if action == "category":
            name = field(form, "name", 120)
            if not name:
                raise FormError("A category needs a name.")
            parent_id = _optional_int(form, "parent_id")
            parent = _owned(db, RvCategory, parent_id, site.id) if parent_id else None
            if parent is not None and parent.parent_id is not None:
                raise FormError("Categories are two levels deep.")
            db.add(RvCategory(site_id=site.id, parent_id=parent.id if parent else None, name=name, slug=_slug_for(db, RvCategory, site.id, name), sort_order=integer(form, "sort_order", 0, 0, 999, "Order")))
        else:
            name = field(form, "name", 160)
            if not name:
                raise FormError("A model needs a name.")
            category_id = _optional_int(form, "category_id")
            if category_id:
                _owned(db, RvCategory, category_id, site.id)
            db.add(
                RvModel(
                    site_id=site.id,
                    category_id=category_id or None,
                    name=name,
                    slug=_slug_for(db, RvModel, site.id, name),
                    year=integer(form, "year", date.today().year, 1950, date.today().year + 2, "Year"),
                    price_cents=integer(form, "price", 0, 0, 100000, "Price") * 100,
                    summary=sanitize_html(block(form, "summary", 8000)),
                    is_published=form.get("publish") == "yes" and user.role != "editor",
                )
            )
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/coaches")
    audit(db, request, request.app.state.settings, user.email, f"rv.{action}", site.slug, "")
    db.commit()
    flash(request, "ok", "Saved.")
    return redirect(f"/admin/sites/{site.id}/coaches")


def _rv_account(request: Request, db: Session, site: Site) -> RvAccount | None:
    row_id = _session_id(request, "rv", site.id)
    row = db.get(RvAccount, row_id) if row_id else None
    if row is None or row.site_id != site.id or not row.is_active:
        return None
    return row


@router.get("/s/{slug}/coaches/login")
def coaches_login_form(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "rv")
    return render(request, "public/stack_account.html", heading="Coach account", mode="both", action=f"/s/{site.slug}/coaches/login", **_context(request, db, site))


@router.post("/s/{slug}/coaches/login")
async def coaches_login(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "rv")
    settings = request.app.state.settings
    form = await posted(request)
    action = field(form, "action", 20) or "login"
    if action == "register":
        if not rate_limit(f"rvreg:{client_ip(request, settings)}", 5, 3600):
            raise HTTPException(status_code=429, detail="Too many registrations. Wait and try again.")
        try:
            email = parse_email(field(form, "email", 255))
            password = form.get("password") if isinstance(form.get("password"), str) else ""
            validate_password(password)
            if db.scalar(select(RvAccount).where(RvAccount.site_id == site.id, RvAccount.email == email)):
                raise FormError("That email is already registered.")
        except FormError as exc:
            flash(request, "error", str(exc))
            return redirect(f"/s/{site.slug}/coaches/login")
        account = RvAccount(site_id=site.id, email=email, name=field(form, "name", 120), password_hash=hash_password(password, settings.env))
        db.add(account)
        db.commit()
        _remember(request, "rv", site.id, account.id)
        return redirect(f"/s/{site.slug}/coaches")
    if not rate_limit(f"rvlogin:{client_ip(request, settings)}", 20, 600):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait and try again.")
    email = field(form, "email", 255).lower()
    password = form.get("password") if isinstance(form.get("password"), str) else ""
    account = db.scalar(select(RvAccount).where(RvAccount.site_id == site.id, RvAccount.email == email))
    if not _password_ok(settings, account, password):
        db.commit()
        flash(request, "error", "Invalid email or password.")
        return redirect(f"/s/{site.slug}/coaches/login")
    db.commit()
    _remember(request, "rv", site.id, account.id)
    return redirect(f"/s/{site.slug}/coaches")


@router.get("/s/{slug}/coaches")
def coaches_public(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "rv")
    models = db.scalars(select(RvModel).where(RvModel.site_id == site.id, RvModel.is_published.is_(True)).order_by(RvModel.name)).all()
    items = [{"title": row.name, "href": f"/s/{site.slug}/coaches/{row.slug}", "meta": f"{row.year} · {row.price_cents / 100:.2f} {site.currency}", "html": _html(row.summary)} for row in models]
    return render(request, "public/stack_list.html", heading="Coaches", items=items, **_context(request, db, site))


@router.get("/s/{slug}/coaches/{model_slug}")
def coach_one(slug: str, model_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "rv")
    row = db.scalar(select(RvModel).where(RvModel.site_id == site.id, RvModel.slug == model_slug, RvModel.is_published.is_(True)))
    if row is None:
        raise HTTPException(status_code=404, detail="That model is not published.")
    return render(request, "public/coach.html", model=row, summary=_html(row.summary), account=_rv_account(request, db, site), **_context(request, db, site))


@router.post("/s/{slug}/coaches/{model_slug}")
async def coach_act(slug: str, model_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "rv")
    account = _rv_account(request, db, site)
    if account is None:
        return redirect(f"/s/{site.slug}/coaches/login")
    row = db.scalar(select(RvModel).where(RvModel.site_id == site.id, RvModel.slug == model_slug, RvModel.is_published.is_(True)))
    if row is None:
        raise HTTPException(status_code=404, detail="That model is not published.")
    form = await posted(request)
    if field(form, "action", 20) == "favorite":
        if db.scalar(select(RvFavorite).where(RvFavorite.account_id == account.id, RvFavorite.model_id == row.id)) is None:
            db.add(RvFavorite(account_id=account.id, model_id=row.id))
        db.commit()
        flash(request, "ok", "Saved to your favorites.")
        return redirect(f"/s/{site.slug}/coaches/{row.slug}")
    amount = integer(form, "amount", 0, 1, 100000, "Offer")
    db.add(RvOffer(account_id=account.id, model_id=row.id, amount_cents=amount * 100, message=redact_secrets(plain(form.get("message"), 2000))))
    db.commit()
    flash(request, "ok", "Offer sent to the dealer. Payment details are not part of an offer.")
    return redirect(f"/s/{site.slug}/coaches/{row.slug}")


# --- Coupons ---


@router.get("/admin/sites/{site_id:int}/coupons")
def coupons_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "coupons")
    categories = db.scalars(select(CouponCategory).where(CouponCategory.site_id == site.id).order_by(CouponCategory.name)).all()
    merchants = db.scalars(select(Merchant).where(Merchant.site_id == site.id).order_by(Merchant.name)).all()
    coupons = db.scalars(select(Coupon).where(Coupon.site_id == site.id).order_by(Coupon.title)).all()
    return render(request, "admin/stack_coupons.html", site=site, sections=_sections(site, user), categories=categories, merchants=merchants, coupons=coupons)


@router.post("/admin/sites/{site_id:int}/coupons")
async def coupons_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "coupons")
    form = await posted(request)
    action = field(form, "action", 20) or "coupon"
    try:
        if action == "approve":
            if user.role == "editor":
                raise FormError("A publisher approves merchants.")
            merchant = _owned(db, Merchant, integer(form, "id", 0, 1, 10_000_000, "Merchant"), site.id)
            merchant.approved = True
        elif action == "category":
            name = field(form, "name", 120)
            if not name:
                raise FormError("A category needs a name.")
            db.add(CouponCategory(site_id=site.id, name=name, slug=_slug_for(db, CouponCategory, site.id, name)))
        elif action == "publish":
            if user.role == "editor":
                raise FormError("A publisher publishes coupons.")
            coupon = _owned(db, Coupon, integer(form, "id", 0, 1, 10_000_000, "Coupon"), site.id)
            coupon.is_published = True
        else:
            title = field(form, "title", 160)
            if not title:
                raise FormError("A coupon needs a title.")
            category_id = _optional_int(form, "category_id")
            if category_id:
                _owned(db, CouponCategory, category_id, site.id)
            db.add(
                Coupon(
                    site_id=site.id,
                    category_id=category_id or None,
                    title=title,
                    slug=_slug_for(db, Coupon, site.id, title),
                    details=redact_secrets(sanitize_html(block(form, "details", 4000))),
                    city=field(form, "city", 80),
                    state=field(form, "state", 80),
                    expires_on=_day(field(form, "expires_on", 10), "expiry"),
                    is_published=form.get("publish") == "yes" and user.role != "editor",
                )
            )
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/coupons")
    audit(db, request, request.app.state.settings, user.email, f"coupon.{action}", site.slug, "")
    db.commit()
    flash(request, "ok", "Saved.")
    return redirect(f"/admin/sites/{site.id}/coupons")


@router.get("/s/{slug}/coupons/signup")
def coupon_signup_form(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "coupons")
    return render(request, "public/stack_account.html", heading="Merchant request", mode="register", places=True, action=f"/s/{site.slug}/coupons/signup", **_context(request, db, site))


@router.post("/s/{slug}/coupons/signup")
async def coupon_signup(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "coupons")
    settings = request.app.state.settings
    if not rate_limit(f"merchant:{client_ip(request, settings)}", 5, 3600):
        raise HTTPException(status_code=429, detail="Too many requests. Wait and try again.")
    form = await posted(request)
    try:
        email = parse_email(field(form, "email", 255))
        password = form.get("password") if isinstance(form.get("password"), str) else ""
        validate_password(password)
        name = field(form, "name", 120)
        if not name:
            raise FormError("A merchant needs a name.")
        if db.scalar(select(Merchant).where(Merchant.site_id == site.id, Merchant.email == email)):
            raise FormError("That email is already registered.")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/coupons/signup")
    db.add(
        Merchant(
            site_id=site.id,
            email=email,
            name=name,
            city=field(form, "city", 80),
            state=field(form, "state", 80),
            password_hash=hash_password(password, settings.env),
            approved=False,
        )
    )
    db.commit()
    flash(request, "ok", "Request received. A publisher has to approve it before you can sign in.")
    return redirect(f"/s/{site.slug}/coupons")


@router.get("/s/{slug}/coupons/login")
def coupon_login_form(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "coupons")
    return render(request, "public/stack_account.html", heading="Merchant sign in", mode="login", action=f"/s/{site.slug}/coupons/login", **_context(request, db, site))


@router.post("/s/{slug}/coupons/login")
async def coupon_login(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "coupons")
    settings = request.app.state.settings
    if not rate_limit(f"merchantlogin:{client_ip(request, settings)}", 20, 600):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait and try again.")
    form = await posted(request)
    email = field(form, "email", 255).lower()
    password = form.get("password") if isinstance(form.get("password"), str) else ""
    merchant = db.scalar(select(Merchant).where(Merchant.site_id == site.id, Merchant.email == email))
    if not _password_ok(settings, merchant, password):
        db.commit()
        flash(request, "error", "Invalid email or password.")
        return redirect(f"/s/{site.slug}/coupons/login")
    if not merchant.approved:
        db.commit()
        flash(request, "error", "That account is waiting for approval.")
        return redirect(f"/s/{site.slug}/coupons/login")
    db.commit()
    _remember(request, "merchants", site.id, merchant.id)
    return redirect(f"/s/{site.slug}/coupons/desk")


@router.get("/s/{slug}/coupons/desk")
def coupon_desk(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "coupons")
    merchant_id = _session_id(request, "merchants", site.id)
    merchant = db.get(Merchant, merchant_id) if merchant_id else None
    if merchant is None or merchant.site_id != site.id or not merchant.approved:
        return redirect(f"/s/{site.slug}/coupons/login")
    rows = db.scalars(select(Coupon).where(Coupon.merchant_id == merchant.id).order_by(Coupon.id.desc())).all()
    return render(request, "public/coupon_desk.html", merchant=merchant, coupons=rows, **_context(request, db, site))


@router.post("/s/{slug}/coupons/desk")
async def coupon_desk_save(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "coupons")
    merchant_id = _session_id(request, "merchants", site.id)
    merchant = db.get(Merchant, merchant_id) if merchant_id else None
    if merchant is None or merchant.site_id != site.id or not merchant.approved:
        return redirect(f"/s/{site.slug}/coupons/login")
    form = await posted(request)
    title = field(form, "title", 160)
    if not title:
        flash(request, "error", "A coupon needs a title.")
        return redirect(f"/s/{site.slug}/coupons/desk")
    try:
        expires = _day(field(form, "expires_on", 10), "expiry")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/coupons/desk")
    db.add(
        Coupon(
            site_id=site.id,
            merchant_id=merchant.id,
            title=title,
            slug=_slug_for(db, Coupon, site.id, title),
            details=redact_secrets(sanitize_html(block(form, "details", 4000))),
            city=merchant.city,
            state=merchant.state,
            expires_on=expires,
            is_published=False,
        )
    )
    db.commit()
    flash(request, "ok", "Saved as a draft. A publisher publishes it.")
    return redirect(f"/s/{site.slug}/coupons/desk")


@router.get("/s/{slug}/coupons")
def coupons_public(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "coupons")
    city = field({"q": request.query_params.get("city", "")}, "q", 80).lower()
    state = field({"q": request.query_params.get("state", "")}, "q", 80).lower()
    rows = db.scalars(select(Coupon).where(Coupon.site_id == site.id, Coupon.is_published.is_(True)).order_by(Coupon.title)).all()
    today = date.today()
    visible = []
    for row in rows:
        if row.expires_on and row.expires_on < today:
            continue
        if city and city not in row.city.lower():
            continue
        if state and state not in row.state.lower():
            continue
        visible.append(row)
    items = [{"title": row.title, "meta": f"{row.city} {row.state}".strip(), "html": _html(row.details)} for row in visible]
    return render(request, "public/coupons.html", items=items, city=request.query_params.get("city", ""), state=request.query_params.get("state", ""), **_context(request, db, site))


# --- Gallery ---


def _desk(db: Session, site: Site) -> GalleryDesk:
    row = db.scalar(select(GalleryDesk).where(GalleryDesk.site_id == site.id))
    if row is None:
        row = GalleryDesk(site_id=site.id)
        db.add(row)
        db.commit()
    return row


def _open_albums(request: Request, site_id: int) -> set[int]:
    box = (request.state.session.get("gallery_open") or {}).get(str(site_id)) or []
    if not isinstance(box, list):
        return set()
    return {item for item in box if isinstance(item, int)}


def _grant_album(request: Request, site_id: int, album_id: int) -> None:
    current = [item for item in _open_albums(request, site_id)]
    if album_id not in current:
        current.append(album_id)
    request.state.session.setdefault("gallery_open", {})[str(site_id)] = current[-20:]


def _query_int(request: Request, name: str, default: int, low: int, high: int) -> int:
    raw = request.query_params.get(name, "")
    if not str(raw).isdigit():
        return default
    value = int(raw)
    if value < low or value > high:
        return default
    return value


def _album_items(db: Session, site: Site, album: GalleryAlbum, kind: str) -> list[tuple[GalleryImage, Media]]:
    rows = db.scalars(
        select(GalleryImage).where(GalleryImage.album_id == album.id, GalleryImage.kind == kind).order_by(GalleryImage.id)
    ).all()
    paired = []
    for image in rows:
        media = db.get(Media, image.media_id)
        if media is None or media.site_id != site.id:
            continue
        if kind == "image" and not media.content_type.startswith("image/"):
            continue
        if kind == "video" and media.content_type not in {"video/mp4", "video/webm"}:
            continue
        paired.append((image, media))
    return paired


@router.get("/admin/sites/{site_id:int}/gallery")
def gallery_admin(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "gallery")
    albums = db.scalars(select(GalleryAlbum).where(GalleryAlbum.site_id == site.id).order_by(GalleryAlbum.title)).all()
    media = db.scalars(select(Media).where(Media.site_id == site.id).order_by(Media.id.desc())).all()
    pictures = [item for item in media if item.content_type.startswith("image/")]
    videos = [item for item in media if item.content_type in {"video/mp4", "video/webm"}]
    return render(
        request,
        "admin/stack_gallery.html",
        site=site,
        sections=_sections(site, user),
        albums=albums,
        pictures=pictures,
        videos=videos,
        desk=_desk(db, site),
    )


@router.post("/admin/sites/{site_id:int}/gallery")
async def gallery_save(site_id: int, request: Request, db: Session = Depends(get_db)):
    user = _guard(request, db, "publisher", "editor")
    site = _featured(db, site_id, "gallery")
    form = await posted(request)
    action = field(form, "action", 20) or "album"
    try:
        _gallery_apply(db, request, site, form, action)
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/admin/sites/{site.id}/gallery")
    audit(db, request, request.app.state.settings, user.email, "gallery.save", site.slug, action)
    db.commit()
    flash(request, "ok", "Saved.")
    return redirect(f"/admin/sites/{site.id}/gallery")


def _gallery_apply(db: Session, request: Request, site: Site, form, action: str) -> None:
    if action == "settings":
        desk = _desk(db, site)
        desk.columns = integer(form, "columns", 3, 1, 6, "Columns")
        desk.rows = integer(form, "rows", 3, 1, 8, "Rows")
        desk.padding = integer(form, "padding", 4, 0, 40, "Padding")
        desk.border_width = integer(form, "border_width", 1, 0, 8, "Border")
        desk.border_color = hex_color(field(form, "border_color", 7), "#000000")
        desk.transition_seconds = integer(form, "transition_seconds", 4, 2, 30, "Transition")
        desk.copyright_name = field(form, "copyright_name", 160)
    elif action == "item":
        album = _owned(db, GalleryAlbum, integer(form, "album_id", 0, 1, 10_000_000, "Album"), site.id)
        media = db.get(Media, integer(form, "media_id", 0, 1, 10_000_000, "File"))
        kind = "image" if media and media.content_type.startswith("image/") else "video"
        allowed = media is not None and media.site_id == site.id and kind in {"image", "video"}
        if kind == "video":
            allowed = allowed and media.content_type in {"video/mp4", "video/webm"}
        if not allowed:
            raise FormError("Choose an image, MP4, or WebM file that belongs to this site.")
        db.add(
            GalleryImage(
                album_id=album.id,
                media_id=media.id,
                caption=field(form, "caption", 180),
                description=plain(form.get("description"), 500),
                kind=kind,
            )
        )
    elif action == "clear":
        album = _owned(db, GalleryAlbum, integer(form, "album_id", 0, 1, 10_000_000, "Album"), site.id)
        album.password_hash = None
    elif action == "lock":
        album = _owned(db, GalleryAlbum, integer(form, "album_id", 0, 1, 10_000_000, "Album"), site.id)
        album.password_hash = hash_password(validate_password(field(form, "password", 128)), request.app.state.settings.env)
    else:
        title = field(form, "title", 160)
        if not title:
            raise FormError("An album needs a title.")
        cover_id = _optional_int(form, "cover_media_id")
        cover = db.get(Media, cover_id) if cover_id else None
        if cover is not None and (cover.site_id != site.id or not cover.content_type.startswith("image/")):
            cover = None
        password = field(form, "password", 128)
        db.add(
            GalleryAlbum(
                site_id=site.id,
                title=title,
                slug=_slug_for(db, GalleryAlbum, site.id, title),
                cover_media_id=cover.id if cover else None,
                password_hash=hash_password(validate_password(password), request.app.state.settings.env) if password else None,
            )
        )


@router.get("/s/{slug}/gallery")
def gallery_public(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "gallery")
    desk = _desk(db, site)
    albums = db.scalars(select(GalleryAlbum).where(GalleryAlbum.site_id == site.id).order_by(GalleryAlbum.title)).all()
    return render(
        request,
        "public/gallery.html",
        mode="albums",
        albums=albums,
        desk=desk,
        album=None,
        items=[],
        pages=[],
        **_context(request, db, site),
    )


@router.post("/s/{slug}/gallery/{album_slug}/unlock")
async def gallery_unlock(slug: str, album_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "gallery")
    album = db.scalar(select(GalleryAlbum).where(GalleryAlbum.site_id == site.id, GalleryAlbum.slug == album_slug))
    if album is None or not album.password_hash:
        raise HTTPException(status_code=404, detail="That album does not exist.")
    settings = request.app.state.settings
    if not rate_limit(f"gallery:{client_ip(request, settings)}:{album.id}", 5, 900):
        raise HTTPException(status_code=429, detail="Too many attempts. Wait and try again.")
    form = await posted(request)
    password = field(form, "password", 128)
    if not verify_password(password, album.password_hash, settings.env):
        flash(request, "error", "That password does not unlock this album.")
        return redirect(f"/s/{site.slug}/gallery/{album.slug}")
    _grant_album(request, site.id, album.id)
    return redirect(f"/s/{site.slug}/gallery/{album.slug}")


@router.get("/s/{slug}/gallery/{album_slug}")
def gallery_album(slug: str, album_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "gallery")
    album = db.scalar(select(GalleryAlbum).where(GalleryAlbum.site_id == site.id, GalleryAlbum.slug == album_slug))
    if album is None:
        raise HTTPException(status_code=404, detail="That album does not exist.")
    desk = _desk(db, site)
    base = f"/s/{site.slug}/gallery/{album.slug}"
    if album.password_hash and album.id not in _open_albums(request, site.id):
        return render(request, "public/gallery.html", mode="locked", album=album, desk=desk, albums=[], items=[], pages=[], **_context(request, db, site))
    view = request.query_params.get("view", "")
    if view not in {"images", "videos"}:
        return render(request, "public/gallery.html", mode="hub", album=album, desk=desk, albums=[], items=[], pages=[], **_context(request, db, site))
    kind = "image" if view == "images" else "video"
    paired = _album_items(db, site, album, kind)
    item_id = _query_int(request, "item", 0, 0, 10_000_000)
    if item_id:
        chosen = next(((image, media) for image, media in paired if image.id == item_id), None)
        if chosen is None:
            raise HTTPException(status_code=404, detail="That file is not in this album.")
        index = next(position for position, (image, _) in enumerate(paired) if image.id == item_id)
        previous_id = paired[index - 1][0].id if index else paired[-1][0].id
        next_id = paired[(index + 1) % len(paired)][0].id
        play = request.query_params.get("play") == "1" and kind == "image"
        refresh_url = f"{base}?view={view}&item={next_id}&play=1" if play else ""
        return render(
            request,
            "public/gallery.html",
            mode="viewer",
            album=album,
            desk=desk,
            view=view,
            current=chosen[0],
            media=chosen[1],
            previous_url=f"{base}?view={view}&item={previous_id}",
            next_url=f"{base}?view={view}&item={next_id}",
            play_url=f"{base}?view={view}&item={item_id}&play=1",
            stop_url=f"{base}?view={view}&item={item_id}",
            refresh_url=refresh_url,
            albums=[],
            items=[],
            pages=[],
            **_context(request, db, site),
        )
    page_size = max(desk.rows, 1) * max(desk.columns, 1)
    page = _query_int(request, "page", 1, 1, 500)
    start = (page - 1) * page_size
    visible = paired[start : start + page_size]
    page_count = max(1, (len(paired) + page_size - 1) // page_size)
    pages = [{"n": number, "href": f"{base}?view={view}&page={number}", "current": number == page} for number in range(1, page_count + 1)]
    return render(
        request,
        "public/gallery.html",
        mode="grid",
        album=album,
        desk=desk,
        view=view,
        items=[{"id": image.id, "caption": image.caption, "media_id": media.id, "kind": kind} for image, media in visible],
        pages=pages,
        albums=[],
        **_context(request, db, site),
    )


# --- Tell a friend ---


@router.get("/s/{slug}/share")
def share_form(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "share")
    return render(request, "public/share.html", **_context(request, db, site))


@router.post("/s/{slug}/share")
async def share_send(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "share")
    settings = request.app.state.settings
    if not rate_limit(f"share:{client_ip(request, settings)}", 5, 3600):
        raise HTTPException(status_code=429, detail="Too many notes. Wait and try again.")
    form = await posted(request)
    try:
        recipient = parse_email(field(form, "email", 255))
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/share")
    note = redact_secrets(plain(form.get("note"), 500))
    page = field(form, "page", 60)
    queue_mail(db, recipient, f"A page at {site.name}", f"{site.name}\n/{page}\n\n{note}")
    db.commit()
    flash(request, "ok", "Queued on this server.")
    return redirect(f"/s/{site.slug}/share")
