from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.page import Page


class Link(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "links"

    source_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_target_url: Mapped[str] = mapped_column(Text, nullable=False)
    link_text: Mapped[str | None] = mapped_column(String(1024))
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_broken: Mapped[bool | None] = mapped_column(Boolean)
    status_code: Mapped[int | None] = mapped_column(Integer)

    source_page: Mapped[Page] = relationship(back_populates="links")
