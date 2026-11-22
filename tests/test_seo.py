import importlib.util
import json

from tests.conftest import csrf, login


def test_keyword_address_redirects_and_is_in_the_sitemap(client):
    assert login(client).status_code == 303
    form = client.get("/admin/sites/1/pages/new")
    saved = client.post(
        "/admin/sites/1/pages",
        data={
            "csrf": csrf(form.text),
            "action": "publish",
            "studio_mode": "grapes",
            "title": "Software development",
            "slug": "Software Development",
            "description": "Custom software development for operators who want one site.",
            "keywords": "software development",
            "nav_order": "4",
            "show_in_nav": "yes",
            "design_html": '<section class="hero"><h2>Software development</h2><p>Build it once.</p><img src="/media/99" alt="x"><a href="javascript:alert(1)">no</a></section>',
            "design_css": "section.hero{padding:24px}h2{font-size:40px}",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    public = client.get("/s/gateway/software-development")
    assert public.status_code == 200
    assert "Build it once." in public.text
    assert "javascript" not in public.text.lower()
    assert "/media/99" not in public.text
    assert 'content="Custom software development for operators who want one site."' in public.text
    assert 'rel="canonical" href="https://gateway.example/software-development"' in public.text
    assert "noindex, nofollow" in public.text
    sitemap = client.get("/s/gateway/sitemap.xml")
    assert "/s/gateway/software-development" in sitemap.text
    robots = client.get("/s/gateway/robots.txt")
    assert "Disallow: /" in robots.text

    edit = client.get(saved.headers["location"])
    renamed = client.post(
        saved.headers["location"],
        data={
            "csrf": csrf(edit.text),
            "action": "publish",
            "studio_mode": "grapes",
            "title": "Software development",
            "slug": "custom-software-development",
            "description": "Custom software development for operators who want one site.",
            "keywords": "custom software development",
            "nav_order": "4",
            "show_in_nav": "yes",
            "design_html": "<section><h2>Software development</h2><p>Build it once.</p></section>",
            "design_css": "",
        },
        follow_redirects=False,
    )
    assert renamed.status_code == 303
    old = client.get("/s/gateway/software-development", follow_redirects=False)
    assert old.status_code == 301
    assert old.headers["location"] == "/s/gateway/custom-software-development"
    assert client.get("/s/gateway/custom-software-development").status_code == 200

    home = client.get("/admin/sites/1/pages/1")
    locked = client.post(
        "/admin/sites/1/pages/1",
        data={
            "csrf": csrf(home.text),
            "action": "save",
            "studio_mode": "grapes",
            "title": "Welcome",
            "slug": "software-development",
            "description": "Book a room directly with Gateway Hotel.",
            "keywords": "Gateway Hotel, reservations",
            "nav_order": "0",
            "show_in_nav": "yes",
            "design_html": "<p>Stay</p>",
            "design_css": "",
        },
        follow_redirects=True,
    )
    assert "front page stays at the site root" in locked.text
    assert client.get("/s/gateway").status_code == 200

    generate = client.get("/admin/sites/1/generate")
    client.post("/admin/sites/1/generate", data={"csrf": csrf(generate.text)}, follow_redirects=True)
    folder = client.app.state.settings.generated_dir
    from pathlib import Path

    app_path = Path(folder) / "gateway" / "app.py"
    spec = importlib.util.spec_from_file_location("generated_keyword_site", app_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from fastapi.testclient import TestClient

    generated = TestClient(module.app)
    moved = generated.get("/software-development", follow_redirects=False)
    assert moved.status_code == 301
    assert moved.headers["location"] == "/custom-software-development"
    page = generated.get("/custom-software-development")
    assert page.status_code == 200
    assert "Build it once." in page.text
    assert "script-src 'none'" in page.headers["content-security-policy"]
    assert "unsafe-eval" not in page.headers["content-security-policy"]
    assert page.headers["permissions-policy"].startswith("camera=()")
    assert "index, follow" in page.text
    assert 'rel="canonical" href="https://gateway.example/custom-software-development"' in page.text
    assert "https://gateway.example/custom-software-development" in generated.get("/sitemap.xml").text
    bundle = json.loads((Path(folder) / "gateway" / "site_bundle.json").read_text(encoding="utf-8"))
    assert bundle["redirects"]["software-development"] == "custom-software-development"
