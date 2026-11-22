"""Standalone site produced by Liquid Software.

This file is new. It does not load legacy binaries, does not call out to other
hosts, and does not keep card numbers.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import date
from html import escape
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from starlette.datastructures import Headers, MutableHeaders

ROOT = Path(__file__).resolve().parent
BUNDLE = json.loads((ROOT / "site_bundle.json").read_text(encoding="utf-8"))
DB_PATH = ROOT / "site.db"
TEMPLATES = Environment(
    loader=FileSystemLoader(str(ROOT / "templates")),
    autoescape=select_autoescape(["html"]),
)


def _secret() -> str:
    path = ROOT / ".secret"
    if path.exists():
        current = path.read_text(encoding="utf-8").strip()
        if len(current) >= 32:
            return current
    value = secrets.token_hex(32)
    path.write_text(value, encoding="utf-8")
    os.chmod(path, 0o600)
    return value


SECRET = _secret()
SERIALIZER = URLSafeTimedSerializer(SECRET, salt="generated-site")
SITE = BUNDLE["site"]
FEATURES = SITE["features"]
REDIRECTS = BUNDLE.get("redirects") or {}
_HOSTS = {item.strip().lower() for item in os.environ.get("SITE_ALLOWED_HOSTS", "").split(",") if item.strip()}
_COOKIE_SECURE = os.environ.get("SITE_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}
try:
    _SESSION_SECONDS = max(1, int(os.environ.get("SITE_SESSION_HOURS", "8") or "8")) * 3600
except ValueError:
    _SESSION_SECONDS = 8 * 3600
_POST_LIMIT = 40
_POST_WINDOW = 60
_BUCKETS: dict[str, list[float]] = {}
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    with db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE,
                room_name TEXT,
                rooms INTEGER,
                adults INTEGER,
                children INTEGER,
                check_in TEXT,
                check_out TEXT,
                nights INTEGER,
                total_cents INTEGER,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                phone TEXT,
                payment_brand TEXT,
                payment_last4 TEXT,
                payment_reference TEXT,
                status TEXT
            )
            """
        )


init_db()


def money(cents: int) -> str:
    amount = abs(int(cents))
    sign = "-" if cents < 0 else ""
    return f"{sign}{amount // 100:,}.{amount % 100:02d} {SITE['currency']}"


TEMPLATES.filters["money"] = money


def luhn_ok(number: str) -> bool:
    if not number.isdigit() or not 13 <= len(number) <= 19:
        return False
    total = 0
    parity = len(number) % 2
    for index, character in enumerate(number):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def accept_card(brand: str, number: str, expiry: str, code: str) -> dict:
    match = re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*(\d{2}|\d{4})", expiry.strip())
    if not match:
        raise ValueError("Enter the expiry as MM/YY.")
    pan = re.sub(r"\D", "", number)
    if not luhn_ok(pan):
        raise ValueError("The card number could not be verified.")
    if not re.fullmatch(r"\d{3,4}", re.sub(r"\D", "", code)):
        raise ValueError("The security code is invalid.")
    return {
        "brand": brand[:30],
        "last4": pan[-4:],
        "reference": "pay_" + secrets.token_hex(8),
    }


def load_session(header: str) -> dict:
    token = ""
    for part in header.split(";"):
        item = part.strip()
        if item.startswith("site_session="):
            token = item.split("=", 1)[1]
    if not token:
        return {"csrf": secrets.token_urlsafe(24)}
    try:
        data = SERIALIZER.loads(token, max_age=60 * 60 * 8)
    except (BadSignature, SignatureExpired):
        return {"csrf": secrets.token_urlsafe(24)}
    if not isinstance(data, dict) or "csrf" not in data:
        return {"csrf": secrets.token_urlsafe(24)}
    return data


def render(request: Request, name: str, status: int = 200, **context) -> HTMLResponse:
    flash = request.state.session.pop("flash", None)
    pages = [page for page in BUNDLE["pages"] if page["show_in_nav"]]
    html = TEMPLATES.get_template(name).render(
        request=request,
        site=SITE,
        features=FEATURES,
        nav=pages,
        csrf=request.state.session.get("csrf", ""),
        flash=flash,
        theme=_theme(),
        seo=_seo(request, context.get("page") if isinstance(context.get("page"), dict) else None),
        **context,
    )
    return HTMLResponse(html, status_code=status)


