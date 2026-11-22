import re

from liquid.guide import catalog_gaps
from tests.conftest import login


def test_every_feature_has_a_guide():
    assert catalog_gaps() == []


def test_help_opens_from_the_feature_and_explains_the_steps(client):
    assert login(client).headers["location"] == "/admin"
    index = client.get("/admin/guide")
    assert index.status_code == 200
    assert "How to use Sitebuilder" in index.text
    assert 'href="/admin/guide/gallery"' in index.text

    gallery = client.get("/admin/guide/gallery")
    assert gallery.status_code == 200
    assert "Create album" in gallery.text
    assert "password" in gallery.text.lower()
    assert client.get("/admin/guide/missing-feature").status_code == 404

    new_site = client.get("/admin/sites/new")
    assert 'href="/admin/guide/new-site"' in new_site.text
    assert 'href="/admin/guide/hotel"' in new_site.text

    home = client.get("/admin")
    assert 'href="/admin/guide/sites"' in home.text
    pages = re.search(r'href="(/admin/sites/\d+/pages)"', home.text)
    assert pages
    assert 'href="/admin/guide/pages"' in client.get(pages.group(1)).text


def test_guide_requires_sign_in(client):
    assert client.get("/admin/guide", follow_redirects=False).status_code == 303
