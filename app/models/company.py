"""Company model."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Company(Base):
    """Company tracked by SignalForge."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    founder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    founder_linkedin_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    company_linkedin_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    target_profile_match: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cto_need_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    signal_records: Mapped[list["SignalRecord"]] = relationship(
        "SignalRecord", back_populates="company", cascade="all, delete-orphan"
    )
    analysis_records: Mapped[list["AnalysisRecord"]] = relationship(
        "AnalysisRecord", back_populates="company", cascade="all, delete-orphan"
    )
    briefing_items: Mapped[list["BriefingItem"]] = relationship(
        "BriefingItem", back_populates="company", cascade="all, delete-orphan"
    )
    signal_events: Mapped[list["SignalEvent"]] = relationship(
        "SignalEvent", back_populates="company", passive_deletes=True
    )
    readiness_snapshots: Mapped[list["ReadinessSnapshot"]] = relationship(
        "ReadinessSnapshot", back_populates="company", cascade="all, delete-orphan"
    )
