import importlib.util
import re
from datetime import datetime, timedelta, timezone

from tests.conftest import csrf, login

PAN = "4242424242424242"
CVV = "123"


def test_security_headers_and_no_public_staff_signup(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "Sitebuilder" in home.text
    assert home.headers["x-content-type-options"] == "nosniff"
    assert home.headers["x-frame-options"] == "DENY"
    assert "script-src 'none'" in home.headers["content-security-policy"]
    assert home.headers["x-robots-tag"] == "noindex, nofollow"
    assert home.headers["permissions-policy"].startswith("camera=()")
    assert client.get("/admin/users", follow_redirects=False).status_code == 303
    assert client.get("/admin/signup", follow_redirects=False).status_code == 404


def test_login_rejects_injection_and_missing_csrf(client):
    forged = client.post(
        "/admin/login",
        data={"csrf": "not-the-token", "email": "builder@liquidsoftware.local", "password": "TestOnly!Liquid2026"},
        follow_redirects=False,
    )
    assert forged.status_code == 403
    page = client.get("/admin/login")
    response = client.post(
        "/admin/login",
        data={"csrf": csrf(page.text), "email": "' OR 1=1 --", "password": "nope"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_account_lockout_uses_the_same_message(client):
    page = client.get("/admin/login")
    token = csrf(page.text)
    for _ in range(5):
        client.post(
            "/admin/login",
            data={"csrf": token, "email": "builder@liquidsoftware.local", "password": "wrong-password-1"},
            follow_redirects=True,
        )
        token = csrf(client.get("/admin/login").text)
    locked = client.post(
        "/admin/login",
        data={"csrf": token, "email": "builder@liquidsoftware.local", "password": "TestOnly!Liquid2026"},
        follow_redirects=True,
    )
    assert "Invalid email or password." in locked.text
    factory = client.app.state.session_factory
    from liquid.models import User
    from sqlalchemy import select

    with factory() as db:
        user = db.scalar(select(User).where(User.email == "builder@liquidsoftware.local"))
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    token = csrf(client.get("/admin/login").text)
    ok = client.post(
        "/admin/login",
        data={"csrf": token, "email": "builder@liquidsoftware.local", "password": "TestOnly!Liquid2026"},
        follow_redirects=False,
    )
    assert ok.headers["location"] == "/admin"


def test_editor_cannot_publish_and_script_is_stripped(client):
    assert login(client).headers["location"] == "/admin"
    users = client.get("/admin/users")
    client.post(
        "/admin/users",
        data={
            "csrf": csrf(users.text),
            "action": "create",
            "email": "editor@liquidsoftware.local",
            "username": "editor",
            "first_name": "Ed",
            "last_name": "Itor",
            "role": "editor",
            "password": "Editor!Liquid2026",
        },
        follow_redirects=True,
    )
    new_page = client.get("/admin/sites/1/pages/new")
    saved = client.post(
        "/admin/sites/1/pages",
        data={
            "csrf": csrf(new_page.text),
            "action": "publish",
            "title": "Notes",
            "slug": "notes",
            "nav_order": "5",
            "show_in_nav": "yes",
            "body": "<script>alert(1)</script><p>Hello</p><img src=\"/media/1\" alt=\"room\">",
            "keywords": "notes",
            "description": "Notes",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    public = client.get("/s/gateway/notes")
    assert public.status_code == 200
    assert "<script" not in public.text.lower()
    assert "Hello" in public.text
    client.post("/admin/logout", data={"csrf": csrf(client.get("/admin").text)}, follow_redirects=False)
    assert login(client, "editor@liquidsoftware.local", "Editor!Liquid2026").headers["location"] == "/admin"
    draft = client.get("/admin/sites/1/pages/new")
    created = client.post(
        "/admin/sites/1/pages",
        data={
            "csrf": csrf(draft.text),
            "action": "save",
            "title": "Draft only",
            "slug": "draft-only",
            "nav_order": "6",
            "body": "<p>Hidden</p>",
        },
        follow_redirects=False,
    )
    edit = created.headers["location"]
    forbidden = client.post(
        edit,
        data={"csrf": csrf(client.get(edit).text), "action": "publish", "title": "Draft only", "body": "<p>Hidden</p>"},
        follow_redirects=False,
    )
    assert forbidden.status_code == 403
    assert client.get("/s/gateway/draft-only").status_code == 404


def test_hotel_booking_discards_card_data_and_blocks_overlap(client):
    search = client.get("/s/gateway/hotel")
    client.post(
        "/s/gateway/hotel",
        data={
            "csrf": csrf(search.text),
            "check_in": "2026-12-01",
            "check_out": "2026-12-04",
            "rooms": "10",
            "adults": "2",
            "children": "0",
        },
        follow_redirects=True,
    )
    results = client.get("/s/gateway/hotel")
    link = re.search(r'href="(/s/gateway/hotel/book/\d+)"', results.text)
    assert link, results.text
    form = client.get(link.group(1))
    booked = client.post(
        link.group(1),
        data={
            "csrf": csrf(form.text),
            "first_name": "Ada",
            "last_name": "Guest",
            "email": "ada@example.com",
            "phone": "5105550101",
            "address": "1 Test Street",
            "city": "Oakland",
            "state": "CA",
            "postal": "94621",
            "country": "United States",
            "comments": f"card {PAN}",
            "card_brand": "Visa",
            "card_number": PAN,
            "card_exp": "12/28",
            "card_cvv": CVV,
            "agree": "yes",
        },
        follow_redirects=True,
    )
    assert "GA" in booked.text or "GATE-" in booked.text or booked.status_code == 200
    assert PAN not in booked.text
    assert CVV not in booked.text
    from liquid.models import Reservation
    from sqlalchemy import select

    with client.app.state.session_factory() as database:
        reservation = database.scalar(select(Reservation))
        stored = " ".join(str(getattr(reservation, column.name)) for column in Reservation.__table__.columns)
    assert PAN not in stored
    assert CVV not in stored
    assert reservation.payment_last4 == "4242"
    assert "[removed]" in reservation.comments
    again = client.get("/s/gateway/hotel")
    client.post(
        "/s/gateway/hotel",
        data={
            "csrf": csrf(again.text),
            "check_in": "2026-12-02",
            "check_out": "2026-12-05",
            "rooms": "1",
            "adults": "1",
            "children": "0",
        },
        follow_redirects=True,
    )
    sold_out = client.get("/s/gateway/hotel")
    assert "Not enough rooms are free." in sold_out.text


def test_generate_writes_a_runnable_site_without_legacy_files(client):
    assert login(client).status_code == 303
    page = client.get("/admin/sites/1/generate")
    client.post("/admin/sites/1/generate", data={"csrf": csrf(page.text)}, follow_redirects=True)
    generated = client.app.state.settings
    from pathlib import Path

    folder = Path(generated.generated_dir) / "gateway"
    assert (folder / "QUARANTINE.txt").is_file()
    assert (folder / "site_bundle.json").is_file()
    assert not list(folder.rglob("*.dll"))
    assert not list(folder.rglob("*.aspx"))
    bundle = (folder / "site_bundle.json").read_text(encoding="utf-8")
    assert "Welcome" in bundle
    assert "Publishing pages" not in bundle
    spec = importlib.util.spec_from_file_location("generated_gateway_site", folder / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from fastapi.testclient import TestClient

    generated_client = TestClient(module.app)
    home = generated_client.get("/")
    assert home.status_code == 200
    assert "Stay directly" in home.text
    assert "script-src 'none'" in home.headers["content-security-policy"]
    assert "unsafe-eval" not in home.headers["content-security-policy"]
    assert home.headers["permissions-policy"].startswith("camera=()")
    assert home.headers["cross-origin-opener-policy"] == "same-origin"
    assert home.headers["cross-origin-resource-policy"] == "same-origin"
    assert "x-robots-tag" not in home.headers
    sitemap = generated_client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "https://gateway.example/" in sitemap.text
    robots = generated_client.get("/robots.txt")
    assert "Sitemap: https://gateway.example/sitemap.xml" in robots.text
    search = generated_client.get("/hotel")
    generated_client.post(
        "/hotel",
        data={"csrf": csrf(search.text), "check_in": "2026-12-10", "check_out": "2026-12-12", "rooms": "1", "adults": "2", "children": "0"},
        follow_redirects=True,
    )
    offers = generated_client.get("/hotel")
    link = re.search(r'href="(/hotel/book/[^"]+)"', offers.text)
    assert link
    form = generated_client.get(link.group(1))
    done = generated_client.post(
        link.group(1),
        data={
            "csrf": csrf(form.text),
            "first_name": "Bea",
            "last_name": "Guest",
            "email": "bea@example.com",
            "phone": "5105550102",
            "card_brand": "Visa",
            "card_number": PAN,
            "card_exp": "12/28",
            "card_cvv": CVV,
        },
        follow_redirects=True,
    )
    assert done.status_code == 200
    assert PAN not in (folder / "site.db").read_bytes().decode("latin1", "ignore")


def test_new_site_form_creates_a_site_without_a_shipping_field(client):
    assert login(client).headers["location"] == "/admin"
    form = client.get("/admin/sites/new")
    assert form.status_code == 200
    created = client.post(
        "/admin/sites/new",
        data={
            "csrf": csrf(form.text),
            "name": "Harbor Inn",
            "company_name": "Harbor",
            "domain": "harbor.example",
            "tagline": "Stay",
            "language": "en",
            "currency": "USD",
            "feature_cms": "yes",
            "feature_menus": "yes",
            "feature_search": "yes",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"].startswith("/admin/sites/")
    page = client.get(created.headers["location"])
    assert page.status_code == 200
    assert "Harbor Inn" in page.text
