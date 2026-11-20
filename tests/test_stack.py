"""The modules that were still only in the ASP.NET source."""

from tests.conftest import csrf, login

PAN = "4242424242424242"


def _enable(client):
    assert login(client).status_code == 303
    page = client.get("/admin/sites/1/settings")
    data = {
        "csrf": csrf(page.text),
        "name": "Gateway Hotel",
        "company_name": "Gateway Hotel",
        "domain": "gateway.example",
        "tagline": "A direct reservation desk for Gateway Hotel.",
        "language": "en",
        "currency": "USD",
        "shipping_cents": "0",
        "color_ink": "#1a1814",
        "color_paper": "#fbf6ee",
        "color_accent": "#8c3d2f",
        "color_header": "#24352c",
        "color_text": "#241f1a",
    }
    for key in (
        "cms",
        "menus",
        "search",
        "files",
        "help",
        "forms",
        "accounts",
        "catalog",
        "hotel",
        "news",
        "banners",
        "calendar",
        "services",
        "gallery",
        "share",
        "lms",
        "rv",
        "coupons",
        "sms",
    ):
        data[f"feature_{key}"] = "yes"
    saved = client.post("/admin/sites/1/settings", data=data, follow_redirects=True)
    assert saved.status_code == 200


def test_news_banner_sms_and_services(client):
    _enable(client)
    news = client.get("/admin/sites/1/news")
    client.post(
        "/admin/sites/1/news",
        data={
            "csrf": csrf(news.text),
            "title": "Desk note",
            "tag": "desk",
            "body": "<script>alert(1)</script><p>Open today</p>",
            "publish": "yes",
        },
        follow_redirects=True,
    )
    public = client.get("/s/gateway/news")
    assert public.status_code == 200
    assert "Open today" in public.text
    assert "<script" not in public.text.lower()

    banners = client.get("/admin/sites/1/banners")
    rejected = client.post(
        "/admin/sites/1/banners",
        data={"csrf": csrf(banners.text), "name": "Bad", "target_url": "javascript:alert(1)", "sort_order": "0", "active": "yes"},
        follow_redirects=True,
    )
    assert "http or https" in rejected.text
    client.post(
        "/admin/sites/1/banners",
        data={"csrf": csrf(client.get("/admin/sites/1/banners").text), "name": "Map", "target_url": "https://example.com/map", "sort_order": "0", "active": "yes"},
        follow_redirects=True,
    )
    shown = client.get("/s/gateway/banners")
    assert "https://example.com/map" in shown.text
    assert "javascript:" not in shown.text

    messages = client.get("/admin/sites/1/messages")
    queued = client.post(
        "/admin/sites/1/messages",
        data={"csrf": csrf(messages.text), "phone": "5105550100", "body": f"call {PAN}"},
        follow_redirects=True,
    )
    assert "not sent to a phone network" in queued.text
    assert "[removed]" in queued.text
    assert PAN not in queued.text

    services = client.get("/admin/sites/1/services")
    client.post(
        "/admin/sites/1/services",
        data={"csrf": csrf(services.text), "name": "Airport shuttle", "postal_codes": "94621, 94102", "details": "<p>Door to door</p>"},
        follow_redirects=True,
    )
    found = client.get("/s/gateway/services?q=94621")
    assert "Airport shuttle" in found.text
    missed = client.get("/s/gateway/services?q=00000")
    assert "Airport shuttle" not in missed.text