def _theme() -> Markup:
    colors = SITE["colors"]
    css = (
        f"--ink: {colors['ink']}; --paper: {colors['paper']}; --accent: {colors['accent']}; "
        f"--header: {colors['header']}; --text: {colors['text']}"
    )
    if not re.fullmatch(r"(?:--[a-z]+: #[0-9a-f]{6}; )+--[a-z]+: #[0-9a-f]{6}", css):
        css = "--ink:#1a1814; --paper:#fbf6ee; --accent:#8c3d2f; --header:#24352c; --text:#241f1a"
    return Markup(css)


def page_by_slug(slug: str) -> dict | None:
    for page in BUNDLE["pages"]:
        if page["slug"] == slug:
            return page
    return None


def _client_ip(scope) -> str:
    client = scope.get("client")
    if not client:
        return ""
    return str(client[0])[:64]


def _allow_post(ip: str) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _BUCKETS.get(ip, []) if now - stamp < _POST_WINDOW]
    if len(recent) >= _POST_LIMIT:
        _BUCKETS[ip] = recent
        return False
    recent.append(now)
    _BUCKETS[ip] = recent
    return True


def _public_host(value: str) -> str:
    text = (value or "").strip().lower()
    if not text or "@" in text or "\\" in text or " " in text or ":" in text:
        return ""
    text = re.sub(r"^https?://", "", text).split("/", 1)[0].split("?", 1)[0].strip(".")
    if not _HOST.fullmatch(text):
        return ""
    return text


def _origin(request: Request) -> str:
    host = _public_host(str(SITE.get("domain") or ""))
    if host:
        return f"https://{host}"
    return str(request.base_url).rstrip("/")


def _page_path(slug: str) -> str:
    return "/" if slug == "home" else f"/{slug}"


def _seo(request: Request, page: dict | None) -> dict:
    if page:
        title = page.get("title") or SITE["name"]
        description = page.get("description") or ""
        keywords = page.get("keywords") or ""
        path = _page_path(page.get("slug") or "")
    else:
        title = SITE["name"]
        description = SITE.get("tagline") or ""
        keywords = ""
        path = request.url.path
    origin = _origin(request)
    return {
        "title": title,
        "description": description,
        "keywords": keywords,
        "canonical": f"{origin}{path if path.startswith('/') else '/' + path}",
        "robots": "index, follow",
    }


