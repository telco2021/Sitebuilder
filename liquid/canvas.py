"""Drag-and-drop page document.

The editor stores a JSON tree. Publishing renders that tree to the same safe
HTML the public site already shows.
"""

from __future__ import annotations

import json
import re

from markupsafe import escape

from liquid.studio import _href, _paragraphs
from liquid.textutil import FormError, one_line, plain, sanitize_html, slugify

MAX_NODES = 40
_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_ALIGN = {"left", "center", "right"}
_TONE = {"default", "accent"}
_SPACER = {"small", "medium", "large"}
_TYPES = {"heading", "text", "image", "button", "list", "columns", "spacer", "form", "html"}


def parse_canvas(raw: object, media_ids: set[int]) -> dict:
    if not isinstance(raw, str):
        raise FormError("The page could not be read. Reload the editor and try again.")
    if len(raw) > 200_000:
        raise FormError("This page is too large.")
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise FormError("The page could not be read. Reload the editor and try again.") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("content"), list):
        raise FormError("The page could not be read. Reload the editor and try again.")
    seen: set[str] = set()
    content = [_node(item, media_ids, seen, nested=False) for item in parsed["content"]]
    if len(seen) > MAX_NODES:
        raise FormError(f"A page can hold {MAX_NODES} parts.")
    return {"version": 1, "content": content}


def render_canvas(document: dict, site_slug: str) -> str:
    slug = slugify(site_slug, "site")
    return "".join(_render(node, slug) for node in document.get("content") or [])


def document_for_editor(raw: str | None, html: str, media_ids: set[int]) -> dict:
    """Open a stored page in the editor, including pages saved before this editor."""

    try:
        parsed = json.loads(raw or "null")
    except json.JSONDecodeError:
        parsed = None
    candidate: dict | None = None
    if isinstance(parsed, dict) and parsed.get("version") == 1 and isinstance(parsed.get("content"), list):
        candidate = parsed
    elif isinstance(parsed, list) and parsed:
        candidate = {"version": 1, "content": [_from_old(item, index) for index, item in enumerate(parsed) if isinstance(item, dict)]}
        candidate["content"] = [item for item in candidate["content"] if item]
    if candidate is None and (html or "").strip():
        candidate = {"version": 1, "content": [{"id": "legacy", "type": "html", "props": {"html": html}}]}
    if candidate is None:
        candidate = {"version": 1, "content": []}
    try:
        return parse_canvas(json.dumps(candidate), media_ids)
    except FormError:
        if not (html or "").strip():
            return {"version": 1, "content": []}
        fallback = {"version": 1, "content": [{"id": "legacy", "type": "html", "props": {"html": html}}]}
        return parse_canvas(json.dumps(fallback), media_ids)


def _from_old(item: dict, index: int) -> dict | None:
    kind = item.get("type")
    node_id = f"old{index}"
    if kind == "heading":
        return {"id": node_id, "type": "heading", "props": {"text": item.get("text") or "", "level": item.get("level") or 2, "align": "left", "tone": "default"}}
    if kind == "text" or kind == "quote":
        return {"id": node_id, "type": "text", "props": {"text": item.get("text") or "", "align": "left", "tone": "default"}}
    if kind == "image":
        return {"id": node_id, "type": "image", "props": {"media_id": item.get("media_id") or 0, "alt": item.get("alt") or "", "align": "left"}}
    if kind == "button":
        return {"id": node_id, "type": "button", "props": {"label": item.get("label") or "", "href": item.get("href") or "", "align": "left"}}
    if kind == "list":
        return {"id": node_id, "type": "list", "props": {"items": item.get("items") or [], "ordered": item.get("ordered") is True, "align": "left"}}
    if kind == "columns":
        return {
            "id": node_id,
            "type": "columns",
            "props": {},
            "left": [{"id": f"{node_id}l", "type": "text", "props": {"text": item.get("left") or "", "align": "left", "tone": "default"}}],
            "right": [{"id": f"{node_id}r", "type": "text", "props": {"text": item.get("right") or "", "align": "left", "tone": "default"}}],
        }
    if kind == "divider":
        return {"id": node_id, "type": "spacer", "props": {"size": "medium"}}
    if kind == "html":
        return {"id": node_id, "type": "html", "props": {"html": item.get("html") or ""}}
    return None


