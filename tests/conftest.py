import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIQUID_ENV", "test")
    monkeypatch.setenv("LIQUID_SECRET_KEY", "test-secret-key-which-is-long-enough-32b")
    monkeypatch.setenv("LIQUID_DATABASE_URL", f"sqlite:///{tmp_path / 'liquid.db'}")
    monkeypatch.setenv("LIQUID_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("LIQUID_GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("LIQUID_SECRET_FILE", str(tmp_path / "secret.key"))
    monkeypatch.setenv("LIQUID_BOOTSTRAP_PASSWORD", "TestOnly!Liquid2026")
    monkeypatch.setenv("LIQUID_BOOTSTRAP_EMAIL", "builder@liquidsoftware.local")
    from liquid.config import get_settings
    from liquid.security import reset_rate_limits

    get_settings.cache_clear()
    reset_rate_limits()
    from liquid.web import create_app

    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
    get_settings.cache_clear()
    reset_rate_limits()


def csrf(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match, "form is missing a CSRF token"
    return match.group(1)


def login(client, email="builder@liquidsoftware.local", password="TestOnly!Liquid2026"):
    page = client.get("/admin/login")
    return client.post(
        "/admin/login",
        data={"csrf": csrf(page.text), "email": email, "password": password},
        follow_redirects=False,
    )
