from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False)
    sessions: Mapped[List["Session"]] = relationship(back_populates="user")
    messages: Mapped[List["MessageLog"]] = relationship(back_populates="user")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, nullable=False
    )
    children_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    interests_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    neighborhoods_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    budget_preference: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    max_travel_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crowd_tolerance: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    indoor_outdoor: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    special_needs_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="profile")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="WELCOME")
    state_payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_user_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sessions")


class MessageLog(Base):
    __tablename__ = "messages_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    tg_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="messages")


class RecommendationLog(Base):
    __tablename__ = "recommendations_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    request_context_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    recommended_events_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    short_title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tagline: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    tags_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ticket_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Dates and times
    start_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, index=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    start_time: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    end_time: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    schedule_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Location
    venue_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    venue_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    borough: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Age
    age_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_best_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_best_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Price
    is_free: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    price_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_min_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_max_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_display: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Media
    main_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    images_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Venue details
    venue_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    stroller_friendly: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    wheelchair_accessible: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    accessibility_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    venue_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    venue_website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Reviews and ratings
    rating_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reviews_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Extra info
    includes_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    is_family_friendly: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    subway_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    derisk_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Import tracking
    source_csv: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class EventRating(Base):
    __tablename__ = "event_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    event_external_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    event_title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    search_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
