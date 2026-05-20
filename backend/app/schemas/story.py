from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class StoryCreate(BaseModel):
    title: str


class StoryOut(ORMModel):
    id: str
    title: str
    active_branch_id: str
    llm_model: str
    created_at: datetime
    updated_at: datetime
