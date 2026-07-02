import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.message import Message
from app.models.story import Story
from app.models.story_settings import StorySettings
from app.schemas.story import StoryCreate, StoryOut
from app.services.ollama_service import generate_story_opening


router = APIRouter(prefix="/api/stories", tags=["stories"])
logger = logging.getLogger(__name__)


@router.post("", response_model=StoryOut)
async def create_story(payload: StoryCreate, db: Session = Depends(get_db)) -> Story:
    story = Story(title=payload.title, llm_model=settings.ollama_chat_model)
    story_settings = StorySettings(story=story)

    db.add(story)
    db.add(story_settings)
    db.flush()

    speakers: list[tuple[str, str]] = []
    narration = ""
    try:
        speakers, narration = await generate_story_opening(story_settings=story_settings, llm_model=story.llm_model)
    except Exception as exc:
        logger.warning("Opening generation failed story_id=%s error=%s", story.id, exc)

    parent_message_id: str | None = None
    for speaker_name, line in speakers:
        opening_dialogue = Message(
            story_id=story.id,
            branch_id=story.active_branch_id,
            parent_message_id=parent_message_id,
            role="assistant",
            kind="dialogue",
            speaker_name=speaker_name,
            content=line,
        )
        db.add(opening_dialogue)
        db.flush()
        parent_message_id = str(opening_dialogue.id)

    if narration:
        opening_narration = Message(
            story_id=story.id,
            branch_id=story.active_branch_id,
            parent_message_id=parent_message_id,
            role="assistant",
            kind="narration",
            content=narration,
        )
        db.add(opening_narration)
    elif not speakers:
        fallback_opening = Message(
            story_id=story.id,
            branch_id=story.active_branch_id,
            parent_message_id=None,
            role="assistant",
            kind="narration",
            content="朝靄の学園都市に鐘が響き、物語はゆっくり幕を開けた。",
        )
        db.add(fallback_opening)

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
