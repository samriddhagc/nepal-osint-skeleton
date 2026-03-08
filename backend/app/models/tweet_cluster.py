"""TweetCluster model — groups semantically similar tweets."""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TweetCluster(Base):
    """Groups related tweets about the same event/topic."""

    __tablename__ = "tweet_clusters"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    representative_tweet_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    tweet_count: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[Optional[str]] = mapped_column(String(50))
    severity: Mapped[Optional[str]] = mapped_column(String(20))
    districts: Mapped[list] = mapped_column(JSONB, default=list)

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship to member tweets
    tweets = relationship("Tweet", back_populates="cluster", foreign_keys="Tweet.tweet_cluster_id")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "representative_tweet_id": str(self.representative_tweet_id) if self.representative_tweet_id else None,
            "tweet_count": self.tweet_count,
            "category": self.category,
            "severity": self.severity,
            "districts": self.districts or [],
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }
