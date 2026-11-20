"""Public marketing site and the sites Sitebuilder is previewing."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends
from markupsafe import Markup
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse

from liquid.db import get_db

from liquid.access import field, posted
from liquid.audit import audit
from liquid.constants import CARD_BRANDS, COUNTRIES, FEATURE_KEYS
from liquid.files import media_path
from liquid.hotel import (
    cancel_reservation,
    confirmation_code,
    fits_capacity,
    parse_stay,
    quote,
    rooms_available,
    stay_dates,
)
from liquid.mailer import queue_mail, reservation_messages
from liquid.models import (
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
from liquid.payments import accept_payment
from liquid.render import flash, redirect, render, theme_style
from liquid.security import client_ip, hash_password, rate_limit, validate_password, verify_password
from liquid.textutil import FormError, one_line, parse_email, plain, redact_secrets, sanitize_html, slugify, strip_tags

router = APIRouter()


def _site(db: Session, slug: str) -> Site:
    site = db.scalar(select(Site).where(Site.slug == slug))
    if site is None:
        raise HTTPException(status_code=404, detail="That site does not exist.")
    return site


def _feature(site: Site, key: str) -> None:
    if key not in FEATURE_KEYS or not (site.features or {}).get(key):
        raise HTTPException(status_code=404, detail="That feature is not part of this site.")


def _nav(db: Session, site: Site) -> list[Page]:
    if not (site.features or {}).get("cms") or not (site.features or {}).get("menus"):
        return []
    return list(
        db.scalars(
            select(Page)
            .where(Page.site_id == site.id, Page.is_published.is_(True), Page.show_in_nav.is_(True))
            .order_by(Page.nav_order, Page.id)
        ).all()
    )


def _customer(request: Request, db: Session, site: Site) -> Customer | None:
    customers = request.state.session.get("customers") or {}
    customer_id = customers.get(str(site.id))
    if not isinstance(customer_id, int):
        return None
    customer = db.get(Customer, customer_id)
    if customer is None or customer.site_id != site.id:
        return None
    return customer


def _context(request: Request, db: Session, site: Site) -> dict:
    return {
        "site": site,
        "features": site.features or {},
        "nav": _nav(db, site),
        "theme": theme_style(site),
        "customer": _customer(request, db, site),
    }


def _page(db: Session, site: Site, slug: str) -> Page:
    page = db.scalar(select(Page).where(Page.site_id == site.id, Page.slug == slug, Page.is_published.is_(True)))
    if page is None:
        raise HTTPException(status_code=404, detail="That page is not published.")
    return page


def _guest(form) -> dict:
    data = {
        "first_name": field(form, "first_name", 80),
        "last_name": field(form, "last_name", 80),
        "email": field(form, "email", 255),
        "phone": field(form, "phone", 40),
        "fax": field(form, "fax", 40),
        "company": field(form, "company", 80),
        "address": field(form, "address", 160),
        "city": field(form, "city", 80),
        "state": field(form, "state", 80),
        "postal": field(form, "postal", 20),
        "country": field(form, "country", 80),
        "comments": redact_secrets(plain(form.get("comments"), 2000) if isinstance(form.get("comments"), str) else ""),
    }
    missing = [name for name in ("first_name", "last_name", "email", "phone", "address", "city", "state", "postal", "country") if not data[name]]
    if missing:
        raise FormError("Complete the guest details.")
    data["email"] = parse_email(data["email"])
    if data["country"] not in COUNTRIES:
        raise FormError("Choose a country.")
    if form.get("agree") != "yes":
        raise FormError("Agree to the policy to continue.")
    return data


def _cart(request: Request, site: Site) -> list:
    carts = request.state.session.setdefault("carts", {})
    return carts.setdefault(str(site.id), [])


def _cart_view(db: Session, site: Site, raw: list) -> list[dict]:
    view = []
    for item in raw:
        product = db.get(Product, item.get("product_id"))
        if product is None or product.site_id != site.id or not product.active:
            continue
        quantity = max(1, min(int(item.get("qty", 1)), 20))
        view.append({"product": product, "qty": quantity, "line": product.price_cents * quantity})
    return view


@router.get("/")
def marketing(request: Request, db: Session = Depends(get_db)):
    gateway = db.scalar(select(Site).where(Site.slug == "gateway"))
    return render(request, "marketing.html", gateway=gateway)


@router.get("/health")
def health():
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok"})


@router.get("/media/{media_id:int}")
def media(media_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(Media, media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="That file does not exist.")
    root = Path(request.app.state.settings.upload_dir)
    try:
        path = media_path(root, item.site_id, item.stored_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="That file does not exist.") from exc
    disposition = "inline" if item.content_type.startswith("image/") else "attachment"
    return FileResponse(path, media_type=item.content_type, filename=item.original_name, content_disposition_type=disposition)


@router.get("/s/{slug}")
@router.get("/s/{slug}/")
def site_home(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "cms")
    page = db.scalar(select(Page).where(Page.site_id == site.id, Page.slug == "home", Page.is_published.is_(True)))
    if page is None:
        page = db.scalar(
            select(Page).where(Page.site_id == site.id, Page.is_published.is_(True)).order_by(Page.nav_order, Page.id)
        )
    if page is None:
        raise HTTPException(status_code=404, detail="This site has no published pages yet.")
    return render(
        request,
        "public/page.html",
        page=page,
        body=Markup(sanitize_html(page.live_body)),
        **_context(request, db, site),
    )


@router.get("/s/{slug}/search")
def search(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "search")
    query = one_line(request.query_params.get("q", ""), 80)
    query = query.replace("%", "").replace("_", "")
    results = []
    if len(query) >= 2:
        like = f"%{query}%"
        rows = db.scalars(
            select(Page).where(
                Page.site_id == site.id,
                Page.is_published.is_(True),
                or_(Page.live_title.ilike(like), Page.live_body.ilike(like)),
            )
        ).all()
        results = [{"page": row, "snippet": strip_tags(row.live_body)[:180]} for row in rows]
    return render(request, "public/search.html", query=query, results=results, **_context(request, db, site))


@router.get("/s/{slug}/hotel")
def hotel_get(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "hotel")
    stay = (request.state.session.get("stays") or {}).get(str(site.id))
    property_row = db.scalar(select(HotelProperty).where(HotelProperty.site_id == site.id))
    offers = []
    if stay:
        check_in, check_out, nights = stay_dates(stay)
        for room in db.scalars(select(RoomType).where(RoomType.site_id == site.id).order_by(RoomType.name)).all():
            available = rooms_available(db, room, check_in, check_out)
            offers.append(
                {
                    "room": room,
                    "available": available,
                    "fits": fits_capacity(room, stay["rooms"], stay["adults"], stay["children"]),
                    "total": quote(room, nights, stay["rooms"]),
                    "nights": nights,
                }
            )
    return render(
        request,
        "public/hotel.html",
        stay=stay,
        property_row=property_row,
        offers=offers,
        today=date.today().isoformat(),
        **_context(request, db, site),
    )


@router.post("/s/{slug}/hotel")
async def hotel_post(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "hotel")
    form = await posted(request)
    try:
        stay = parse_stay(form)
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/hotel")
    request.state.session.setdefault("stays", {})[str(site.id)] = stay
    return redirect(f"/s/{site.slug}/hotel")


@router.get("/s/{slug}/hotel/book/{room_id:int}")
def book_form(slug: str, room_id: int, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "hotel")
    room, stay, nights, available = _bookable(db, site, request, room_id)
    property_row = db.scalar(select(HotelProperty).where(HotelProperty.site_id == site.id))
    return render(
        request,
        "public/book.html",
        room=room,
        stay=stay,
        nights=nights,
        available=available,
        total=quote(room, nights, stay["rooms"]),
        property_row=property_row,
        brands=CARD_BRANDS,
        countries=COUNTRIES,
        **_context(request, db, site),
    )


@router.post("/s/{slug}/hotel/book/{room_id:int}")
async def book_submit(slug: str, room_id: int, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "hotel")
    settings = request.app.state.settings
    if not rate_limit(f"book:{client_ip(request, settings)}", 30, 3600):
        raise HTTPException(status_code=429, detail="Too many booking attempts. Wait and try again.")
    form = await posted(request)
    room, stay, nights, _available = _bookable(db, site, request, room_id)
    try:
        guest = _guest(form)
        receipt = accept_payment(field(form, "card_brand", 30), field(form, "card_number", 40), field(form, "card_exp", 10), field(form, "card_cvv", 8))
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/hotel/book/{room.id}")
    check_in, check_out, nights = stay_dates(stay)
    if rooms_available(db, room, check_in, check_out) < stay["rooms"]:
        flash(request, "error", "Those rooms were just taken. Search again.")
        return redirect(f"/s/{site.slug}/hotel")
    code = confirmation_code(site.slug)
    reservation = Reservation(
        site_id=site.id,
        room_type_id=room.id,
        confirmation_code=code,
        rooms=stay["rooms"],
        adults=stay["adults"],
        children=stay["children"],
        check_in=check_in,
        check_out=check_out,
        nights=nights,
        nightly_rate_cents=room.nightly_rate_cents,
        total_cents=quote(room, nights, stay["rooms"]),
        payment_brand=receipt.brand,
        payment_last4=receipt.last4,
        payment_exp=receipt.exp,
        payment_reference=receipt.reference,
        status="confirmed",
        **guest,
    )
    db.add(reservation)
    property_row = db.scalar(select(HotelProperty).where(HotelProperty.site_id == site.id))
    summary = "\n".join(
        [
            f"Confirmation {code}",
            f"Room {room.name} x {stay['rooms']}",
            f"{check_in.isoformat()} to {check_out.isoformat()} ({nights} nights)",
            f"Total {reservation.total_cents / 100:.2f} {site.currency}",
            f"Paid with {receipt.brand} ending {receipt.last4}",
            f"Reference {receipt.reference}",
        ]
    )
    staff = property_row.email if property_row else ""
    for recipient, subject, body in reservation_messages(site.name, guest["email"], staff, summary):
        queue_mail(db, recipient, subject, body)
    audit(db, request, settings, guest["email"], "reservation.create", code, room.name)
    db.commit()
    return redirect(f"/s/{site.slug}/hotel/confirmation/{code}")


@router.get("/s/{slug}/hotel/confirmation/{code}")
def confirmation(slug: str, code: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "hotel")
    reservation = db.scalar(select(Reservation).where(Reservation.site_id == site.id, Reservation.confirmation_code == code))
    if reservation is None:
        raise HTTPException(status_code=404, detail="That confirmation does not exist.")
    property_row = db.scalar(select(HotelProperty).where(HotelProperty.site_id == site.id))
    return render(
        request,
        "public/confirm.html",
        reservation=reservation,
        property_row=property_row,
        **_context(request, db, site),
    )


@router.get("/s/{slug}/hotel/cancel")
def cancel_form(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "hotel")
    return render(request, "public/cancel.html", **_context(request, db, site))


@router.post("/s/{slug}/hotel/cancel")
async def cancel_submit(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "hotel")
    form = await posted(request)
    code = field(form, "confirmation_code", 20).upper()
    try:
        email = parse_email(field(form, "email", 255))
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/hotel/cancel")
    reservation = db.scalar(select(Reservation).where(Reservation.site_id == site.id, Reservation.confirmation_code == code))
    if reservation is None or reservation.email.lower() != email:
        flash(request, "error", "No matching reservation.")
        return redirect(f"/s/{site.slug}/hotel/cancel")
    try:
        cancel_reservation(db, reservation, "Guest")
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/hotel/cancel")
    audit(db, request, request.app.state.settings, email, "reservation.cancel", code, "guest")
    db.commit()
    flash(request, "ok", "The reservation is cancelled and the rooms are available again.")
    return redirect(f"/s/{site.slug}/hotel/confirmation/{code}")


@router.get("/s/{slug}/shop")
def shop(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "catalog")
    products = db.scalars(select(Product).where(Product.site_id == site.id, Product.active.is_(True)).order_by(Product.name)).all()
    return render(request, "public/shop.html", products=products, **_context(request, db, site))


@router.get("/s/{slug}/shop/{product_slug}")
def product_page(slug: str, product_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "catalog")
    product = db.scalar(select(Product).where(Product.site_id == site.id, Product.slug == product_slug, Product.active.is_(True)))
    if product is None:
        raise HTTPException(status_code=404, detail="That product is not available.")
    return render(request, "public/product.html", product=product, **_context(request, db, site))


@router.post("/s/{slug}/cart")
async def cart_post(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "catalog")
    form = await posted(request)
    action = field(form, "action", 20)
    cart = _cart(request, site)
    if action == "add":
        product = db.scalar(select(Product).where(Product.site_id == site.id, Product.id == _int_or_zero(form.get("product_id")), Product.active.is_(True)))
        if product is None:
            raise HTTPException(status_code=404, detail="That product is not available.")
        quantity = max(1, min(_int_or_zero(form.get("qty")) or 1, 20))
        for item in cart:
            if item.get("product_id") == product.id:
                item["qty"] = min(20, item["qty"] + quantity)
                break
        else:
            cart.append({"product_id": product.id, "qty": quantity})
        flash(request, "ok", "Added to the cart.")
    elif action == "update":
        wanted = _int_or_zero(form.get("product_id"))
        quantity = max(0, min(_int_or_zero(form.get("qty")), 20))
        kept = []
        for item in cart:
            if item.get("product_id") == wanted:
                if quantity:
                    item["qty"] = quantity
                    kept.append(item)
            else:
                kept.append(item)
        request.state.session["carts"][str(site.id)] = kept
    return redirect(f"/s/{site.slug}/cart")


@router.get("/s/{slug}/cart")
def cart_page(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "catalog")
    view = _cart_view(db, site, _cart(request, site))
    subtotal = sum(item["line"] for item in view)
    return render(request, "public/cart.html", items=view, subtotal=subtotal, **_context(request, db, site))


@router.get("/s/{slug}/checkout")
def checkout_form(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "catalog")
    view = _cart_view(db, site, _cart(request, site))
    if not view:
        flash(request, "error", "The cart is empty.")
        return redirect(f"/s/{site.slug}/shop")
    subtotal = sum(item["line"] for item in view)
    return render(
        request,
        "public/checkout.html",
        items=view,
        subtotal=subtotal,
        shipping=site.shipping_cents,
        total=subtotal + site.shipping_cents,
        brands=CARD_BRANDS,
        countries=COUNTRIES,
        **_context(request, db, site),
    )


@router.post("/s/{slug}/checkout")
async def checkout_submit(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "catalog")
    form = await posted(request)
    view = _cart_view(db, site, _cart(request, site))
    if not view:
        flash(request, "error", "The cart is empty.")
        return redirect(f"/s/{site.slug}/shop")
    try:
        buyer = _guest(form)
        receipt = accept_payment(field(form, "card_brand", 30), field(form, "card_number", 40), field(form, "card_exp", 10), field(form, "card_cvv", 8))
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/checkout")
    for item in view:
        product = db.get(Product, item["product"].id)
        if product is None or product.stock < item["qty"]:
            db.rollback()
            flash(request, "error", "Something in the cart is no longer in stock.")
            return redirect(f"/s/{site.slug}/cart")
        product.stock -= item["qty"]
    subtotal = sum(item["line"] for item in view)
    number = "OR-" + confirmation_code(site.slug).split("-", 1)[1]
    order = Order(
        site_id=site.id,
        number=number,
        email=buyer["email"],
        first_name=buyer["first_name"],
        last_name=buyer["last_name"],
        phone=buyer["phone"],
        address=buyer["address"],
        city=buyer["city"],
        state=buyer["state"],
        postal=buyer["postal"],
        country=buyer["country"],
        subtotal_cents=subtotal,
        shipping_cents=site.shipping_cents,
        total_cents=subtotal + site.shipping_cents,
        payment_brand=receipt.brand,
        payment_last4=receipt.last4,
        payment_reference=receipt.reference,
    )
    db.add(order)
    db.flush()
    for item in view:
        db.add(OrderLine(order_id=order.id, product_name=item["product"].name, quantity=item["qty"], unit_cents=item["product"].price_cents))
    request.state.session["carts"][str(site.id)] = []
    queue_mail(db, buyer["email"], f"Order {number} at {site.name}", f"Order {number}\nTotal {order.total_cents / 100:.2f} {site.currency}\nReference {receipt.reference}")
    audit(db, request, request.app.state.settings, buyer["email"], "order.create", number, "")
    db.commit()
    return redirect(f"/s/{site.slug}/orders/{number}")


@router.get("/s/{slug}/orders/{number}")
def order_page(slug: str, number: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "catalog")
    order = db.scalar(select(Order).where(Order.site_id == site.id, Order.number == number))
    if order is None:
        raise HTTPException(status_code=404, detail="That order does not exist.")
    return render(request, "public/order.html", order=order, **_context(request, db, site))


@router.get("/s/{slug}/forms/{form_slug}")
def form_page(slug: str, form_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "forms")
    form_def = _form(db, site, form_slug)
    return render(request, "public/form.html", form_def=form_def, **_context(request, db, site))


@router.post("/s/{slug}/forms/{form_slug}")
async def form_submit(slug: str, form_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "forms")
    form_def = _form(db, site, form_slug)
    form = await posted(request)
    payload = {}
    try:
        for spec in form_def.fields:
            value = plain(form.get(spec["name"]), 4000) if spec["type"] == "textarea" else field(form, spec["name"], 300)
            if spec.get("required") and not value:
                raise FormError(f"Enter {spec['label']}.")
            if spec["type"] == "email" and value:
                value = parse_email(value)
            payload[spec["name"]] = redact_secrets(value)
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/forms/{form_def.slug}")
    db.add(FormSubmission(form_id=form_def.id, payload=payload, ip=client_ip(request, request.app.state.settings)))
    db.commit()
    flash(request, "ok", "Sent. The site owner can read it in Sitebuilder.")
    return redirect(f"/s/{site.slug}/forms/{form_def.slug}")


@router.get("/s/{slug}/help")
def help_page(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "help")
    articles = db.scalars(select(HelpArticle).where(HelpArticle.site_id == site.id, HelpArticle.audience == "public").order_by(HelpArticle.id)).all()
    return render(request, "public/help.html", articles=articles, **_context(request, db, site))


@router.get("/s/{slug}/account")
def account_form(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "accounts")
    return render(request, "public/account.html", **_context(request, db, site))


@router.post("/s/{slug}/account")
async def account_submit(slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "accounts")
    form = await posted(request)
    action = field(form, "action", 20)
    customers = request.state.session.setdefault("customers", {})
    if action == "logout":
        customers.pop(str(site.id), None)
        flash(request, "ok", "Signed out.")
        return redirect(f"/s/{site.slug}/account")
    try:
        email = parse_email(field(form, "email", 255))
        password = form.get("password") if isinstance(form.get("password"), str) else ""
    except FormError as exc:
        flash(request, "error", str(exc))
        return redirect(f"/s/{site.slug}/account")
    settings = request.app.state.settings
    if action == "register":
        try:
            validate_password(password)
        except FormError as exc:
            flash(request, "error", str(exc))
            return redirect(f"/s/{site.slug}/account")
        if db.scalar(select(Customer).where(Customer.site_id == site.id, Customer.email == email)):
            flash(request, "error", "That email is already registered on this site.")
            return redirect(f"/s/{site.slug}/account")
        customer = Customer(
            site_id=site.id,
            email=email,
            password_hash=hash_password(password, settings.env),
            first_name=field(form, "first_name", 80),
            last_name=field(form, "last_name", 80),
        )
        db.add(customer)
        db.commit()
        customers[str(site.id)] = customer.id
        flash(request, "ok", "Account created.")
        return redirect(f"/s/{site.slug}/account")
    customer = db.scalar(select(Customer).where(Customer.site_id == site.id, Customer.email == email))
    if customer is None or not verify_password(password, customer.password_hash, settings.env):
        flash(request, "error", "Invalid email or password.")
        return redirect(f"/s/{site.slug}/account")
    customers[str(site.id)] = customer.id
    flash(request, "ok", "Signed in.")
    return redirect(f"/s/{site.slug}/account")


@router.get("/s/{slug}/{page_slug}")
def site_page(slug: str, page_slug: str, request: Request, db: Session = Depends(get_db)):
    site = _site(db, slug)
    _feature(site, "cms")
    page = _page(db, site, slugify(page_slug, ""))
    if not page.slug:
        raise HTTPException(status_code=404, detail="That page is not published.")
    return render(
        request,
        "public/page.html",
        page=page,
        body=Markup(sanitize_html(page.live_body)),
        **_context(request, db, site),
    )


def _bookable(db: Session, site: Site, request: Request, room_id: int):
    stay = (request.state.session.get("stays") or {}).get(str(site.id))
    if not stay:
        raise HTTPException(status_code=404, detail="Search for dates before booking.")
    room = db.get(RoomType, room_id)
    if room is None or room.site_id != site.id:
        raise HTTPException(status_code=404, detail="That room does not exist.")
    check_in, check_out, nights = stay_dates(stay)
    if not fits_capacity(room, stay["rooms"], stay["adults"], stay["children"]):
        raise HTTPException(status_code=400, detail="That room cannot hold the party. Search again.")
    available = rooms_available(db, room, check_in, check_out)
    if available < stay["rooms"]:
        raise HTTPException(status_code=409, detail="Not enough rooms are free for those dates.")
    return room, stay, nights, available


def _form(db: Session, site: Site, form_slug: str) -> FormDef:
    form_def = db.scalar(select(FormDef).where(FormDef.site_id == site.id, FormDef.slug == form_slug))
    if form_def is None:
        raise HTTPException(status_code=404, detail="That form does not exist.")
    return form_def


def _int_or_zero(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
