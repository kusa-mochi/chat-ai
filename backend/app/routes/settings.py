from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.story import Story
from app.models.story_settings import StorySettings
from app.schemas.settings import StorySettingsOut, StorySettingsUpdate


router = APIRouter(prefix="/api/stories/{story_id}/settings", tags=["settings"])


@router.get("", response_model=StorySettingsOut)
def get_story_settings(story_id: str, db: Session = Depends(get_db)) -> StorySettings:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    settings = db.scalar(select(StorySettings).where(StorySettings.story_id == story_id))
    if settings is None:
        settings = StorySettings(story_id=story_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.put("", response_model=StorySettingsOut)
def update_story_settings(
    story_id: str,
    payload: StorySettingsUpdate,
    db: Session = Depends(get_db),
) -> StorySettings:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    settings = db.scalar(select(StorySettings).where(StorySettings.story_id == story_id))
    if settings is None:
        settings = StorySettings(story_id=story_id)
        db.add(settings)

    settings.context_size = payload.context_size
    settings.character_name = payload.character_name
    settings.temperature = payload.temperature
    settings.top_p = payload.top_p

    db.commit()
    db.refresh(settings)
    return settings
