"""CompanyAlias model for entity resolution and deduplication."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class CompanyAlias(Base):
    """Alternate names, domains, URLs for company deduplication."""

    __tablename__ = "company_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)  # name, domain, url, social
    alias_value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    company: Mapped["Company"] = relationship("Company", back_populates="aliases")
