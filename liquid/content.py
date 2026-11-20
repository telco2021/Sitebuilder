"""Safe placement of published news inside a page."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from liquid.models import NewsPost, Site
from liquid.textutil import sanitize_html

_NEWS_TAG = re.compile(r"\{news:([a-z0-9-]{1,40})\}")


def embed_news(db: Session, site: Site, html: str) -> str:
    if not (site.features or {}).get("news"):
        return html

    def replace(match: re.Match[str]) -> str:
        post = db.scalar(
            select(NewsPost).where(
                NewsPost.site_id == site.id,
                NewsPost.tag == match.group(1),
                NewsPost.is_published.is_(True),
            )
        )
        if post is None:
            return ""
        return sanitize_html(post.body)

    return _NEWS_TAG.sub(replace, html)
