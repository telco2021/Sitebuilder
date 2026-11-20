"""Write a deployable site package from published content."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from liquid.files import media_path
from liquid.models import Category, FormDef, HelpArticle, HotelProperty, Media, Page, Product, RoomType, Site
from liquid.sites import clean_features

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

        return _MEDIA_URL.sub(replace, html)

    pages = []
    parents: dict[int, str] = {}
    for page in db.scalars(select(Page).where(Page.site_id == site.id, Page.is_published.is_(True)).order_by(Page.nav_order, Page.id)).all():
        parents[page.id] = page.slug
        pages.append(
            {
                "slug": page.slug,
                "title": page.live_title,
                "body": rewrite(page.live_body),
                "keywords": page.live_keywords,
                "description": page.live_description,
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
    return {
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
        "property": property_payload,
        "rooms": rooms,
        "categories": categories,
        "products": products,
        "forms": forms,
        "help": help_articles,
    }


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

Card numbers and security codes are not stored. A booking keeps the brand, last four digits, expiry, and a payment reference.
"""
