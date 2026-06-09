import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StorySettings(Base):
    __tablename__ = "story_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id", ondelete="CASCADE"), unique=True)

    context_size: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    character_name: Mapped[str] = mapped_column(String(80), default="シャルロット", nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    top_p: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    story = relationship("Story", back_populates="settings")
