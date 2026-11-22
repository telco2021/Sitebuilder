"""Write a deployable site package from published content."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from liquid.content import embed_news
from liquid.design import published_body
from liquid.files import media_path
from liquid.models import (
    Banner,
    CalendarEvent,
    Category,
    Coupon,
    Course,
    CourseQuestion,
    FormDef,
    GalleryAlbum,
    GalleryImage,
    HelpArticle,
    HotelProperty,
    Media,
    NewsPost,
    Page,
    PageAlias,
    Product,
    RoomType,
    RvCategory,
    RvModel,
    ServiceOffer,
    Site,
)
from liquid.seo import listing_paths
from liquid.sites import clean_features
from liquid.textutil import sanitize_html

_BLUEPRINT = Path(__file__).resolve().parent / "blueprint"
_MEDIA_URL = re.compile(r"/media/(\d+)")


def build_bundle(db: Session, site: Site, upload_root: Path, media_dest: Path | None) -> dict:
    id_to_file: dict[int, str] = {}
    if media_dest is not None:
        media_dest.mkdir(parents=True, exist_ok=True)
        for item in db.scalars(select(Media).where(Media.site_id == site.id)).all():
            try:
                source = media_path(upload_root, site.id, item.stored_name)
            except FileNotFoundError:
                continue
            target_name = Path(item.stored_name).name
            shutil.copyfile(source, media_dest / target_name)
            id_to_file[item.id] = target_name

    def rewrite(html: str) -> str:
        def replace(match: re.Match[str]) -> str:
            name = id_to_file.get(int(match.group(1)))
            return f"/media/{name}" if name else match.group(0)

        rewritten = _MEDIA_URL.sub(replace, html)
        prefix = f"/s/{site.slug}"
        return rewritten.replace(prefix + "/", "/").replace(prefix + '"', '/"').replace(prefix + "'", "/'")

    pages = []
    parents: dict[int, str] = {}
    image_ids = set(id_to_file)
    for page in db.scalars(select(Page).where(Page.site_id == site.id, Page.is_published.is_(True)).order_by(Page.nav_order, Page.id)).all():
        parents[page.id] = page.slug
        updated = page.updated_at.date().isoformat() if page.updated_at else ""
        pages.append(
            {
                "slug": page.slug,
                "title": page.live_title,
                "body": rewrite(embed_news(db, site, published_body(page.live_blocks or "", page.live_body or "", image_ids))),
                "keywords": page.live_keywords,
                "description": page.live_description,
                "updated": updated,
                "show_in_nav": page.show_in_nav,
                "nav_order": page.nav_order,
                "parent_slug": None,
                "parent_id": page.parent_id,
            }
        )
    for page in pages:
        parent_id = page.pop("parent_id")
        page["parent_slug"] = parents.get(parent_id) if parent_id else None

    property_row = db.scalar(select(HotelProperty).where(HotelProperty.site_id == site.id))
    property_payload = None
    if property_row:
        property_payload = {
            "name": property_row.name,
            "language": property_row.language,
            "address1": property_row.address1,
            "address2": property_row.address2,
            "city": property_row.city,
            "postcode": property_row.postcode,
            "state": property_row.state,
            "country": property_row.country,
            "phone": property_row.phone,
            "fax": property_row.fax,
            "email": property_row.email,
            "policies": property_row.policies,
            "currency": property_row.currency,
        }
    rooms = [
        {
            "name": room.name,
            "nightly_rate_cents": room.nightly_rate_cents,
            "capacity": room.capacity,
            "inventory": room.inventory,
            "description": room.description,
        }
        for room in db.scalars(select(RoomType).where(RoomType.site_id == site.id).order_by(RoomType.id)).all()
    ]
    categories = [
        {"slug": row.slug, "name": row.name}
        for row in db.scalars(select(Category).where(Category.site_id == site.id).order_by(Category.name)).all()
    ]
    products = [
        {
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
            "price_cents": row.price_cents,
            "stock": row.stock,
            "active": row.active,
            "category_slug": row.category.slug if row.category else "",
        }
        for row in db.scalars(select(Product).where(Product.site_id == site.id).order_by(Product.name)).all()
    ]
    forms = [
        {
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
            "fields": row.fields,
        }
        for row in db.scalars(select(FormDef).where(FormDef.site_id == site.id).order_by(FormDef.name)).all()
    ]
    help_articles = [
        {"title": row.title, "body": row.body}
        for row in db.scalars(
            select(HelpArticle).where(HelpArticle.site_id == site.id, HelpArticle.audience == "public").order_by(HelpArticle.id)
        ).all()
    ]
    news = [
        {"slug": row.slug, "title": row.title, "tag": row.tag or "", "body": sanitize_html(row.body)}
        for row in db.scalars(select(NewsPost).where(NewsPost.site_id == site.id, NewsPost.is_published.is_(True)).order_by(NewsPost.id)).all()
    ]
    banners = [
        {"name": row.name, "target_url": row.target_url, "image": id_to_file.get(row.image_id, "") if row.image_id else ""}
        for row in db.scalars(select(Banner).where(Banner.site_id == site.id, Banner.active.is_(True)).order_by(Banner.sort_order)).all()
    ]
    events = [
        {"title": row.title, "starts_on": row.starts_on.isoformat(), "ends_on": row.ends_on.isoformat(), "location": row.location, "body": sanitize_html(row.body)}
        for row in db.scalars(select(CalendarEvent).where(CalendarEvent.site_id == site.id).order_by(CalendarEvent.starts_on)).all()
    ]
    services = [
        {"name": row.name, "details": sanitize_html(row.details), "postal_codes": row.postal_codes}
        for row in db.scalars(select(ServiceOffer).where(ServiceOffer.site_id == site.id).order_by(ServiceOffer.name)).all()
    ]
    courses = []
    for course in db.scalars(select(Course).where(Course.site_id == site.id, Course.is_published.is_(True)).order_by(Course.title)).all():
        courses.append(
            {
                "slug": course.slug,
                "title": course.title,
                "summary": sanitize_html(course.summary),
                "questions": [
                    {"prompt": question.prompt, "choices": question.choices}
                    for question in db.scalars(select(CourseQuestion).where(CourseQuestion.course_id == course.id).order_by(CourseQuestion.sort_order, CourseQuestion.id)).all()
                ],
            }
        )
    coaches = [
        {"slug": row.slug, "name": row.name, "year": row.year, "price_cents": row.price_cents, "summary": sanitize_html(row.summary)}
        for row in db.scalars(select(RvModel).where(RvModel.site_id == site.id, RvModel.is_published.is_(True)).order_by(RvModel.name)).all()
    ]
    coach_categories = [
        {"name": row.name, "slug": row.slug}
        for row in db.scalars(select(RvCategory).where(RvCategory.site_id == site.id).order_by(RvCategory.name)).all()
    ]
    coupons = [
        {"title": row.title, "city": row.city, "state": row.state, "details": sanitize_html(row.details), "expires_on": row.expires_on.isoformat() if row.expires_on else ""}
        for row in db.scalars(select(Coupon).where(Coupon.site_id == site.id, Coupon.is_published.is_(True)).order_by(Coupon.title)).all()
    ]
    albums = []
    for album in db.scalars(select(GalleryAlbum).where(GalleryAlbum.site_id == site.id).order_by(GalleryAlbum.title)).all():
        if album.password_hash:
            continue
        pictures = []
        for image in db.scalars(select(GalleryImage).where(GalleryImage.album_id == album.id).order_by(GalleryImage.id)).all():
            filename = id_to_file.get(image.media_id, "")
            if filename:
                pictures.append({"file": filename, "caption": image.caption, "kind": image.kind if image.kind in {"image", "video"} else "image"})
        albums.append({"slug": album.slug, "title": album.title, "images": pictures})
    bundle = {
        "format": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site": {
            "name": site.name,
            "slug": site.slug,
            "company_name": site.company_name,
            "domain": site.domain,
            "language": site.language,
            "tagline": site.tagline,
            "currency": site.currency,
            "shipping_cents": site.shipping_cents,
            "colors": {
                "ink": site.color_ink,
                "paper": site.color_paper,
                "accent": site.color_accent,
                "header": site.color_header,
                "text": site.color_text,
            },
            "features": clean_features(site.features),
        },
        "pages": pages,
        "redirects": _redirects(db, site),
        "paths": [{"path": path, "updated": updated} for path, updated in listing_paths(pages, clean_features(site.features), "")],
        "property": property_payload,
        "rooms": rooms,
        "categories": categories,
        "products": products,
        "forms": forms,
        "help": help_articles,
        "news": news,
        "banners": banners,
        "events": events,
        "services": services,
        "courses": courses,
        "coaches": coaches,
        "coach_categories": coach_categories,
        "coupons": coupons,
        "albums": albums,
    }
    if media_dest is not None and media_dest.is_dir():
        referenced = json.dumps(bundle)
        for path in media_dest.iterdir():
            if path.is_file() and path.name not in referenced:
                path.unlink()
    return bundle


def generate_site(db: Session, site: Site, upload_root: Path, generated_root: Path) -> tuple[Path, Path]:
    destination = (generated_root / site.slug).resolve()
    if not destination.is_relative_to(generated_root.resolve()):
        raise RuntimeError("Refusing to generate outside the output directory.")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(_BLUEPRINT, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "README.md"))
    bundle = build_bundle(db, site, upload_root, destination / "media")
    (destination / "site_bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    (destination / "README.md").write_text(_readme(site), encoding="utf-8")
    archive_base = generated_root / site.slug
    archive = shutil.make_archive(str(archive_base), "zip", root_dir=generated_root, base_dir=site.slug)
    return destination, Path(archive)


def _redirects(db: Session, site: Site) -> dict[str, str]:
    redirects: dict[str, str] = {}
    for alias in db.scalars(select(PageAlias).where(PageAlias.site_id == site.id)).all():
        target = db.get(Page, alias.page_id)
        if target is not None and target.site_id == site.id and target.is_published and target.slug != alias.slug:
            redirects[alias.slug] = target.slug
    return redirects


def _readme(site: Site) -> str:
    return f"""# {site.name}

Generated by Liquid Software Sitebuilder. This folder is a standalone site.
It includes published pages and the features that were enabled at generation time.
Reservations, orders, and form submissions created here stay in `site.db` and are not sent back to Sitebuilder.

## Run

```bash
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8080
```

On Windows, Waitress is a simple production server behind IIS or on its own:

```bash
python -m waitress --listen=127.0.0.1:8080 app:app
```

Put a TLS proxy in front before exposing the site. The session secret is created on first launch as `.secret`.

Set these before the site is reachable on the public internet:

```bash
SITE_ALLOWED_HOSTS=www.example.com
SITE_COOKIE_SECURE=true
SITE_SESSION_HOURS=8
```

`SITE_ALLOWED_HOSTS` is the domain visitors use. Leave it empty only while you are trying the site on this computer. `SITE_COOKIE_SECURE=true` keeps the sign-in cookie on HTTPS. The security headers on this site match Sitebuilder: no scripts, no framing, and a locked session cookie.

Card numbers and security codes are not stored. A booking keeps the brand, last four digits, expiry, and a payment reference.
"""
