from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class IllustrationCreateIn(BaseModel):
    source_text: str
    message_id: str | None = None


class IllustrationOut(ORMModel):
    id: str
    story_id: str
    message_id: str | None
    source_text: str
    status: str
    image_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
