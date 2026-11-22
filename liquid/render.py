"""Template rendering."""

from __future__ import annotations

from pathlib import Path

from markupsafe import Markup
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

from liquid.guide import article_for_path, guide_slug_for_feature
from liquid.models import Site
from liquid.textutil import hex_color

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _money(cents: int, currency: str = "USD") -> str:
    sign = "-" if cents < 0 else ""
    amount = abs(int(cents))
    return f"{sign}{amount // 100:,}.{amount % 100:02d} {currency}"


TEMPLATES.env.filters["money"] = _money
TEMPLATES.env.globals["guide_slug_for_feature"] = guide_slug_for_feature


def flash(request: Request, level: str, message: str) -> None:
    request.state.session["flash"] = {"level": level, "message": message}


def redirect(url: str) -> RedirectResponse:
    if not url.startswith("/") or url.startswith("//"):
        url = "/"
    return RedirectResponse(url, status_code=303)


def render(request: Request, name: str, status: int = 200, **context):
    context.setdefault("csrf", request.state.session.get("csrf", ""))
    context.setdefault("flash", request.state.session.pop("flash", None))
    context.setdefault("user", getattr(request.state, "user", None))
    context.setdefault("guide", article_for_path(request.url.path))
    return TEMPLATES.TemplateResponse(request, name, context, status_code=status)


def theme_style(site: Site) -> Markup:
    pairs = {
        "--ink": hex_color(site.color_ink, "#1a1814"),
        "--paper": hex_color(site.color_paper, "#fbf6ee"),
        "--accent": hex_color(site.color_accent, "#8c3d2f"),
        "--header": hex_color(site.color_header, "#24352c"),
        "--text": hex_color(site.color_text, "#241f1a"),
    }
    css = "; ".join(f"{name}: {value}" for name, value in pairs.items())
    return Markup(css)
