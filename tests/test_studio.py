import json

from liquid.studio import parse_blocks, render_blocks
from liquid.textutil import sanitize_html
from tests.conftest import csrf, login


def test_design_blocks_render_to_safe_html():
    blocks = parse_blocks(
        json.dumps(
            [
                {"type": "heading", "text": "<script>alert(1)</script>", "level": 2},
                {"type": "text", "text": "A paragraph"},
                {"type": "button", "label": "Go", "href": "javascript:alert(1)"},
                {"type": "html", "html": "<script>alert(1)</script><p onclick=\"x\">Kept</p>"},
            ]
        ),
        set(),
    )
    html = sanitize_html(render_blocks(blocks))
    assert "<script" not in html.lower()
    assert "javascript:" not in html.lower()
    assert "Kept" in html
    assert "A paragraph" in html
    assert "&lt;script&gt;" in html


def test_page_studio_publishes_a_designed_page(client):
    assert login(client).headers["location"] == "/admin"
    home = client.get("/")
    assert "script-src 'none'" in home.headers["content-security-policy"]

    form = client.get("/admin/sites/1/pages/new")
    assert form.status_code == 200
    assert "Page studio" in form.text
    assert 'src="/static/studio.js"' in form.text
    assert "script-src 'self'" in form.headers["content-security-policy"]
    assert "script-src 'none'" not in form.headers["content-security-policy"]

    existing = client.get("/admin/sites/1/pages/1")
    assert "Stay directly with the hotel" in existing.text
    assert 'data-studio-tab="html"' in existing.text

    saved = client.post(
        "/admin/sites/1/pages",
        data={
            "csrf": csrf(form.text),
            "action": "publish",
            "studio_mode": "design",
            "title": "Designed",
            "slug": "designed",
            "nav_order": "7",
            "show_in_nav": "yes",
            "blocks": json.dumps(
                [
                    {"type": "heading", "text": "Welcome aboard", "level": 2},
                    {"type": "list", "items": ["Pages", "Forms"], "ordered": False},
                    {"type": "button", "label": "Book", "href": "/hotel"},
                ]
            ),
            "body": "<script>alert(1)</script>",
            "keywords": "design",
            "description": "A designed page",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    public = client.get("/s/gateway/designed")
    assert public.status_code == 200
    assert "Welcome aboard" in public.text
    assert "<li>Pages</li>" in public.text
    assert 'href="/hotel"' in public.text
    assert "<script" not in public.text.lower()
