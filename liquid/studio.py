"""Page studio: a block design that renders to the same safe HTML the site already publishes."""

from __future__ import annotations

import json

from markupsafe import escape

from liquid.textutil import FormError, http_url, one_line, parse_email, plain, sanitize_html

MAX_BLOCKS = 40
_LEVELS = {2, 3}


def editor_blocks(raw: str | None) -> list[dict]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict) and isinstance(item.get("type"), str)]


def parse_blocks(raw: object, media_ids: set[int]) -> list[dict]:
    if not isinstance(raw, str):
        raise FormError("The design could not be read. Open Design and save again.")
    if len(raw) > 100_000:
        raise FormError("This design is too large.")
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise FormError("The design could not be read. Open Design and save again.") from exc
    if not isinstance(parsed, list):
        raise FormError("The design could not be read. Open Design and save again.")
    if len(parsed) > MAX_BLOCKS:
        raise FormError(f"A page can hold {MAX_BLOCKS} blocks.")
    return [_block(item, media_ids) for item in parsed]


def render_blocks(blocks: list[dict]) -> str:
    parts = [html for block in blocks if (html := _render(block))]
    return "".join(parts)


def _block(item: object, media_ids: set[int]) -> dict:
    if not isinstance(item, dict):
        raise FormError("A block in the design is not valid.")
    kind = item.get("type")
    if kind == "heading":
        level = item.get("level")
        try:
            level = int(level)
        except (TypeError, ValueError):
            level = 2
        if level not in _LEVELS:
            level = 2
        return {"type": "heading", "text": one_line(item.get("text"), 200), "level": level}
    if kind == "text":
        return {"type": "text", "text": plain(item.get("text"), 4000)}
    if kind == "image":
        try:
            media_id = int(item.get("media_id") or 0)
        except (TypeError, ValueError):
            media_id = 0
        if media_id not in media_ids:
            media_id = 0
        return {"type": "image", "media_id": media_id, "alt": one_line(item.get("alt"), 180)}
    if kind == "button":
        return {"type": "button", "label": one_line(item.get("label"), 80), "href": _href(item.get("href"))}
    if kind == "quote":
        return {"type": "quote", "text": plain(item.get("text"), 500), "cite": one_line(item.get("cite"), 120)}
    if kind == "list":
        items = item.get("items")
        if isinstance(items, str):
            rows = items.split("\n")
        elif isinstance(items, list):
            rows = items
        else:
            rows = []
        cleaned = [one_line(row, 200) for row in rows if one_line(row, 200)]
        return {"type": "list", "items": cleaned[:20], "ordered": item.get("ordered") is True}
    if kind == "columns":
        return {"type": "columns", "left": plain(item.get("left"), 1500), "right": plain(item.get("right"), 1500)}
    if kind == "divider":
        return {"type": "divider"}
    if kind == "html":
        return {"type": "html", "html": sanitize_html(plain(item.get("html"), 20000))}
    raise FormError("A block in the design is not a known type.")


def _href(value: object) -> str:
    text = one_line(value, 300)
    if text.startswith("/") and not text.startswith("//") and "\\" not in text and ":" not in text:
        return text
    if text.startswith("mailto:"):
        try:
            return "mailto:" + parse_email(text[7:])
        except FormError:
            return ""
    try:
        return http_url(text)
    except FormError:
        return ""


def _paragraphs(value: str) -> str:
    chunks = [chunk.strip() for chunk in value.split("\n\n")]
    parts = []
    for chunk in chunks:
        if not chunk:
            continue
        lines = "<br>".join(str(escape(line)) for line in chunk.split("\n"))
        parts.append(f"<p>{lines}</p>")
    return "".join(parts)


def _render(block: dict) -> str:
    kind = block.get("type")
    if kind == "heading":
        text = one_line(block.get("text"), 200)
        if not text:
            return ""
        tag = "h3" if block.get("level") == 3 else "h2"
        return f"<{tag}>{escape(text)}</{tag}>"
    if kind == "text":
        return _paragraphs(plain(block.get("text"), 4000))
    if kind == "image":
        media_id = block.get("media_id") or 0
        if not media_id:
            return ""
        alt = escape(one_line(block.get("alt"), 180))
        return f'<p><img src="/media/{int(media_id)}" alt="{alt}"></p>'
    if kind == "button":
        label = one_line(block.get("label"), 80)
        href = _href(block.get("href"))
        if not label or not href:
            return ""
        return f'<p><a href="{escape(href)}">{escape(label)}</a></p>'
    if kind == "quote":
        text = plain(block.get("text"), 500).strip()
        if not text:
            return ""
        cite = one_line(block.get("cite"), 120)
        body = f"<blockquote><p>{escape(text)}</p>"
        if cite:
            body += f"<p><em>{escape(cite)}</em></p>"
        return body + "</blockquote>"
    if kind == "list":
        items = block.get("items") or []
        if not items:
            return ""
        tag = "ol" if block.get("ordered") else "ul"
        rows = "".join(f"<li>{escape(one_line(item, 200))}</li>" for item in items)
        return f"<{tag}>{rows}</{tag}>"
    if kind == "columns":
        left = _paragraphs(plain(block.get("left"), 1500)) or "<p></p>"
        right = _paragraphs(plain(block.get("right"), 1500)) or "<p></p>"
        return f"<table><tr><td>{left}</td><td>{right}</td></tr></table>"
    if kind == "divider":
        return "<hr>"
    if kind == "html":
        return sanitize_html(str(block.get("html") or ""))
    return ""
