from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.story import Story
from app.models.story_settings import StorySettings
from app.schemas.story import StoryCreate, StoryOut


router = APIRouter(prefix="/api/stories", tags=["stories"])


@router.post("", response_model=StoryOut)
def create_story(payload: StoryCreate, db: Session = Depends(get_db)) -> Story:
    story = Story(title=payload.title)
    settings = StorySettings(story=story)
    db.add(story)
    db.add(settings)
    db.commit()
    db.refresh(story)
    return story


@router.get("", response_model=list[StoryOut])
def list_stories(db: Session = Depends(get_db)) -> list[Story]:
    return list(db.scalars(select(Story).order_by(Story.updated_at.desc())).all())


@router.get("/{story_id}", response_model=StoryOut)
def get_story(story_id: str, db: Session = Depends(get_db)) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return story
