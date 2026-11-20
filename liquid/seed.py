"""First-run staff account and the Gateway Hotel sample site."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from liquid.config import Settings
from liquid.models import FormDef, HelpArticle, HotelProperty, Page, RoomType, Site, User
from liquid.security import hash_password, validate_password
from liquid.sites import clean_features
from liquid.textutil import FormError

log = logging.getLogger("liquid.seed")

_HOME = """
<h2>Stay directly with the hotel</h2>
<p>Search open dates, choose a room, and receive a confirmation code. The hotel keeps the reservation; card numbers are not stored.</p>
<p>Arrival and departure are calendar dates. A room is held for the nights in between, and inventory updates as soon as a booking is confirmed or cancelled.</p>
""".strip()

_STAY = """
<h2>Rooms</h2>
<p>The Standard Room has one king bed and sleeps two. The King Suite is a larger room with one king bed and sleeps three.</p>
<p>Rates shown during search are the nightly rate multiplied by the number of nights and rooms.</p>
""".strip()

_PRIVACY = """
<h2>Privacy</h2>
<p>Reservation details are used to host your stay and to keep accounting records. They are not sold to marketing lists.</p>
<p>Card numbers and security codes are checked at booking and then discarded. The reservation keeps the card brand, the last four digits, the expiry, and a payment reference.</p>
""".strip()

_SECURITY = """
<h2>Security</h2>
<p>Serve this site over HTTPS. Staff sign in with hashed passwords, and every form is protected against cross-site requests.</p>
<p>Hotel staff can see a payment reference and the last four digits. They cannot recover a full card number from this system.</p>
""".strip()

_CANCEL = """
<h2>Cancellation</h2>
<p>Cancel at least 24 hours before arrival by using your confirmation code and the email on the reservation. The room is returned to inventory immediately.</p>
""".strip()


def bootstrap_password(settings: Settings) -> str:
    if settings.bootstrap_password:
        try:
            return validate_password(settings.bootstrap_password)
        except FormError as exc:
            raise RuntimeError(f"LIQUID_BOOTSTRAP_PASSWORD is not strong enough. {exc}") from exc
    if settings.env == "development":
        log.warning("Using the documented development password. Set LIQUID_BOOTSTRAP_PASSWORD before exposing this host.")
        return "ChangeMe!Liquid2026"
    raise RuntimeError("Set LIQUID_BOOTSTRAP_PASSWORD before the first launch.")


def seed(db: Session, settings: Settings) -> None:
    if db.scalar(select(User.id).limit(1)):
        return
    password = bootstrap_password(settings)
    owner = User(
        email=settings.bootstrap_email.strip().lower(),
        username="builder",
        password_hash=hash_password(password, settings.env),
        first_name="Site",
        last_name="Builder",
        role="owner",
    )
    db.add(owner)
    db.flush()
    site = Site(
        name="Gateway Hotel",
        slug="gateway",
        company_name="Gateway Hotel",
        domain="gateway.example",
        language="en",
        tagline="A direct reservation desk for Gateway Hotel.",
        currency="USD",
        features=clean_features(
            {"cms": True, "menus": True, "search": True, "files": True, "help": True, "forms": True, "hotel": True}
        ),
    )
    db.add(site)
    db.flush()
    pages = [
        ("home", "Welcome", _HOME, "Gateway Hotel, reservations", "Book a room directly with Gateway Hotel.", 0),
        ("stay", "The stay", _STAY, "rooms, king suite", "Room types at Gateway Hotel.", 1),
        ("privacy", "Privacy", _PRIVACY, "privacy", "How reservation data is handled.", 2),
        ("security", "Security", _SECURITY, "security", "How payments and sign-in are protected.", 3),
        ("cancellation", "Cancellation", _CANCEL, "cancellation", "How to cancel a reservation.", 4),
    ]
    for slug, title, body, keywords, description, order in pages:
        db.add(
            Page(
                site_id=site.id,
                slug=slug,
                nav_order=order,
                show_in_nav=True,
                draft_title=title,
                draft_body=body,
                draft_keywords=keywords,
                draft_description=description,
                live_title=title,
                live_body=body,
                live_keywords=keywords,
                live_description=description,
                is_published=True,
                updated_by_id=owner.id,
            )
        )
    db.add(
        HotelProperty(
            site_id=site.id,
            name="Gateway Hotel",
            language="en",
            address1="10 Hegenberger Rd",
            city="Oakland",
            postcode="94621",
            state="CA",
            country="United States",
            phone="+1-510-555-0100",
            email="desk@gateway.example",
            policies="Cancel at least 24 hours before arrival. The confirmation email is the record of the stay.",
            currency="USD",
        )
    )
    db.add_all(
        [
            RoomType(
                site_id=site.id,
                name="Standard Room King Bed",
                nightly_rate_cents=12900,
                capacity=2,
                inventory=10,
                description="Standard room with one king bed.",
            ),
            RoomType(
                site_id=site.id,
                name="King Suite",
                nightly_rate_cents=18900,
                capacity=3,
                inventory=4,
                description="Larger room with one king bed.",
            ),
        ]
    )
    db.add(
        HelpArticle(
            site_id=site.id,
            title="How to search",
            audience="public",
            body="Enter arrival, departure, rooms, and guests. The next screen lists room types that can take the whole party and still have inventory for those nights.",
        )
    )
    db.add(
        HelpArticle(
            site_id=site.id,
            title="Publishing pages",
            audience="staff",
            body="Editors save drafts. Publishers copy a draft onto the live site. Revert copies the live page back over the draft.",
        )
    )
    db.add(
        FormDef(
            site_id=site.id,
            name="Contact the desk",
            slug="contact",
            description="Questions about a stay.",
            fields=[
                {"name": "name", "label": "Name", "type": "text", "required": True},
                {"name": "email", "label": "Email", "type": "email", "required": True},
                {"name": "message", "label": "Message", "type": "textarea", "required": True},
            ],
        )
    )
    db.commit()
    log.info("Seeded Sitebuilder owner %s and the Gateway Hotel sample.", owner.email)