def test_course_is_graded_without_storing_the_password(client):
    _enable(client)
    learn = client.get("/admin/sites/1/learn")
    client.post(
        "/admin/sites/1/learn",
        data={"csrf": csrf(learn.text), "action": "course", "title": "Front desk", "summary": "<p>Welcome</p>", "publish": "yes"},
        follow_redirects=True,
    )
    learn = client.get("/admin/sites/1/learn")
    client.post(
        "/admin/sites/1/learn",
        data={"csrf": csrf(learn.text), "action": "question", "course_id": "1", "prompt": "The desk opens at noon.", "kind": "tf", "correct": "1"},
        follow_redirects=True,
    )
    learn = client.get("/admin/sites/1/learn")
    client.post(
        "/admin/sites/1/learn",
        data={
            "csrf": csrf(learn.text),
            "action": "student",
            "name": "Ada",
            "email": "ada.student@example.com",
            "password": "Student!Liquid2026",
            "course_id": "1",
        },
        follow_redirects=True,
    )
    from liquid.models import Student
    from sqlalchemy import select

    with client.app.state.session_factory() as database:
        student = database.scalar(select(Student))
        assert student.password_hash != "Student!Liquid2026"
        assert "Student!Liquid2026" not in student.password_hash
    login_page = client.get("/s/gateway/learn/login")
    client.post(
        "/s/gateway/learn/login",
        data={"csrf": csrf(login_page.text), "action": "login", "email": "ada.student@example.com", "password": "Student!Liquid2026"},
        follow_redirects=True,
    )
    quiz = client.get("/s/gateway/learn/front-desk")
    assert "The desk opens at noon." in quiz.text
    assert "correct_index" not in quiz.text
    question = quiz.text.split('name="q_', 1)[1].split('"', 1)[0]
    graded = client.post(f"/s/gateway/learn/front-desk", data={"csrf": csrf(quiz.text), f"q_{question}": "0"}, follow_redirects=True)
    assert "Score 1 of 1." in graded.text


def test_coupon_offer_and_coach_drop_card_numbers(client):
    _enable(client)
    coupons = client.get("/admin/sites/1/coupons")
    client.post(
        "/admin/sites/1/coupons",
        data={
            "csrf": csrf(coupons.text),
            "action": "coupon",
            "title": "Breakfast",
            "city": "Oakland",
            "state": "CA",
            "details": f"<p>Show card {PAN}</p>",
            "publish": "yes",
        },
        follow_redirects=True,
    )
    public = client.get("/s/gateway/coupons")
    assert "Breakfast" in public.text
    assert "[removed]" in public.text
    assert PAN not in public.text
    signup = client.get("/s/gateway/coupons/signup")
    client.post(
        "/s/gateway/coupons/signup",
        data={
            "csrf": csrf(signup.text),
            "action": "register",
            "name": "Cafe",
            "email": "cafe@example.com",
            "password": "Merchant!Liquid2026",
            "city": "Oakland",
            "state": "CA",
        },
        follow_redirects=True,
    )
    waiting = client.post(
        "/s/gateway/coupons/login",
        data={"csrf": csrf(client.get("/s/gateway/coupons/login").text), "email": "cafe@example.com", "password": "Merchant!Liquid2026"},
        follow_redirects=True,
    )
    assert "waiting for approval" in waiting.text
    client.post(
        "/admin/sites/1/coupons",
        data={"csrf": csrf(client.get("/admin/sites/1/coupons").text), "action": "approve", "id": "1"},
        follow_redirects=True,
    )
    client.post(
        "/s/gateway/coupons/login",
        data={"csrf": csrf(client.get("/s/gateway/coupons/login").text), "email": "cafe@example.com", "password": "Merchant!Liquid2026"},
        follow_redirects=False,
    )
    draft = client.post(
        "/s/gateway/coupons/desk",
        data={"csrf": csrf(client.get("/s/gateway/coupons/desk").text), "title": "Late plate", "details": "After nine"},
        follow_redirects=True,
    )
    assert "draft" in draft.text.lower()
    assert "Late plate" not in client.get("/s/gateway/coupons").text

    coaches = client.get("/admin/sites/1/coaches")
    client.post(
        "/admin/sites/1/coaches",
        data={"csrf": csrf(coaches.text), "action": "model", "name": "Harbor", "year": "2026", "price": "40", "summary": "<p>One slide</p>", "publish": "yes"},
        follow_redirects=True,
    )
    account = client.get("/s/gateway/coaches/login")
    client.post(
        "/s/gateway/coaches/login",
        data={"csrf": csrf(account.text), "action": "register", "name": "Bea", "email": "bea.coach@example.com", "password": "Coach!Liquid2026"},
        follow_redirects=True,
    )
    model = client.get("/s/gateway/coaches/harbor")
    client.post(
        f"/s/gateway/coaches/harbor",
        data={"csrf": csrf(model.text), "action": "offer", "amount": "30", "message": f"card {PAN}"},
        follow_redirects=True,
    )
    desk = client.get("/admin/sites/1/coaches")
    assert "[removed]" in desk.text
    assert PAN not in desk.text
