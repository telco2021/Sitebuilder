"""Built-in Sitebuilder guides. These explain the software itself.

Visitor help articles are a separate feature. Staff write those for a site.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from liquid.constants import FEATURE_KEYS


@dataclass(frozen=True)
class Guide:
    slug: str
    title: str
    group: str
    summary: str
    steps: tuple[str, ...]
    notes: tuple[str, ...] = ()
    related: tuple[str, ...] = ()


GUIDES: tuple[Guide, ...] = (
    Guide(
        "sites",
        "Sites",
        "Start",
        "A site is one website. Sitebuilder keeps every site in this list.",
        (
            "Sign in. The Sites page opens.",
            "Read the name and tagline on each card.",
            "Choose Preview to open the public site.",
            "Choose a feature name on the card, such as Pages or Hotel, to work on that part.",
            "Choose New site when you want another website.",
        ),
        related=("new-site", "settings"),
    ),
    Guide(
        "new-site",
        "New site",
        "Start",
        "Create a website, then turn on the features it needs.",
        (
            "Open Sites and choose New site.",
            "Type a site name. The address of the site is made from that name.",
            "Add the company, a domain label, a tagline, a language, and a currency if you have them.",
            "An owner can tick the features this site should include. Pages, Menus, and Search start ticked.",
            "Choose Create site. The settings page for the new site opens.",
        ),
        ("Shipping is set later, on Settings. A new site starts with no flat shipping charge.",),
        ("settings", "pages"),
    ),
    Guide(
        "settings",
        "Settings",
        "Start",
        "Settings hold the site name, colors, shipping, and the feature switches.",
        (
            "Open the site and choose Settings.",
            "Edit the name, company, domain label, tagline, language, and currency.",
            "Type a flat shipping amount in cents. 500 means 5.00 in the site currency. Use 0 when shipping is free.",
            "Set the five colors. Each color is a value such as #24352c.",
            "An owner ticks Features to show or hide each module. Choose Help beside a feature to read how that feature works.",
            "Choose Save settings.",
        ),
        ("Delete this site is at the bottom and is only for an owner. Deleting removes the site and its uploaded files.",),
        ("new-site", "generate"),
    ),
    Guide(
        "staff",
        "Staff",
        "Start",
        "An owner creates the people who work in Sitebuilder and assigns each person a role.",
        (
            "Open Staff in the left menu.",
            "Enter the email, username, and name.",
            "Choose a role. Owner manages staff and features. Publisher publishes pages and generates the site. Editor saves drafts, files, forms, and visitor help. Hotel runs the reservation desk.",
            "Type a temporary password of 12 to 128 characters, with an upper-case letter, a lower-case letter, and a digit.",
            "Choose Create account. Ask the person to sign in and change the password.",
            "Use Activate or Deactivate on a row when someone should gain or lose access.",
        ),
        related=("password", "audit"),
    ),
    Guide(
        "password",
        "Password",
        "Start",
        "Each person changes their own Sitebuilder password here.",
        (
            "Open Password in the left menu.",
            "Type the current password.",
            "Type the new password twice. Use 12 to 128 characters, with an upper-case letter, a lower-case letter, and a digit.",
            "Choose Change password.",
        ),
        related=("staff",),
    ),
    Guide(
        "pages",
        "Pages",
        "Content",
        "Pages are the written pages of the site. A draft stays private until a publisher publishes it.",
        (
            "Open the site and choose Pages.",
            "Choose New page.",
            "Type a title and an address, such as about. The address becomes /about on the public site.",
            "Set Menu order and Parent when this page belongs under another page. Tick Show in the menu to list it.",
            "Open Design to add headings, text, images, buttons, lists, quotes, columns, and dividers. Open HTML to edit the page as HTML. Scripts are removed when you save.",
            "Add keywords and a short description for search.",
            "Choose Save draft to keep working. A publisher chooses Publish to copy the draft onto the live site.",
            "Revert draft copies the live page back over the draft. Delete page removes the page.",
        ),
        ("An editor can save drafts. Publishing and generating need a publisher or an owner.", "To place an uploaded picture, use the address shown on Files, such as /media/1, as the image source."),
        ("menus", "files", "search"),
    ),
    Guide(
        "menus",
        "Menus",
        "Content",
        "The public menu is built from published pages. There is no separate menu screen.",
        (
            "Turn on Menus and Pages in Settings.",
            "Open Pages and edit the page.",
            "Tick Show in the menu.",
            "Set Menu order. Lower numbers come first.",
            "Choose a Parent to nest the page under another page.",
            "Publish the page. The live menu uses the published title and address.",
        ),
        related=("pages", "settings"),
    ),
    Guide(
        "search",
        "Search",
        "Content",
        "Search looks through published pages on the public site.",
        (
            "Turn on Search in Settings.",
            "Publish the pages you want visitors to find.",
            "Open the public site. The search box is in the header.",
            "A visitor types words and the site lists matching published pages.",
        ),
        ("Drafts stay out of search until they are published.",),
        ("pages",),
    ),
    Guide(
        "files",
        "Files",
        "Content",
        "Upload pictures, PDFs, and short videos, then place them on a page or in the gallery.",
        (
            "Open Files.",
            "Choose a PNG, JPEG, GIF, WebP, PDF, MP4, or WebM file. The limit is 5 MB.",
            "Choose Upload. Sitebuilder checks the file type from the file itself.",
            "Copy the address in Use in a page, such as /media/3.",
            "On a page, use that address as the image source. In Gallery, pick the same file when you add an item.",
            "Choose Delete on a row to remove that file.",
        ),
        related=("pages", "gallery", "banners"),
    ),
    Guide(
        "visitor-help",
        "Visitor help articles",
        "Content",
        "These articles are for the visitors of one site. They are separate from this Sitebuilder guide.",
        (
            "Turn on Help in Settings.",
            "Open Help on the site card.",
            "Type a title and the article.",
            "Choose Public to show it on the site, or Staff only to keep it inside Sitebuilder.",
            "Choose Save article.",
            "Visitors open Help on the public site to read the public articles.",
        ),
        ("The Help button in Sitebuilder explains the software. The Help section on a site is the text you write for visitors.",),
        ("pages",),
    ),
    Guide(
        "forms",
        "Online forms",
        "Content",
        "A form collects answers from visitors and stores them in Sitebuilder.",
        (
            "Open Forms.",
            "Type a name and a short description.",
            "List one field per line: name, label, type, and required, separated by |.",
            "Use the type text, email, textarea, or tel. Put yes in the last column when the field is required.",
            "Choose Create form. The form address is shown in the list.",
            "Open a form in the list to read the submissions visitors have sent.",
        ),
        ("Example line: email | Email | email | yes",),
        ("pages",),
    ),
    Guide(
        "news",
        "News",
        "Content",
        "News articles appear on the public News page. A tag can also drop an article into a page.",
        (
            "Open News.",
            "Type a title, an optional tag, and the body.",
            "Tick Publish when the article should be visible.",
            "Choose Save article.",
            "Visitors read the list at /news on the site.",
            "To show tagged articles inside a page, put {news:your-tag} in the page body and publish the page.",
        ),
        related=("pages",),
    ),
    Guide(
        "banners",
        "Banners",
        "Content",
        "A banner is a named link, with an optional picture and dates.",
        (
            "Upload the picture on Files first if you want one.",
            "Open Banners.",
            "Type a name and the link the banner should open.",
            "Type the image id from Files, or leave it blank.",
            "Set a start date, an end date, and an order.",
            "Leave Active ticked, then choose Save banner.",
            "Visitors see current active banners on the public Banners page.",
        ),
        related=("files",),
    ),
    Guide(
        "calendar",
        "Calendar",
        "Content",
        "Calendar events are dated items on the public calendar.",
        (
            "Open Calendar.",
            "Type a title, a start date, an optional end date, a location, and the details.",
            "Choose Save event.",
            "Visitors open Calendar on the public site.",
            "Choose Delete beside an event to remove it.",
        ),
        related=("news",),
    ),
    Guide(
        "services",
        "Services",
        "Content",
        "A service is offered in the postal codes you list. Visitors search by postal code.",
        (
            "Open Services.",
            "Type the service name.",
            "Type the postal codes, separated by commas.",
            "Add the details and choose Save service.",
            "On the public Services page, a visitor enters a postal code and sees the matching services.",
        ),
        related=("pages",),
    ),
    Guide(
        "gallery",
        "Gallery",
        "Content",
        "A gallery is a set of albums. An album holds images and MP4 or WebM video.",
        (
            "Upload the pictures and videos on Files first.",
            "Open Gallery.",
            "Set columns, rows, padding, border, slide seconds, and a copyright line, then choose Save layout.",
            "Type an album title, choose a cover image, and choose Create album. Leave the password blank for a public album.",
            "To lock an album, type a password of 12 or more characters with upper case, lower case, and a digit, then choose Lock.",
            "Add an image or video: choose the album, the file, a caption, and a description, then choose Add to album.",
            "Visitors open Gallery on the public site. A locked album asks for the password before it shows its files.",
            "Choose Remove password to make a locked album public again.",
        ),
        (
            "Sitebuilder stores a hash of the album password. The password itself is not written into a generated site.",
            "A locked album is left out when you generate the site.",
        ),
        ("files", "generate"),
    ),
    Guide(
        "share",
        "Tell a friend",
        "Content",
        "A visitor can queue a short note about a page. The note waits on this server.",
        (
            "Turn on Tell a friend in Settings.",
            "On the public site, open Tell a friend.",
            "The visitor enters an email, a page address, and a note, then queues it.",
            "An owner can read queued mail under Outbox.",
        ),
        ("The note stays in the outbox until a mail service is connected. Sitebuilder does not deliver it by itself.",),
        ("outbox",),
    ),
    Guide(
        "accounts",
        "Customer accounts",
        "Commerce",
        "Visitors can register and sign in on the public site.",
        (
            "Turn on Customer accounts in Settings.",
            "On the public site, open Sign in.",
            "A visitor creates an account with name, email, and password, or signs in with an account that already exists.",
            "The public menu then shows Account for that visitor.",
        ),
        related=("catalog",),
    ),
    Guide(
        "catalog",
        "Catalog and checkout",
        "Commerce",
        "The catalog is the shop: categories, products, a cart, and an order.",
        (
            "Open Catalog.",
            "Add a category, then add a product with a name, category, price, stock, and description.",
            "Leave Active ticked so the product appears in the shop. Choose Save product.",
            "Set flat shipping in cents on Settings. That amount is added at checkout.",
            "A visitor opens Shop, adds a product to the cart, and checks out.",
            "Checkout keeps the card brand, the last four digits, and a reference. The full card number and the security code are discarded.",
        ),
        related=("settings", "accounts"),
    ),
    Guide(
        "coupons",
        "Coupons",
        "Commerce",
        "Coupons are offers grouped by category, city, and state. A merchant can ask to be approved.",
        (
            "Open Coupons.",
            "Add a category.",
            "Save a coupon with a title, category, city, state, expiry, and details. Tick Publish to show it.",
            "Visitors browse Coupons on the public site.",
            "A merchant signs up from the public coupons area. The request appears under Merchants.",
            "Choose Approve when that merchant should be able to post offers. Approval stays in Sitebuilder.",
        ),
        related=("catalog",),
    ),
    Guide(
        "hotel",
        "Hotel reservations",
        "Hospitality",
        "The hotel desk stores the property, the rooms you can sell, and the reservations guests make.",
        (
            "Open Hotel.",
            "Fill in the property name, address, phone, desk email, and policies, then choose Save property.",
            "Add a room type with a nightly rate, guests per room, and how many rooms you have. Choose Add room type.",
            "On the public site, a guest opens Reserve, enters dates and the number of rooms and guests, and picks an available room.",
            "The booking page checks the card and stores the brand, the last four digits, the expiry, and a reference. The full card number and the security code are discarded.",
            "The reservation appears on this Hotel page. Update the guest details, or choose Cancel reservation while it is confirmed.",
            "A guest can also open Cancel on the public site and use the confirmation code.",
        ),
        ("Availability counts nights that overlap a stay. A publisher or the hotel role can run this desk.",),
        ("generate",),
    ),
    Guide(
        "courses",
        "Courses",
        "Learning",
        "A course has a summary, questions, and enrolled students. Students sign in on the public site and submit a quiz.",
        (
            "Open Courses.",
            "Save a course with a title and summary. Tick Publish to show it.",
            "Add a question. Choose true or false, or multiple choice with one choice per line. Correct choice starts at 1.",
            "Create a student with an email and password, and choose the course under Enroll in.",
            "The student opens Courses on the public site, signs in, opens the course, and submits the quiz.",
            "Grading stays in Sitebuilder.",
        ),
        related=("accounts",),
    ),
    Guide(
        "coaches",
        "RV coaches",
        "Inventory",
        "Coaches are recreational-vehicle models, arranged in categories. A signed-in visitor can save a favorite or make an offer.",
        (
            "Open Coaches.",
            "Add a category. A category can have a parent.",
            "Save a model with a name, category, year, price in whole currency units, and a summary. Tick Publish to show it.",
            "Visitors open Coaches on the public site. After they sign in there, they can mark a favorite or send an offer.",
            "Offers appear in the Offers list on this page.",
        ),
        related=("catalog",),
    ),
    Guide(
        "messages",
        "Messages",
        "Desk",
        "The message queue stores a short note beside a phone number. It stays on this server.",
        (
            "Open Messages.",
            "Type a phone number and a message of up to 140 characters.",
            "Choose Queue message.",
            "The row shows the time, the number, the status, and the text.",
        ),
        ("Sitebuilder keeps the message in this queue. It does not hand the message to a phone network.",),
        ("outbox",),
    ),
    Guide(
        "generate",
        "Generate",
        "Desk",
        "Generate writes a standalone copy of the published site that you can download and run.",
        (
            "Publish the pages and items that should be in the copy.",
            "Open Generate.",
            "Choose Generate source. Sitebuilder writes a folder for this site and a zip file.",
            "Choose the download link and keep the zip.",
            "On the computer that will run the site, install the requirements from that folder and start its app.",
        ),
        (
            "Reservations made on the generated site stay in that copy.",
            "Generating again replaces the snapshot in Sitebuilder. Download and keep a running copy before you generate again.",
            "Locked gallery albums are left out of the generated site.",
        ),
        ("pages", "gallery", "hotel"),
    ),
    Guide(
        "audit",
        "Audit",
        "Desk",
        "The audit list shows who did what in Sitebuilder.",
        (
            "Open Audit in the left menu. Owners and publishers can open it.",
            "Read the time, the person, the action, and the target.",
            "Use it to confirm a sign-in, a published page, a new site, or a reservation change.",
        ),
        related=("staff",),
    ),
    Guide(
        "outbox",
        "Outbox",
        "Desk",
        "The outbox holds mail that Sitebuilder has queued, including password-reset links and tell-a-friend notes.",
        (
            "Open Outbox in the left menu. This list is for an owner.",
            "Each card shows the subject and the recipient.",
            "In development, the message body is shown so you can copy a reset link when no mail server is connected.",
            "In production, message bodies stay hidden.",
        ),
        ("Connect a mail service before you rely on delivery. Until then, the messages wait here.",),
        ("share", "password"),
    ),
)


_BY_SLUG = {guide.slug: guide for guide in GUIDES}

FEATURE_GUIDES = {
    "cms": "pages",
    "menus": "menus",
    "search": "search",
    "files": "files",
    "help": "visitor-help",
    "forms": "forms",
    "accounts": "accounts",
    "catalog": "catalog",
    "hotel": "hotel",
    "news": "news",
    "banners": "banners",
    "calendar": "calendar",
    "services": "services",
    "gallery": "gallery",
    "share": "share",
    "lms": "courses",
    "rv": "coaches",
    "coupons": "coupons",
    "sms": "messages",
}

_PATHS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^/admin/sites/new$"), "new-site"),
    (re.compile(r"^/admin/sites/\d+/pages(?:/|$)"), "pages"),
    (re.compile(r"^/admin/sites/\d+/files(?:/|$)"), "files"),
    (re.compile(r"^/admin/sites/\d+/hotel(?:/|$)"), "hotel"),
    (re.compile(r"^/admin/sites/\d+/catalog(?:/|$)"), "catalog"),
    (re.compile(r"^/admin/sites/\d+/forms(?:/|$)"), "forms"),
    (re.compile(r"^/admin/sites/\d+/help(?:/|$)"), "visitor-help"),
    (re.compile(r"^/admin/sites/\d+/news(?:/|$)"), "news"),
    (re.compile(r"^/admin/sites/\d+/banners(?:/|$)"), "banners"),
    (re.compile(r"^/admin/sites/\d+/calendar(?:/|$)"), "calendar"),
    (re.compile(r"^/admin/sites/\d+/services(?:/|$)"), "services"),
    (re.compile(r"^/admin/sites/\d+/gallery(?:/|$)"), "gallery"),
    (re.compile(r"^/admin/sites/\d+/learn(?:/|$)"), "courses"),
    (re.compile(r"^/admin/sites/\d+/coaches(?:/|$)"), "coaches"),
    (re.compile(r"^/admin/sites/\d+/coupons(?:/|$)"), "coupons"),
    (re.compile(r"^/admin/sites/\d+/messages(?:/|$)"), "messages"),
    (re.compile(r"^/admin/sites/\d+/settings$"), "settings"),
    (re.compile(r"^/admin/sites/\d+/generate$"), "generate"),
    (re.compile(r"^/admin/sites/\d+/download$"), "generate"),
    (re.compile(r"^/admin/users$"), "staff"),
    (re.compile(r"^/admin/audit$"), "audit"),
    (re.compile(r"^/admin/outbox$"), "outbox"),
    (re.compile(r"^/admin/account$"), "password"),
    (re.compile(r"^/admin$"), "sites"),
)


def guide_slug_for_feature(key: str) -> str:
    return FEATURE_GUIDES.get(key, "")


def article(slug: str) -> Guide | None:
    return _BY_SLUG.get(slug)


def article_for_path(path: str) -> Guide | None:
    clean = path.split("?", 1)[0].rstrip("/") or "/"
    if clean.startswith("/admin/guide"):
        return None
    for pattern, slug in _PATHS:
        if pattern.search(clean):
            return _BY_SLUG[slug]
    return None


def grouped_guides() -> list[tuple[str, list[Guide]]]:
    order = ("Start", "Content", "Commerce", "Hospitality", "Learning", "Inventory", "Desk")
    buckets: dict[str, list[Guide]] = {name: [] for name in order}
    for guide in GUIDES:
        buckets.setdefault(guide.group, []).append(guide)
    return [(name, items) for name, items in buckets.items() if items]


def related_guides(guide: Guide) -> list[Guide]:
    return [item for slug in guide.related if (item := _BY_SLUG.get(slug))]


def catalog_gaps() -> list[str]:
    missing = [key for key in FEATURE_KEYS if FEATURE_GUIDES.get(key) not in _BY_SLUG]
    missing.extend(slug for slug in FEATURE_GUIDES.values() if slug not in _BY_SLUG)
    return missing
