from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StorySettingsUpdate(BaseModel):
    context_size: int = Field(ge=512, le=32768)
    character_name: str
    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(ge=0, le=1)


class StorySettingsOut(ORMModel):
    story_id: str
    context_size: int
    character_name: str
    temperature: float
    top_p: float
