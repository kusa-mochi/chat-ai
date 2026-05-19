from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

EntryRole = Literal["user", "ai_character", "narration"]


class StoryCreateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class StorySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class StorySettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    story_id: str
    context_size: int
    pre_prompt: str
    ai_character_name: str
    ai_persona: str
    temperature: float


class StorySettingUpdateRequest(BaseModel):
    context_size: Optional[int] = Field(default=None, ge=5, le=200)
    pre_prompt: Optional[str] = None
    ai_character_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    ai_persona: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class StoryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: str
    role: EntryRole
    content: str
    turn_index: int
    is_active: bool
    parent_entry_id: Optional[int]
    created_at: datetime


class StoryDetailResponse(BaseModel):
    story: StorySummary
    settings: StorySettingResponse


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    user_entry: StoryEntryResponse
    ai_dialogue_entry: StoryEntryResponse
    narration_entry: StoryEntryResponse


class RewindRequest(BaseModel):
    entry_id: int


class RewindResponse(BaseModel):
    deactivated_entry_ids: list[int]


class ImageGenerateRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=4000)
    source_entry_id: Optional[int] = None


class ImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: str
    source_entry_id: Optional[int]
    source_text: str
    prompt: str
    image_url: str
    status: str
    created_at: datetime


class HistoryResponse(BaseModel):
    items: list[StoryEntryResponse]
