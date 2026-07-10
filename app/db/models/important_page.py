from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import ImportantPageType

if TYPE_CHECKING:
    from app.db.models.website import Website


class ImportantPage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "important_pages"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        UniqueConstraint(
            "website_id", "page_type", "url", name="uq_important_pages_website_type_url"
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_type: Mapped[ImportantPageType] = mapped_column(
        Enum(
            ImportantPageType,
            name="important_page_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    website: Mapped[Website] = relationship(back_populates="important_pages")
