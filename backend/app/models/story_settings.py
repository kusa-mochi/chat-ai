import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StorySettings(Base):
    __tablename__ = "story_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id", ondelete="CASCADE"), unique=True)

    context_size: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    preprompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    character_name: Mapped[str] = mapped_column(String(80), default="語り部の相棒", nullable=False)
    character_persona: Mapped[str] = mapped_column(
        Text,
        default="親密で文学的、比喩を交えつつ物語を前へ進める。",
        nullable=False,
    )
    temperature: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)
    top_p: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)

    story = relationship("Story", back_populates="settings")
