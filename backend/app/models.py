from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    settings: Mapped["StorySetting"] = relationship(back_populates="story", uselist=False, cascade="all, delete-orphan")
    entries: Mapped[list["StoryEntry"]] = relationship(back_populates="story", cascade="all, delete-orphan")
    images: Mapped[list["GeneratedImage"]] = relationship(back_populates="story", cascade="all, delete-orphan")


class StorySetting(Base):
    __tablename__ = "story_settings"

    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True)
    context_size: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    pre_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_character_name: Mapped[str] = mapped_column(String(80), nullable=False, default="語り手")
    ai_persona: Mapped[str] = mapped_column(Text, nullable=False, default="落ち着いた語り口で、場面描写を丁寧に行う。")
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)

    story: Mapped[Story] = relationship(back_populates="settings")


class StoryEntry(Base):
    __tablename__ = "story_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    parent_entry_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("story_entries.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    story: Mapped[Story] = relationship(back_populates="entries")


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    source_entry_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("story_entries.id", ondelete="SET NULL"), nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    story: Mapped[Story] = relationship(back_populates="images")
