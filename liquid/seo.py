"""Search fields that belong on every page: the keyword address, the description, and the files a crawler reads."""

from __future__ import annotations

import re
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from liquid.constants import RESERVED_PAGE_SLUGS
from liquid.models import Page, PageAlias
from liquid.textutil import FormError, one_line, slugify

PAGE_SLUG_LIMIT = 80
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")

FEATURE_PATHS = (
    ("search", "search"),
    ("news", "news"),
    ("banners", "banners"),
    ("calendar", "calendar"),
    ("services", "services"),
    ("gallery", "gallery"),
    ("lms", "learn"),
    ("rv", "coaches"),
    ("coupons", "coupons"),
    ("hotel", "hotel"),
)


def keyword_slug(value: str, fallback: str = "") -> str:
    return slugify(value, fallback, limit=PAGE_SLUG_LIMIT)


def public_host(value: object) -> str:
    """A domain such as www.example.com. A scheme or a trailing path is removed."""

    text = one_line(value, 255).lower().strip()
    if not text:
        return ""
    if "@" in text or "\\" in text or " " in text:
        raise FormError("Enter the domain only, such as www.example.com.")
    text = re.sub(r"^https?://", "", text)
    text = text.split("/", 1)[0].split("?", 1)[0].strip().strip(".")
    if ":" in text or not _HOST.fullmatch(text):
        raise FormError("Enter the domain only, such as www.example.com.")
    return text


def host_or_blank(value: object) -> str:
    try:
        return public_host(value)
    except FormError:
        return ""


def assign_keyword_slug(db: Session, site_id: int, page: Page | None, requested: str, title: str) -> str:
    """Set the public address. A published address that changes keeps a permanent redirect."""

    new_slug = keyword_slug(requested or title, "")
    if not new_slug:
        raise FormError("Enter a keyword address, such as software-development.")
    if new_slug in RESERVED_PAGE_SLUGS:
        raise FormError("That address is reserved.")
    if page is not None and page.slug == "home" and new_slug != "home":
        raise FormError("The front page stays at the site root. Add a new page when you want a keyword address.")
    taken = db.scalar(select(Page).where(Page.site_id == site_id, Page.slug == new_slug))
    if taken is not None and (page is None or taken.id != page.id):
        raise FormError("Another page already uses that address.")
    alias = db.scalar(select(PageAlias).where(PageAlias.site_id == site_id, PageAlias.slug == new_slug))
    if alias is not None and (page is None or alias.page_id != page.id):
        raise FormError("That address still redirects to another page. Choose a different keyword address.")
    if page is not None and page.is_published and page.slug not in {"", "home", new_slug}:
        previous = page.slug
        holder = db.scalar(select(PageAlias).where(PageAlias.site_id == site_id, PageAlias.slug == previous))
        if holder is not None and holder.page_id != page.id:
            raise FormError("The previous address is already a redirect.")
        if holder is None:
            db.add(PageAlias(site_id=site_id, page_id=page.id, slug=previous))
    if alias is not None and page is not None and alias.page_id == page.id:
        db.delete(alias)
    if page is not None:
        page.slug = new_slug
    return new_slug


def join_path(root: str, slug: str) -> str:
    if slug in {"", "home"}:
        return root or "/"
    if root:
        return f"{root}/{slug}"
    return f"/{slug}"


def listing_paths(pages: list[dict], features: dict, root: str) -> list[tuple[str, str]]:
    rows = [(join_path(root, page["slug"]), page.get("updated") or "") for page in pages]
    for key, slug in FEATURE_PATHS:
        if features.get(key):
            rows.append((join_path(root, slug), ""))
    return rows


def absolute_url(origin: str, path: str) -> str:
    base = origin.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def canonical_url(domain: object, path: str) -> str:
    host = host_or_blank(domain)
    if not host:
        return ""
    return absolute_url(f"https://{host}", path)


def sitemap_xml(urls: list[tuple[str, str]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in urls:
        item = f"<url><loc>{escape(loc)}</loc>"
        if lastmod:
            item += f"<lastmod>{escape(lastmod)}</lastmod>"
        item += "</url>"
        lines.append(item)
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt(sitemap_url: str, *, index: bool) -> str:
    if not index:
        return "User-agent: *\nDisallow: /\n"
    lines = ["User-agent: *", "Allow: /"]
    if sitemap_url:
        lines.append(f"Sitemap: {sitemap_url}")
    return "\n".join(lines) + "\n"


def origin_for(domain: object, fallback: str) -> str:
    host = host_or_blank(domain)
    if host:
        return f"https://{host}"
    return fallback.rstrip("/")