def booked(room_name: str, check_in: str, check_out: str) -> int:
    with db() as connection:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(rooms), 0) AS taken FROM reservations
            WHERE room_name = ? AND status = 'confirmed' AND check_in < ? AND check_out > ?
            """,
            (room_name, check_out, check_in),
        ).fetchone()
    return int(row["taken"])


def room_by_name(name: str) -> dict | None:
    for room in BUNDLE["rooms"]:
        if room["name"] == name:
            return room
    return None


class SessionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        scope.setdefault("state", {})
        scope["state"]["session"] = load_session(Headers(scope=scope).get("cookie", ""))

        host = Headers(scope=scope).get("host", "").split(":")[0].lower()
        if _HOSTS and host not in _HOSTS:
            await Response("Host is not allowed.", status_code=400)(scope, receive, send)
            return
        if scope.get("method") == "POST" and not _allow_post(_client_ip(scope)):
            await Response("Too many requests.", status_code=429)(scope, receive, send)
            return

        async def send_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=list(message.get("headers", [])))
                token = SERIALIZER.dumps(scope["state"]["session"])
                cookie = Response()
                cookie.set_cookie(
                    "site_session",
                    token,
                    max_age=_SESSION_SECONDS,
                    httponly=True,
                    samesite="lax",
                    secure=_COOKIE_SECURE,
                    path="/",
                )
                headers.append("set-cookie", cookie.headers["set-cookie"])
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
                headers["Content-Security-Policy"] = (
                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                    "font-src 'self' data:; connect-src 'self'; script-src 'none'; form-action 'self'; "
                    "frame-src 'none'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; worker-src 'none'"
                )
                headers["Cross-Origin-Opener-Policy"] = "same-origin"
                headers["Cross-Origin-Resource-Policy"] = "same-origin"
                headers["X-Permitted-Cross-Domain-Policies"] = "none"
                headers["Cache-Control"] = "no-store"
                if "server" in headers:
                    del headers["server"]
                message["headers"] = headers.raw
            await send(message)

        await self.app(scope, receive, send_headers)


app = FastAPI(title=SITE["name"], docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def csrf_ok(request: Request, form) -> bool:
    supplied = form.get("csrf") if isinstance(form.get("csrf"), str) else ""
    expected = request.state.session.get("csrf", "")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def feature(name: str) -> bool:
    return bool(FEATURES.get(name))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    page = page_by_slug("home") or (BUNDLE["pages"][0] if BUNDLE["pages"] else None)
    if page is None:
        return HTMLResponse("This site has no published pages.", status_code=404)
    return render(request, "page.html", page=page, body=Markup(page["body"]))


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    if not feature("search"):
        return HTMLResponse("Not found", status_code=404)
    query = q.strip()[:80]
    results = []
    if len(query) >= 2:
        needle = query.lower()
        results = [page for page in BUNDLE["pages"] if needle in page["title"].lower() or needle in page["body"].lower()]
    return render(request, "search.html", query=query, results=results)


@app.get("/hotel", response_class=HTMLResponse)
def hotel(request: Request):
    if not feature("hotel"):
        return HTMLResponse("Not found", status_code=404)
    stay = request.state.session.get("stay")
    offers = []
    if stay:
        for room in BUNDLE["rooms"]:
            taken = booked(room["name"], stay["check_in"], stay["check_out"])
            available = max(0, room["inventory"] - taken)
            nights = (date.fromisoformat(stay["check_out"]) - date.fromisoformat(stay["check_in"])).days
            offers.append({"room": room, "available": available, "nights": nights, "total": room["nightly_rate_cents"] * nights * stay["rooms"]})
    return render(request, "hotel.html", stay=stay, offers=offers, today=date.today().isoformat(), property_row=BUNDLE.get("property"))


@app.post("/hotel")
async def hotel_search(request: Request):
    if not feature("hotel"):
        return HTMLResponse("Not found", status_code=404)
    form = await request.form()
    if not csrf_ok(request, form):
        return HTMLResponse("The form expired.", status_code=403)
    try:
        check_in = date.fromisoformat(str(form.get("check_in")))
        check_out = date.fromisoformat(str(form.get("check_out")))
        rooms = int(form.get("rooms", "1"))
        adults = int(form.get("adults", "1"))
        children = int(form.get("children", "0"))
    except (TypeError, ValueError):
        request.state.session["flash"] = {"level": "error", "message": "Check the dates and guest counts."}
        return RedirectResponse("/hotel", status_code=303)
    nights = (check_out - check_in).days
    if check_in < date.today() or not 1 <= nights <= 30 or not 1 <= rooms <= 10 or adults < 1 or children < 0:
        request.state.session["flash"] = {"level": "error", "message": "Those dates or guest counts are not accepted."}
        return RedirectResponse("/hotel", status_code=303)
    request.state.session["stay"] = {
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "rooms": rooms,
        "adults": adults,
        "children": children,
    }
    return RedirectResponse("/hotel", status_code=303)


@app.get("/hotel/book/{room_name}", response_class=HTMLResponse)
def book_form(room_name: str, request: Request):
    if not feature("hotel"):
        return HTMLResponse("Not found", status_code=404)
    room = room_by_name(room_name)
    stay = request.state.session.get("stay")
    if room is None or not stay:
        return HTMLResponse("Search for dates first.", status_code=404)
    nights = (date.fromisoformat(stay["check_out"]) - date.fromisoformat(stay["check_in"])).days
    return render(request, "book.html", room=room, stay=stay, nights=nights, total=room["nightly_rate_cents"] * nights * stay["rooms"], property_row=BUNDLE.get("property"))


@app.post("/hotel/book/{room_name}")
async def book_submit(room_name: str, request: Request):
    if not feature("hotel"):
        return HTMLResponse("Not found", status_code=404)
    room = room_by_name(room_name)
    stay = request.state.session.get("stay")
    form = await request.form()
    if room is None or not stay or not csrf_ok(request, form):
        return HTMLResponse("The form expired.", status_code=403)
    try:
        receipt = accept_card(str(form.get("card_brand", "")), str(form.get("card_number", "")), str(form.get("card_exp", "")), str(form.get("card_cvv", "")))
    except ValueError as exc:
        request.state.session["flash"] = {"level": "error", "message": str(exc)}
        return RedirectResponse(f"/hotel/book/{room_name}", status_code=303)
    if booked(room["name"], stay["check_in"], stay["check_out"]) + stay["rooms"] > room["inventory"]:
        request.state.session["flash"] = {"level": "error", "message": "Those rooms were just taken."}
        return RedirectResponse("/hotel", status_code=303)
    code = "RS-" + secrets.token_hex(4).upper()
    nights = (date.fromisoformat(stay["check_out"]) - date.fromisoformat(stay["check_in"])).days
    with db() as connection:
        connection.execute(
            """
            INSERT INTO reservations (code, room_name, rooms, adults, children, check_in, check_out, nights, total_cents,
              first_name, last_name, email, phone, payment_brand, payment_last4, payment_reference, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')
            """,
            (
                code,
                room["name"],
                stay["rooms"],
                stay["adults"],
                stay["children"],
                stay["check_in"],
                stay["check_out"],
                nights,
                room["nightly_rate_cents"] * nights * stay["rooms"],
                str(form.get("first_name", ""))[:80],
                str(form.get("last_name", ""))[:80],
                str(form.get("email", ""))[:255],
                str(form.get("phone", ""))[:40],
                receipt["brand"],
                receipt["last4"],
                receipt["reference"],
            ),
        )
    return RedirectResponse(f"/hotel/confirmation/{code}", status_code=303)


@app.get("/hotel/confirmation/{code}", response_class=HTMLResponse)
def confirmation(code: str, request: Request):
    with db() as connection:
        reservation = connection.execute("SELECT * FROM reservations WHERE code = ?", (code,)).fetchone()
    if reservation is None:
        return HTMLResponse("Not found", status_code=404)
    return render(request, "confirm.html", reservation=reservation)


def _records(kind: str) -> list:
    return BUNDLE.get(kind) or []


@app.get("/news", response_class=HTMLResponse)
def generated_news(request: Request):
    if not feature("news"):
        return HTMLResponse("Not found", status_code=404)
    return render(request, "records.html", heading="News", items=[{"title": row["title"], "html": Markup(row["body"])} for row in _records("news")])


@app.get("/banners", response_class=HTMLResponse)
def generated_banners(request: Request):
    if not feature("banners"):
        return HTMLResponse("Not found", status_code=404)
    items = []
    for row in _records("banners"):
        if not str(row.get("target_url", "")).startswith(("http://", "https://")):
            continue
        items.append({"title": row["name"], "href": row["target_url"]})
    return render(request, "records.html", heading="Banners", items=items)


@app.get("/calendar", response_class=HTMLResponse)
def generated_calendar(request: Request):
    if not feature("calendar"):
        return HTMLResponse("Not found", status_code=404)
    items = [{"title": row["title"], "meta": f"{row['starts_on']} {row.get('location', '')}", "html": Markup(row.get("body", ""))} for row in _records("events")]
    return render(request, "records.html", heading="Calendar", items=items)


@app.get("/services", response_class=HTMLResponse)
def generated_services(request: Request, q: str = ""):
    if not feature("services"):
        return HTMLResponse("Not found", status_code=404)
    query = q.strip().upper()
    rows = _records("services")
    if query:
        rows = [row for row in rows if query in {code.upper() for code in row.get("postal_codes", [])}]
    items = [{"title": row["name"], "meta": ", ".join(row.get("postal_codes", [])), "html": Markup(row.get("details", ""))} for row in rows]
    return render(request, "records.html", heading="Services", items=items)


@app.get("/learn", response_class=HTMLResponse)
def generated_learn(request: Request):
    if not feature("lms"):
        return HTMLResponse("Not found", status_code=404)
    items = []
    for course in _records("courses"):
        prompts = "".join(f"<p>{escape(question.get('prompt', ''))}</p>" for question in course.get("questions", []))
        items.append({"title": course["title"], "html": Markup(course.get("summary", "") + prompts)})
    return render(request, "records.html", heading="Courses", items=items)


@app.get("/coaches", response_class=HTMLResponse)
def generated_coaches(request: Request):
    if not feature("rv"):
        return HTMLResponse("Not found", status_code=404)
    items = [{"title": row["name"], "meta": str(row.get("year", "")), "html": Markup(row.get("summary", ""))} for row in _records("coaches")]
    return render(request, "records.html", heading="Coaches", items=items)


@app.get("/coupons", response_class=HTMLResponse)
def generated_coupons(request: Request):
    if not feature("coupons"):
        return HTMLResponse("Not found", status_code=404)
    items = [{"title": row["title"], "meta": f"{row.get('city', '')} {row.get('state', '')}", "html": Markup(row.get("details", ""))} for row in _records("coupons")]
    return render(request, "records.html", heading="Coupons", items=items)


@app.get("/gallery", response_class=HTMLResponse)
def generated_gallery(request: Request):
    if not feature("gallery"):
        return HTMLResponse("Not found", status_code=404)
    items = []
    for album in _records("albums"):
        blocks = []
        for image in album.get("images", []):
            name = image.get("file", "")
            caption = escape(image.get("caption", ""))
            if re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|jpeg|gif|webp)", name):
                blocks.append(f'<p><img src="/media/{name}" alt=""></p><p>{caption}</p>')
            elif image.get("kind") == "video" and re.fullmatch(r"[a-f0-9]{32}\.(mp4|webm)", name):
                blocks.append(f'<p><video controls src="/media/{name}"></video></p><p>{caption}</p>')
        items.append({"title": album["title"], "html": Markup("".join(blocks))})
    return render(request, "records.html", heading="Gallery", items=items)


@app.get("/robots.txt")
def robots(request: Request):
    return Response(f"User-agent: *\nAllow: /\nSitemap: {_origin(request)}/sitemap.xml\n", media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap(request: Request):
    origin = _origin(request)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    paths = BUNDLE.get("paths") or [{"path": _page_path(page["slug"]), "updated": page.get("updated") or ""} for page in BUNDLE["pages"]]
    for item in paths:
        loc = f"{origin}{item.get('path') or '/'}"
        row = f"<url><loc>{escape(loc)}</loc>"
        if item.get("updated"):
            row += f"<lastmod>{escape(str(item['updated']))}</lastmod>"
        lines.append(row + "</url>")
    lines.append("</urlset>")
    return Response("\n".join(lines) + "\n", media_type="application/xml")


@app.get("/{slug}", response_class=HTMLResponse)
def site_page(slug: str, request: Request):
    if slug in {"hotel", "search", "static", "media", "news", "banners", "calendar", "services", "gallery", "learn", "coaches", "coupons", "sitemap", "robots"}:
        return HTMLResponse("Not found", status_code=404)
    page = page_by_slug(slug)
    if page is None:
        target = REDIRECTS.get(slug)
        if target:
            return RedirectResponse(_page_path(target), status_code=301)
        return HTMLResponse("Not found", status_code=404)
    return render(request, "page.html", page=page, body=Markup(page["body"]))


@app.get("/media/{name}")
def media(name: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|jpeg|gif|webp|pdf|mp4|webm)", name):
        return HTMLResponse("Not found", status_code=404)
    path = (ROOT / "media" / name).resolve()
    if not path.is_relative_to((ROOT / "media").resolve()) or not path.is_file():
        return HTMLResponse("Not found", status_code=404)
    from fastapi.responses import FileResponse

    return FileResponse(path)