def _node(item: object, media_ids: set[int], seen: set[str], nested: bool) -> dict:
    if not isinstance(item, dict):
        raise FormError("A part on the page is not valid.")
    kind = item.get("type")
    if kind not in _TYPES:
        raise FormError("A part on the page is not a known type.")
    if kind == "columns" and nested:
        raise FormError("Columns cannot sit inside columns.")
    node_id = item.get("id")
    if not isinstance(node_id, str) or not _ID.fullmatch(node_id):
        raise FormError("A part on the page is not valid.")
    if node_id in seen:
        raise FormError("A part on the page is repeated.")
    seen.add(node_id)
    props = item.get("props") if isinstance(item.get("props"), dict) else {}
    if kind == "heading":
        level = props.get("level")
        try:
            level = int(level)
        except (TypeError, ValueError):
            level = 2
        return {"id": node_id, "type": "heading", "props": {"text": one_line(props.get("text"), 200), "level": 3 if level == 3 else 2, "align": _choice(props.get("align"), _ALIGN, "left"), "tone": _choice(props.get("tone"), _TONE, "default")}}
    if kind == "text":
        return {"id": node_id, "type": "text", "props": {"text": plain(props.get("text"), 4000), "align": _choice(props.get("align"), _ALIGN, "left"), "tone": _choice(props.get("tone"), _TONE, "default")}}
    if kind == "image":
        try:
            media_id = int(props.get("media_id") or 0)
        except (TypeError, ValueError):
            media_id = 0
        if media_id not in media_ids:
            media_id = 0
        return {"id": node_id, "type": "image", "props": {"media_id": media_id, "alt": one_line(props.get("alt"), 180), "align": _choice(props.get("align"), _ALIGN, "left")}}
    if kind == "button":
        return {"id": node_id, "type": "button", "props": {"label": one_line(props.get("label"), 80), "href": _href(props.get("href")), "align": _choice(props.get("align"), _ALIGN, "left")}}
    if kind == "list":
        rows = props.get("items")
        if isinstance(rows, str):
            rows = rows.split("\n")
        elif not isinstance(rows, list):
            rows = []
        cleaned = [one_line(row, 200) for row in rows if one_line(row, 200)]
        return {"id": node_id, "type": "list", "props": {"items": cleaned[:20], "ordered": props.get("ordered") is True, "align": _choice(props.get("align"), _ALIGN, "left")}}
    if kind == "spacer":
        return {"id": node_id, "type": "spacer", "props": {"size": _choice(props.get("size"), _SPACER, "medium")}}
    if kind == "form":
        return {"id": node_id, "type": "form", "props": {"intro": one_line(props.get("intro"), 200), "form_slug": slugify(one_line(props.get("form_slug"), 60) or "contact", "contact"), "align": _choice(props.get("align"), _ALIGN, "left")}}
    if kind == "html":
        return {"id": node_id, "type": "html", "props": {"html": sanitize_html(plain(props.get("html"), 20000))}}
    left = item.get("left") if isinstance(item.get("left"), list) else []
    right = item.get("right") if isinstance(item.get("right"), list) else []
    return {
        "id": node_id,
        "type": "columns",
        "props": {},
        "left": [_node(child, media_ids, seen, nested=True) for child in left],
        "right": [_node(child, media_ids, seen, nested=True) for child in right],
    }


def _choice(value: object, allowed: set[str], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def _classes(props: dict, extra: str = "") -> str:
    names = [extra] if extra else []
    align = props.get("align")
    if align in {"center", "right"}:
        names.append(f"align-{align}")
    if props.get("tone") == "accent":
        names.append("tone-accent")
    return f' class="{" ".join(names)}"' if names else ""


def _render(node: dict, site_slug: str) -> str:
    kind = node.get("type")
    props = node.get("props") or {}
    if kind == "heading":
        text = one_line(props.get("text"), 200)
        if not text:
            return ""
        tag = "h3" if props.get("level") == 3 else "h2"
        return f"<{tag}{_classes(props)}>{escape(text)}</{tag}>"
    if kind == "text":
        body = _paragraphs(plain(props.get("text"), 4000))
        css = _classes(props)
        if css:
            body = body.replace("<p>", f"<p{css}>")
        return body
    if kind == "image":
        media_id = props.get("media_id") or 0
        if not media_id:
            return ""
        alt = escape(one_line(props.get("alt"), 180))
        return f"<p{_classes(props)}><img src=\"/media/{int(media_id)}\" alt=\"{alt}\"></p>"
    if kind == "button":
        label = one_line(props.get("label"), 80)
        href = _href(props.get("href"))
        if not label or not href:
            return ""
        return f"<p{_classes(props)}><a href=\"{escape(href)}\">{escape(label)}</a></p>"
    if kind == "list":
        items = props.get("items") or []
        if not items:
            return ""
        tag = "ol" if props.get("ordered") else "ul"
        rows = "".join(f"<li>{escape(one_line(item, 200))}</li>" for item in items)
        return f"<{tag}{_classes(props)}>{rows}</{tag}>"
    if kind == "columns":
        left = "".join(_render(child, site_slug) for child in node.get("left") or []) or "<p></p>"
        right = "".join(_render(child, site_slug) for child in node.get("right") or []) or "<p></p>"
        return f'<table class="columns"><tr><td>{left}</td><td>{right}</td></tr></table>'
    if kind == "spacer":
        size = _choice(props.get("size"), _SPACER, "medium")
        return f'<hr class="spacer size-{size}">'
    if kind == "form":
        intro = one_line(props.get("intro"), 200)
        form_slug = slugify(one_line(props.get("form_slug"), 60) or "contact", "contact")
        href = f"/s/{site_slug}/forms/{form_slug}"
        lead = f"<p{_classes(props)}>{escape(intro)}</p>" if intro else ""
        return lead + f"<p{_classes(props)}><a href=\"{href}\">Send a message</a></p>"
    if kind == "html":
        return sanitize_html(str(props.get("html") or ""))
    return ""
