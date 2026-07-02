import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


DEFAULT_CHARACTERS_TEXT = """シャルロット: グレイシア第一王女、氷魔法、17歳女、第2席、ツンデレ、素直になれない好意、序列とプライドに執着、決闘口実でユーザー接触
リリア: ローベルト第一王女留学生、風魔法、17歳女、第3席、明るく社交的、フレンドリーな好意、知的な話し方
ロロ: グレイシア貴族令嬢、闇魔法、14歳女、第4席、無口ミステリアス、ユーザーにだけ懐く、観察力高い、影ある話し方
アーサー: グレイシア第一王子、炎魔法、16歳男、第5席、シャルロットの弟、シスコン、ユーザー警戒、姉を奪われる恐怖、ぎこちない話し方"""


class StorySettings(Base):
    __tablename__ = "story_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id", ondelete="CASCADE"), unique=True)

    context_size: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    character_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    characters_text: Mapped[str] = mapped_column(String(4000), default=DEFAULT_CHARACTERS_TEXT, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    top_p: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    story = relationship("Story", back_populates="settings")
