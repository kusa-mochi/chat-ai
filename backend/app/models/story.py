import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    active_branch_id: Mapped[str] = mapped_column(String(36), nullable=False, default="main")
    llm_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="qwen2.5-7b-instruct-uncensored-q4km:latest"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    settings = relationship("StorySettings", back_populates="story", uselist=False, cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="story", cascade="all, delete-orphan")
    illustration_jobs = relationship("IllustrationJob", back_populates="story", cascade="all, delete-orphan")
