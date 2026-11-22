"""Persistence model for Sitebuilder and the sites it publishes."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    first_name: Mapped[str] = mapped_column(String(80), default="")
    last_name: Mapped[str] = mapped_column(String(80), default="")
    role: Mapped[str] = mapped_column(String(20), default="editor")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(80), default="")
    domain: Mapped[str] = mapped_column(String(255), default="")
    language: Mapped[str] = mapped_column(String(12), default="en")
    tagline: Mapped[str] = mapped_column(String(180), default="")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    shipping_cents: Mapped[int] = mapped_column(Integer, default=0)
    color_ink: Mapped[str] = mapped_column(String(7), default="#1a1814")
    color_paper: Mapped[str] = mapped_column(String(7), default="#fbf6ee")
    color_accent: Mapped[str] = mapped_column(String(7), default="#8c3d2f")
    color_header: Mapped[str] = mapped_column(String(7), default="#24352c")
    color_text: Mapped[str] = mapped_column(String(7), default="#241f1a")
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    pages: Mapped[list[Page]] = relationship(back_populates="site")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(80))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True)
    nav_order: Mapped[int] = mapped_column(Integer, default=0)
    show_in_nav: Mapped[bool] = mapped_column(Boolean, default=True)
    draft_title: Mapped[str] = mapped_column(String(160), default="")
    draft_body: Mapped[str] = mapped_column(Text, default="")
    draft_keywords: Mapped[str] = mapped_column(String(300), default="")
    draft_description: Mapped[str] = mapped_column(String(300), default="")
    draft_blocks: Mapped[str] = mapped_column(Text, default="[]")
    live_title: Mapped[str] = mapped_column(String(160), default="")
    live_body: Mapped[str] = mapped_column(Text, default="")
    live_keywords: Mapped[str] = mapped_column(String(300), default="")
    live_description: Mapped[str] = mapped_column(String(300), default="")
    live_blocks: Mapped[str] = mapped_column(Text, default="[]")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    site: Mapped[Site] = relationship(back_populates="pages")

    @property
    def dirty(self) -> bool:
        return (
            self.draft_title != self.live_title
            or self.draft_body != self.live_body
            or self.draft_keywords != self.live_keywords
            or self.draft_description != self.live_description
            or (self.draft_blocks or "[]") != (self.live_blocks or "[]")
        )


class PageAlias(Base):
    """A published address that now points at another address. Search engines keep the old link."""

    __tablename__ = "page_aliases"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(80))


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(180))
    stored_name: Mapped[str] = mapped_column(String(80), unique=True)
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HelpArticle(Base):
    __tablename__ = "help_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(String(16), default="public")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FormDef(Base):
    __tablename__ = "forms"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300), default="")
    fields: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("forms.id", ondelete="CASCADE"), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HotelProperty(Base):
    __tablename__ = "hotel_properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    language: Mapped[str] = mapped_column(String(12), default="en")
    address1: Mapped[str] = mapped_column(String(120), default="")
    address2: Mapped[str] = mapped_column(String(120), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    postcode: Mapped[str] = mapped_column(String(20), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    fax: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    policies: Mapped[str] = mapped_column(Text, default="")
    currency: Mapped[str] = mapped_column(String(3), default="USD")


class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (UniqueConstraint("site_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    nightly_rate_cents: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)
    inventory: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), index=True)
    confirmation_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    rooms: Mapped[int] = mapped_column(Integer)
    adults: Mapped[int] = mapped_column(Integer)
    children: Mapped[int] = mapped_column(Integer)
    check_in: Mapped[date] = mapped_column(Date, index=True)
    check_out: Mapped[date] = mapped_column(Date, index=True)
    nights: Mapped[int] = mapped_column(Integer)
    nightly_rate_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(40), default="")
    fax: Mapped[str] = mapped_column(String(40), default="")
    company: Mapped[str] = mapped_column(String(80), default="")
    address: Mapped[str] = mapped_column(String(160), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    postal: Mapped[str] = mapped_column(String(20), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    comments: Mapped[str] = mapped_column(Text, default="")
    payment_brand: Mapped[str] = mapped_column(String(30), default="")
    payment_last4: Mapped[str] = mapped_column(String(4), default="")
    payment_exp: Mapped[str] = mapped_column(String(7), default="")
    payment_reference: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="confirmed", index=True)
    cancelled_by: Mapped[str] = mapped_column(String(120), default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    room: Mapped[RoomType] = relationship()


class CancellationLog(Base):
    __tablename__ = "cancellation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id", ondelete="CASCADE"), index=True)
    admin_name: Mapped[str] = mapped_column(String(120))
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(60))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped[Category | None] = relationship()


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(40), default="")
    address: Mapped[str] = mapped_column(String(160), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    postal: Mapped[str] = mapped_column(String(20), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    shipping_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    payment_brand: Mapped[str] = mapped_column(String(30), default="")
    payment_last4: Mapped[str] = mapped_column(String(4), default="")
    payment_reference: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="paid")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lines: Mapped[list[OrderLine]] = relationship(back_populates="order")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cents: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="lines")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("site_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(512))
    first_name: Mapped[str] = mapped_column(String(80), default="")
    last_name: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="")
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(180), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MailOutbox(Base):
    __tablename__ = "mail_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NewsPost(Base):
    __tablename__ = "news_posts"
    __table_args__ = (UniqueConstraint("site_id", "slug"), UniqueConstraint("site_id", "tag"))

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(60))
    tag: Mapped[str | None] = mapped_column(String(40), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target_url: Mapped[str] = mapped_column(String(300))
    image_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    starts_on: Mapped[date] = mapped_column(Date, index=True)
    ends_on: Mapped[date] = mapped_column(Date)
    location: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text, default="")


class ServiceOffer(Base):
    __tablename__ = "service_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    details: Mapped[str] = mapped_column(Text, default="")
    postal_codes: Mapped[list] = mapped_column(JSON, default=list)


class SmsMessage(Base):
    __tablename__ = "sms_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(String(140))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(Text, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    questions: Mapped[list["CourseQuestion"]] = relationship(back_populates="course")


class CourseQuestion(Base):
    __tablename__ = "course_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    prompt: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(8))
    choices: Mapped[list] = mapped_column(JSON, default=list)
    correct_index: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped[Course] = relationship(back_populates="questions")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("site_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RvCategory(Base):
    __tablename__ = "rv_categories"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("rv_categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class RvModel(Base):
    __tablename__ = "rv_models"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("rv_categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(60))
    year: Mapped[int] = mapped_column(Integer, default=0)
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


class RvAccount(Base):
    __tablename__ = "rv_accounts"
    __table_args__ = (UniqueConstraint("site_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RvFavorite(Base):
    __tablename__ = "rv_favorites"
    __table_args__ = (UniqueConstraint("account_id", "model_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("rv_accounts.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("rv_models.id", ondelete="CASCADE"), index=True)


class RvOffer(Base):
    __tablename__ = "rv_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("rv_accounts.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("rv_models.id", ondelete="CASCADE"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CouponCategory(Base):
    __tablename__ = "coupon_categories"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("coupon_categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60))


class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (UniqueConstraint("site_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str] = mapped_column(String(512))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("coupon_categories.id"), nullable=True)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(60))
    details: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


class GalleryAlbum(Base):
    __tablename__ = "gallery_albums"
    __table_args__ = (UniqueConstraint("site_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(60))
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cover_media_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GalleryImage(Base):
    __tablename__ = "gallery_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("gallery_albums.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[int] = mapped_column(Integer)
    caption: Mapped[str] = mapped_column(String(180), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="image")


class GalleryDesk(Base):
    """Layout for the public image and video gallery. One row per site."""

    __tablename__ = "gallery_desks"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), unique=True)
    columns: Mapped[int] = mapped_column(Integer, default=3)
    rows: Mapped[int] = mapped_column(Integer, default=3)
    padding: Mapped[int] = mapped_column(Integer, default=4)
    border_width: Mapped[int] = mapped_column(Integer, default=1)
    border_color: Mapped[str] = mapped_column(String(7), default="#000000")
    transition_seconds: Mapped[int] = mapped_column(Integer, default=4)
    copyright_name: Mapped[str] = mapped_column(String(160), default="")
