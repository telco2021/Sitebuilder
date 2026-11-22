"""Plain-text, slug, email, and HTML sanitation."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

import bleach
from email_validator import EmailNotValidError, validate_email

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SLUG = re.compile(r"[^a-z0-9]+")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_SCRIPT = re.compile(r"(?is)<(script|style|iframe|object|embed)\b[^>]*>.*?</\1>")
_SCRIPT_OPEN = re.compile(r"(?is)<(script|style|iframe|object|embed)\b[^>]*>")

_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "a",
    "h2",
    "h3",
    "h4",
    "blockquote",
    "img",
    "hr",
    "code",
    "pre",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]
_ATTRS = {
    "a": ["href", "title"],
    "img": ["src", "alt"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
_SAFE_CLASS = {
    "align-left",
    "align-center",
    "align-right",
    "tone-accent",
    "spacer",
    "size-small",
    "size-medium",
    "size-large",
    "columns",
}
_CLASS_TAGS = {"p", "h2", "h3", "ul", "ol", "table", "hr"}


class FormError(Exception):
    """A validation error safe to show to the person who submitted the form."""


def plain(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = _CONTROL.sub("", value).replace("\r\n", "\n").replace("\r", "\n").strip()
    return cleaned[:limit]


def one_line(value: object, limit: int) -> str:
    return plain(value, limit).replace("\n", " ").strip()


def slugify(value: str, fallback: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG.sub("-", normalized.lower()).strip("-")
    slug = slug[:60].strip("-")
    return slug or fallback


def hex_color(value: object, default: str) -> str:
    text = one_line(value, 7)
    if _HEX.fullmatch(text):
        return text.lower()
    return default


def _allow_attr(tag: str, name: str, value: str) -> bool:
    if name in _ATTRS.get(tag, []):
        return True
    if name != "class" or tag not in _CLASS_TAGS:
        return False
    parts = (value or "").split()
    return bool(parts) and all(part in _SAFE_CLASS for part in parts)


def sanitize_html(value: str) -> str:
    without_scripts = _SCRIPT.sub("", value)
    without_scripts = _SCRIPT_OPEN.sub("", without_scripts)
    return bleach.clean(
        without_scripts,
        tags=_TAGS,
        attributes=_allow_attr,
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def strip_tags(value: str) -> str:
    return bleach.clean(value or "", tags=[], strip=True)


_PAN_LIKE = re.compile(r"(?:\d[ -]?){13,19}")


def redact_secrets(value: str) -> str:
    """Drop sequences that look like card numbers from anything we store."""

    return _PAN_LIKE.sub("[removed]", value)


_EMAIL = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}")
_OFFLINE_TLDS = (".local", ".localhost", ".test", ".example", ".invalid")


def http_url(value: object) -> str:
    text = one_line(value, 300)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise FormError("Use an http or https link.")
    return text


def parse_email(value: object) -> str:
    text = one_line(value, 255).lower()
    if not _EMAIL.fullmatch(text):
        raise FormError("Enter a valid email.")
    try:
        validate_email(text, check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        if not text.endswith(_OFFLINE_TLDS):
            raise FormError("Enter a valid email.") from exc
    return text
