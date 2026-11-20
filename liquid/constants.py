"""Feature catalog and shared limits for Sitebuilder."""

FEATURES: tuple[tuple[str, str, str, str], ...] = (
    ("cms", "Pages", "Content", "Draft, publish, and revert pages."),
    ("menus", "Menus", "Content", "Navigation built from the page tree."),
    ("search", "Search", "Content", "Search published pages."),
    ("files", "Files", "Content", "Upload images and documents into pages."),
    ("help", "Help", "Content", "Public help articles and staff notes."),
    ("forms", "Online forms", "Content", "Custom forms with stored submissions."),
    ("accounts", "Customer accounts", "Commerce", "Visitor registration and sign-in."),
    ("catalog", "Catalog and checkout", "Commerce", "Products, cart, and orders."),
    ("hotel", "Hotel reservations", "Hospitality", "Rooms, availability, booking, and cancellation."),
    ("news", "News", "Content", "Published articles. A page can include one with {news:tag}."),
    ("banners", "Banners", "Content", "Campaign links and images, managed by staff."),
    ("calendar", "Calendar", "Content", "Dated events."),
    ("services", "Services", "Content", "Services matched to a postal code."),
    ("gallery", "Gallery", "Content", "Albums of files already uploaded to the site."),
    ("share", "Tell a friend", "Content", "Queue a short note to someone. It stays on this server."),
    ("lms", "Courses", "Learning", "Courses, enrolled students, and graded quizzes."),
    ("rv", "RV coaches", "Inventory", "Coach categories, models, favorites, and offers."),
    ("coupons", "Coupons", "Commerce", "Offers by city and state. Merchants wait for approval."),
    ("sms", "Messages", "Desk", "A local message queue. Nothing is sent to a phone network."),
)

FEATURE_KEYS = tuple(item[0] for item in FEATURES)

RESERVED_PAGE_SLUGS = frozenset(
    {
        "hotel",
        "shop",
        "cart",
        "checkout",
        "account",
        "search",
        "forms",
        "help",
        "media",
        "static",
        "admin",
        "api",
        "orders",
        "news",
        "banners",
        "calendar",
        "services",
        "gallery",
        "share",
        "learn",
        "coaches",
        "coupons",
        "messages",
    }
)

CARD_BRANDS = ("Visa", "Mastercard", "American Express", "Discover")

COUNTRIES = (
    "Australia",
    "Brazil",
    "Canada",
    "China",
    "France",
    "Germany",
    "India",
    "Ireland",
    "Italy",
    "Japan",
    "Mexico",
    "Netherlands",
    "New Zealand",
    "Singapore",
    "Spain",
    "Sweden",
    "Switzerland",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
)

MAX_STAY_NIGHTS = 30
MAX_ROOMS = 10
MAX_GUESTS = 12
UPLOAD_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}
