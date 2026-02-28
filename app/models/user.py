"""User model."""

from datetime import UTC, datetime

import bcrypt as _bcrypt
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class User(Base):
    """Application user for authentication."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    def set_password(self, password: str) -> None:
        """Hash and store password using bcrypt."""
        self.password_hash = _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode(
            "utf-8"
        )

    def verify_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return _bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))
