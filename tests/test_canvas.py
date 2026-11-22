import json

from liquid.canvas import parse_canvas, render_canvas
from liquid.textutil import sanitize_html
from tests.conftest import csrf, login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_canvas_renders_safe_html_and_drops_unknown_pictures():
    document = parse_canvas(
        json.dumps(
            {
                "version": 1,
                "content": [
                    {"id": "h", "type": "heading", "props": {"text": "<script>alert(1)</script>", "level": 2, "align": "center", "tone": "accent"}},
                    {"id": "b", "type": "button", "props": {"label": "Go", "href": "javascript:alert(1)", "align": "left"}},
                    {"id": "i", "type": "image", "props": {"media_id": 99, "alt": "missing", "align": "left"}},
                    {"id": "s", "type": "spacer", "props": {"size": "large"}},
                ],
            }
        ),
        set(),
    )
    html = sanitize_html(render_canvas(document, "gateway"))
    assert "<script" not in html.lower()
    assert "javascript:" not in html.lower()
    assert "align-center" in html
    assert "tone-accent" in html
    assert "/media/99" not in html
    assert "size-large" in html
    assert 'onclick' not in html


def test_page_editor_publishes_dragged_parts(client):
    assert login(client).headers["location"] == "/admin"
    form = client.get("/admin/sites/1/pages/new")
    saved = client.post(
        "/admin/sites/1/pages",
        data={
            "csrf": csrf(form.text),
            "action": "publish",
            "studio_mode": "canvas",
            "title": "Canvas page",
            "slug": "canvas-page",
            "nav_order": "3",
            "show_in_nav": "yes",
            "keywords": "canvas",
            "description": "A page made by dragging parts",
            "blocks": json.dumps(
                {
                    "version": 1,
                    "content": [
                        {"id": "h1", "type": "heading", "props": {"text": "Dragged heading", "level": 2, "align": "left", "tone": "default"}},
                        {"id": "p1", "type": "text", "props": {"text": "A paragraph on the page.", "align": "left", "tone": "default"}},
                        {"id": "c1", "type": "columns", "props": {}, "left": [{"id": "cl", "type": "text", "props": {"text": "Left side", "align": "left", "tone": "default"}}], "right": []},
                    ],
                }
            ),
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    public = client.get("/s/gateway/canvas-page")
    assert public.status_code == 200
    assert "Dragged heading" in public.text
    assert "A paragraph on the page." in public.text
    assert "Left side" in public.text
    assert 'content="A page made by dragging parts"' in public.text


def test_editor_upload_returns_the_picture(client):
    assert login(client).headers["location"] == "/admin"
    form = client.get("/admin/sites/1/pages/new")
    uploaded = client.post(
        "/admin/sites/1/media",
        data={"csrf": csrf(form.text)},
        files={"upload": ("room.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["url"] == f"/media/{body['id']}"
    assert client.get(body["url"]).status_code == 200
