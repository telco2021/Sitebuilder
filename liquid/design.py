"""Visual page design.

The editor can submit HTML and CSS. This module keeps the tags and style
declarations a page needs for layout, and drops scripts, event handlers, and
addresses that are not part of the site.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import bleach

from liquid.canvas import parse_canvas, render_canvas
from liquid.studio import parse_blocks, render_blocks
from liquid.textutil import FormError, sanitize_html

MAX_HTML = 150_000
MAX_CSS = 80_000

_TAGS = [
    "section",
    "article",
    "header",
    "div",
    "span",
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
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
    "figure",
    "figcaption",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]
_TAG_SET = set(_TAGS)
_STYLE_BLOCK = re.compile(r"(?is)<style\b[^>]*>(.*?)</style>")
_STYLE_OPEN = re.compile(r"(?is)<style\b[^>]*>")
_H1 = re.compile(r"(?i)<(/?)h1(\s|>)")
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_MEDIA = re.compile(r"^@media\s+\(\s*(?:max|min)-width\s*:\s*[0-9]{2,4}px\s*\)$", re.I)
_TOKEN = re.compile(
    r"\s*(?:[a-z][a-z0-9]{0,19}|\.[A-Za-z_][A-Za-z0-9_-]{0,63}|#[A-Za-z_][A-Za-z0-9_-]{0,63}|:hover|:focus|[>+~])\s*"
)
_SELECTOR_TAGS = _TAG_SET | {"h1"}
_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_VALUE = re.compile(r"^[A-Za-z0-9 #%.,()/'\"+/\-!]+$")
_URL = re.compile(r"url\(\s*([^)]+)\)", re.I)
_MEDIA_SRC = re.compile(r"/media/([0-9]{1,10})")
_BARE_IMG = re.compile(r"(?is)<img\b(?![^>]*\bsrc\s*=)[^>]*>")
_PROPS = {
    "color",
    "background",
    "background-color",
    "background-image",
    "background-position",
    "background-repeat",
    "background-size",
    "font",
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
    "line-height",
    "letter-spacing",
    "text-align",
    "text-decoration",
    "text-transform",
    "margin",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "padding",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "border",
    "border-radius",
    "border-color",
    "border-width",
    "border-style",
    "border-top",
    "border-right",
    "border-bottom",
    "border-left",
    "display",
    "flex",
    "flex-direction",
    "flex-wrap",
    "justify-content",
    "align-items",
    "align-self",
    "gap",
    "row-gap",
    "column-gap",
    "grid-template-columns",
    "grid-template-rows",
    "width",
    "height",
    "max-width",
    "min-width",
    "max-height",
    "min-height",
    "object-fit",
    "vertical-align",
    "box-shadow",
    "opacity",
    "overflow",
    "list-style",
    "list-style-type",
    "float",
    "clear",
    "z-index",
    "position",
    "top",
    "right",
    "bottom",
    "left",
}


def parse_design(html: object, css: object, media_ids: set[int] | None) -> dict:
    if not isinstance(html, str) or not isinstance(css, str):
        raise FormError("The page could not be read. Reload the editor and try again.")
    if len(html) > MAX_HTML or len(css) > MAX_CSS:
        raise FormError("This page is too large.")
    extracted, markup = _extract_styles(html)
    markup = _H1.sub(r"<\1h2\2", markup)
    markup = _prepare_inline_styles(markup, media_ids)
    clean_html = _sanitize_html(markup, media_ids)
    clean_css = sanitize_css(extracted + "\n" + css, media_ids)
    return {"version": 2, "engine": "grapes", "html": clean_html, "css": clean_css}


def render_design(document: dict) -> str:
    css = document.get("css") or ""
    html = document.get("html") or ""
    if "<" in css:
        css = ""
    style = f"<style>{css}</style>" if css else ""
    return f'{style}<div class="page-body">{html}</div>'


def published_body(blocks: str, body: str, media_ids: set[int] | None = None) -> str:
    """HTML for a public page. Design pages are checked again on the way out."""

    try:
        parsed = json.loads(blocks or "null")
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict) and parsed.get("version") == 2 and parsed.get("engine") == "grapes":
        document = parse_design(str(parsed.get("html") or ""), str(parsed.get("css") or ""), media_ids)
        return render_design(document)
    return sanitize_html(body or "")


def design_for_editor(raw: str | None, html: str, site_slug: str, media_ids: set[int]) -> dict:
    """Open a stored page in the visual editor, including pages saved by the older editor."""

    try:
        parsed = json.loads(raw or "null")
    except json.JSONDecodeError:
        parsed = None
    rendered = ""
    if isinstance(parsed, dict) and parsed.get("version") == 2 and parsed.get("engine") == "grapes":
        return parse_design(str(parsed.get("html") or ""), str(parsed.get("css") or ""), media_ids)
    if isinstance(parsed, dict) and parsed.get("version") == 1:
        try:
            rendered = render_canvas(parse_canvas(json.dumps(parsed), media_ids), site_slug)
        except FormError:
            rendered = ""
    elif isinstance(parsed, list) and parsed:
        try:
            rendered = render_blocks(parse_blocks(json.dumps(parsed), media_ids))
        except FormError:
            rendered = ""
    if not rendered:
        rendered = html or ""
    return parse_design(rendered, "", media_ids)


def sanitize_css(css: str, media_ids: set[int] | None) -> str:
    cleaned = _COMMENT.sub("", css or "")
    cleaned = cleaned.split("/*", 1)[0]
    cleaned = cleaned.replace("\x00", "")
    if len(cleaned) > MAX_CSS:
        cleaned = cleaned[:MAX_CSS]
    return _rules(cleaned, media_ids, nested=False)


def _extract_styles(html: str) -> tuple[str, str]:
    found = "\n".join(_STYLE_BLOCK.findall(html))
    without = _STYLE_BLOCK.sub("", html)
    without = _STYLE_OPEN.sub("", without)
    return found, without


def _prepare_inline_styles(html: str, media_ids: set[int] | None) -> str:
    def replace(match: re.Match[str]) -> str:
        safe = _declarations(match.group(2), media_ids).replace('"', "'")
        if not safe:
            return ""
        return f' style="{safe}"'

    prepared = re.sub(r"(?is)\sstyle\s*=\s*(['\"])(.*?)\1", replace, html)
    return re.sub(r"(?is)\sstyle\s*=\s*[^\s>]+", "", prepared)


def _sanitize_html(html: str, media_ids: set[int] | None) -> str:
    def allow(tag: str, name: str, value: str) -> bool:
        if name == "style":
            safe = _declarations(value, media_ids)
            return bool(safe) and safe == (value or "").strip()
        if name == "class":
            parts = (value or "").split()
            return bool(parts) and len(parts) <= 12 and all(_CLASS.fullmatch(part) for part in parts)
        if name == "id":
            return bool(_CLASS.fullmatch(value or ""))
        if tag == "a" and name == "href":
            return _href_ok(value)
        if tag == "a" and name == "title":
            return True
        if tag == "img" and name == "alt":
            return True
        if tag == "img" and name == "src":
            return _media_ok(value, media_ids)
        if tag == "img" and name in {"width", "height"}:
            return bool(re.fullmatch(r"[0-9]{1,4}", value or ""))
        if tag in {"td", "th"} and name in {"colspan", "rowspan"}:
            return bool(re.fullmatch(r"[1-9][0-9]?", value or ""))
        return False

    cleaned = bleach.clean(html, tags=_TAGS, attributes=allow, protocols=["http", "https", "mailto"], strip=True)
    cleaned = _BARE_IMG.sub("", cleaned)
    return _rewrite_styles(cleaned, media_ids)


def _rewrite_styles(html: str, media_ids: set[int] | None) -> str:
    """Bleach keeps a style attribute once it is allowed. Write back only the safe declarations."""

    def replace(match: re.Match[str]) -> str:
        quote = match.group(1)
        value = match.group(2)
        safe = _declarations(value, media_ids)
        if not safe:
            return ""
        return f" style={quote}{safe}{quote}"

    return re.sub(r"\sstyle=(['\"])(.*?)\1", replace, html)


def _href_ok(value: str) -> bool:
    text = (value or "").strip()
    if not text or len(text) > 300 or any(ord(character) < 32 for character in text):
        return False
    if text.startswith("#"):
        return bool(re.fullmatch(r"#[A-Za-z0-9_-]{0,64}", text))
    if text.startswith("/") and not text.startswith("//") and "\\" not in text and ".." not in text:
        return bool(re.fullmatch(r"/[A-Za-z0-9_./-]{0,240}", text))
    parsed = urlparse(text)
    if parsed.username or parsed.password:
        return False
    if parsed.scheme == "mailto":
        return bool(re.fullmatch(r"mailto:[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+", text))
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _media_ok(value: str, media_ids: set[int] | None) -> bool:
    match = _MEDIA_SRC.fullmatch((value or "").strip())
    if match is None:
        return False
    if media_ids is None:
        return True
    return int(match.group(1)) in media_ids


def _rules(css: str, media_ids: set[int] | None, nested: bool) -> str:
    output: list[str] = []
    index = 0
    length = len(css)
    while index < length:
        while index < length and css[index].isspace():
            index += 1
        if index >= length or css[index] == "}":
            break
        brace = css.find("{", index)
        semi = css.find(";", index)
        if brace == -1 or (semi != -1 and semi < brace):
            index = length if semi == -1 else semi + 1
            continue
        selector = " ".join(css[index:brace].split())
        body, index = _brace_body(css, brace)
        if selector.lower().startswith("@media"):
            if nested or _MEDIA.fullmatch(selector) is None:
                continue
            inner = _rules(body, media_ids, nested=True)
            if inner:
                output.append(f"{selector.lower()}{{{inner}}}")
            continue
        if not _selector_ok(selector):
            continue
        declarations = _declarations(body, media_ids)
        if declarations:
            output.append(f"{selector}{{{declarations}}}")
    return "".join(output)


def _brace_body(css: str, open_at: int) -> tuple[str, int]:
    depth = 1
    index = open_at + 1
    start = index
    while index < len(css) and depth:
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[start:index], index + 1
        index += 1
    return "", len(css)


def _selector_ok(selector: str) -> bool:
    if not selector or len(selector) > 300 or "\\" in selector or "<" in selector:
        return False
    for part in selector.split(","):
        part = part.strip()
        if not part:
            return False
        position = 0
        saw = False
        while position < len(part):
            match = _TOKEN.match(part, position)
            if match is None:
                return False
            token = match.group(0).strip()
            if re.fullmatch(r"[a-z][a-z0-9]*", token) and token not in _SELECTOR_TAGS:
                return False
            position = match.end()
            saw = True
        if not saw or position != len(part):
            return False
    return True


def _declarations(body: str, media_ids: set[int] | None) -> str:
    if "{" in body or "<" in body:
        return ""
    kept: list[str] = []
    for chunk in body.split(";"):
        if ":" not in chunk:
            continue
        prop, value = chunk.split(":", 1)
        prop = prop.strip().lower()
        value = " ".join(value.strip().split())
        if prop not in _PROPS or not value or len(value) > 300:
            continue
        if not _value_ok(value, media_ids):
            continue
        kept.append(f"{prop}:{value}")
        if len(kept) >= 40:
            break
    return ";".join(kept)


def _value_ok(value: str, media_ids: set[int] | None) -> bool:
    lowered = value.lower()
    if any(token in lowered for token in ("expression", "javascript", "vbscript", "binding", "behavior", "@", "\\")):
        return False
    if not _VALUE.fullmatch(value):
        return False
    for raw in _URL.findall(value):
        inner = raw.strip().strip("\"'")
        if not _media_ok(inner, media_ids):
            return False
    return True
