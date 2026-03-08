"""User model for authentication and authorization."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserRole(str, Enum):
    """User role enum for RBAC."""
    CONSUMER = "consumer"
    ANALYST = "analyst"
    DEV = "dev"


class User(Base, TimestampMixin):
    """User model for authentication."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(30),
        unique=True,
        index=True,
        nullable=True,
    )
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )
    auth_provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="local",
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    role: Mapped[UserRole] = mapped_column(
        ENUM(
            UserRole,
            name="user_role",
            create_type=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=UserRole.CONSUMER,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role.value}) [{self.auth_provider}]>"

    def has_role(self, *roles: UserRole) -> bool:
        """Check if user has one of the specified roles."""
        return self.role in roles

    def is_analyst_or_above(self) -> bool:
        """Check if user has analyst or dev role."""
        return self.role in (UserRole.ANALYST, UserRole.DEV)

    def is_dev(self) -> bool:
        """Check if user has dev role."""
        return self.role == UserRole.DEV
