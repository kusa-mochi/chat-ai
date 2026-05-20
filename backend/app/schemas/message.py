from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ChatSendIn(BaseModel):
    content: str
    branch_id: str = "main"
    parent_message_id: str | None = None


class MessageOut(ORMModel):
    id: str
    story_id: str
    branch_id: str
    parent_message_id: str | None
    role: str
    kind: str
    content: str
    created_at: datetime


class ChatSendOut(BaseModel):
    branch_id: str
    messages: list[MessageOut]


class MessageListOut(BaseModel):
    items: list[MessageOut]
    has_more: bool
    next_before_message_id: str | None = None


class BranchSummaryOut(BaseModel):
    branch_id: str
    message_count: int
    last_message_at: datetime | None
    is_active: bool


class BranchListOut(BaseModel):
    items: list[BranchSummaryOut]


class RewindIn(BaseModel):
    message_id: str
    new_branch_name: str | None = None


class RewindOut(BaseModel):
    new_branch_id: str
    from_message_id: str
    messages: list[MessageOut]


class MessageSearchIn(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)
