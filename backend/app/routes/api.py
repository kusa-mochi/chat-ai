from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import get_settings
from app.database import get_db

router = APIRouter(prefix=get_settings().api_prefix)


def _get_story_or_404(db: Session, story_id: str) -> models.Story:
    story = db.get(models.Story, story_id)
    if not story:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return story


def _next_turn_index(db: Session, story_id: str) -> int:
    max_turn = db.query(func.max(models.StoryEntry.turn_index)).filter(models.StoryEntry.story_id == story_id).scalar()
    return int(max_turn or 0) + 1


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/stories", response_model=schemas.StoryDetailResponse)
def create_story(payload: schemas.StoryCreateRequest, db: Session = Depends(get_db)) -> schemas.StoryDetailResponse:
    title = payload.title.strip() if payload.title else f"新しい物語 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    story = models.Story(title=title)
    db.add(story)
    db.flush()

    story_settings = models.StorySetting(story_id=story.id)
    db.add(story_settings)
    db.commit()
    db.refresh(story)
    db.refresh(story_settings)
    return schemas.StoryDetailResponse(story=story, settings=story_settings)


@router.get("/stories", response_model=list[schemas.StorySummary])
def list_stories(db: Session = Depends(get_db)) -> list[models.Story]:
    return db.query(models.Story).order_by(models.Story.updated_at.desc()).all()


@router.get("/stories/{story_id}", response_model=schemas.StoryDetailResponse)
def get_story(story_id: str, db: Session = Depends(get_db)) -> schemas.StoryDetailResponse:
    story = _get_story_or_404(db, story_id)
    return schemas.StoryDetailResponse(story=story, settings=story.settings)


@router.get("/stories/{story_id}/settings", response_model=schemas.StorySettingResponse)
def get_story_settings(story_id: str, db: Session = Depends(get_db)) -> models.StorySetting:
    story = _get_story_or_404(db, story_id)
    return story.settings


@router.put("/stories/{story_id}/settings", response_model=schemas.StorySettingResponse)
def update_story_settings(
    story_id: str,
    payload: schemas.StorySettingUpdateRequest,
    db: Session = Depends(get_db),
) -> models.StorySetting:
    story = _get_story_or_404(db, story_id)
    settings_obj = story.settings
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(settings_obj, key, value)
    story.updated_at = datetime.now(timezone.utc)
    db.add(story)
    db.add(settings_obj)
    db.commit()
    db.refresh(settings_obj)
    return settings_obj


@router.get("/stories/{story_id}/entries", response_model=schemas.HistoryResponse)
def list_story_entries(
    story_id: str,
    limit: int = 100,
    before_entry_id: int | None = None,
    db: Session = Depends(get_db),
) -> schemas.HistoryResponse:
    _get_story_or_404(db, story_id)
    limit = max(1, min(limit, 300))

    query = db.query(models.StoryEntry).filter(
        and_(models.StoryEntry.story_id == story_id, models.StoryEntry.is_active.is_(True))
    )
    if before_entry_id is not None:
        query = query.filter(models.StoryEntry.id < before_entry_id)

    items = query.order_by(models.StoryEntry.id.desc()).limit(limit).all()
    items.reverse()
    return schemas.HistoryResponse(items=items)


@router.post("/stories/{story_id}/chat", response_model=schemas.ChatResponse)
def create_chat_turn(
    story_id: str,
    payload: schemas.ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> schemas.ChatResponse:
    story = _get_story_or_404(db, story_id)
    ai_service = request.app.state.ai_service
    vector_store = request.app.state.vector_store
    settings = get_settings()

    user_turn_index = _next_turn_index(db, story_id)
    user_entry = models.StoryEntry(
        story_id=story_id,
        role="user",
        content=payload.message,
        turn_index=user_turn_index,
        is_active=True,
    )
    db.add(user_entry)
    db.flush()

    recent_entries = (
        db.query(models.StoryEntry)
        .filter(and_(models.StoryEntry.story_id == story_id, models.StoryEntry.is_active.is_(True)))
        .order_by(models.StoryEntry.turn_index.desc())
        .limit(story.settings.context_size)
        .all()
    )
    recent_entries.reverse()

    query_vector = ai_service.embed_text(payload.message)
    semantic_entries = vector_store.search_by_story(
        story_id=story_id,
        query_vector=query_vector,
        limit=min(settings.semantic_search_limit, story.settings.context_size),
    )

    ai_turn = ai_service.generate_turn(
        story_title=story.title,
        story_settings=story.settings,
        recent_entries=recent_entries,
        semantic_entries=semantic_entries,
        user_message=payload.message,
    )

    ai_dialogue_entry = models.StoryEntry(
        story_id=story_id,
        role="ai_character",
        content=ai_turn.dialogue,
        turn_index=user_turn_index + 1,
        parent_entry_id=user_entry.id,
        is_active=True,
    )
    narration_entry = models.StoryEntry(
        story_id=story_id,
        role="narration",
        content=ai_turn.narration,
        turn_index=user_turn_index + 2,
        parent_entry_id=user_entry.id,
        is_active=True,
    )

    db.add(ai_dialogue_entry)
    db.add(narration_entry)
    story.updated_at = datetime.now(timezone.utc)
    db.add(story)
    db.commit()
    db.refresh(user_entry)
    db.refresh(ai_dialogue_entry)
    db.refresh(narration_entry)

    vector_store.upsert_entry(
        story_id=story_id,
        entry_id=user_entry.id,
        role=user_entry.role,
        content=user_entry.content,
        vector=query_vector,
        is_active=True,
    )
    vector_store.upsert_entry(
        story_id=story_id,
        entry_id=ai_dialogue_entry.id,
        role=ai_dialogue_entry.role,
        content=ai_dialogue_entry.content,
        vector=ai_service.embed_text(ai_dialogue_entry.content),
        is_active=True,
    )
    vector_store.upsert_entry(
        story_id=story_id,
        entry_id=narration_entry.id,
        role=narration_entry.role,
        content=narration_entry.content,
        vector=ai_service.embed_text(narration_entry.content),
        is_active=True,
    )

    return schemas.ChatResponse(
        user_entry=user_entry,
        ai_dialogue_entry=ai_dialogue_entry,
        narration_entry=narration_entry,
    )


@router.post("/stories/{story_id}/rewind", response_model=schemas.RewindResponse)
def rewind_story(
    story_id: str,
    payload: schemas.RewindRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> schemas.RewindResponse:
    _get_story_or_404(db, story_id)
    target = (
        db.query(models.StoryEntry)
        .filter(
            and_(
                models.StoryEntry.story_id == story_id,
                models.StoryEntry.id == payload.entry_id,
                models.StoryEntry.is_active.is_(True),
            )
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target entry not found")

    entries = (
        db.query(models.StoryEntry)
        .filter(
            and_(
                models.StoryEntry.story_id == story_id,
                models.StoryEntry.id > payload.entry_id,
                models.StoryEntry.is_active.is_(True),
            )
        )
        .all()
    )
    deactivate_ids = [entry.id for entry in entries]

    if deactivate_ids:
        (
            db.query(models.StoryEntry)
            .filter(models.StoryEntry.id.in_(deactivate_ids))
            .update({models.StoryEntry.is_active: False}, synchronize_session=False)
        )

    story = _get_story_or_404(db, story_id)
    story.updated_at = datetime.now(timezone.utc)
    db.add(story)
    db.commit()

    request.app.state.vector_store.set_entries_active(deactivate_ids, is_active=False)
    return schemas.RewindResponse(deactivated_entry_ids=deactivate_ids)


@router.post("/stories/{story_id}/images", response_model=schemas.ImageResponse)
def generate_image(
    story_id: str,
    payload: schemas.ImageGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> models.GeneratedImage:
    story = _get_story_or_404(db, story_id)

    if payload.source_entry_id is not None:
        entry = (
            db.query(models.StoryEntry)
            .filter(
                and_(
                    models.StoryEntry.id == payload.source_entry_id,
                    models.StoryEntry.story_id == story_id,
                    models.StoryEntry.is_active.is_(True),
                )
            )
            .first()
        )
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source entry not found")

    ai_service = request.app.state.ai_service
    image_service = request.app.state.image_service
    prompt = ai_service.build_image_prompt(payload.source_text, story.settings)
    image_url = image_service.generate_image(prompt=prompt, source_text=payload.source_text)

    image = models.GeneratedImage(
        story_id=story_id,
        source_entry_id=payload.source_entry_id,
        source_text=payload.source_text,
        prompt=prompt,
        image_url=image_url,
        status="ready",
    )
    db.add(image)
    story.updated_at = datetime.now(timezone.utc)
    db.add(story)
    db.commit()
    db.refresh(image)
    return image


@router.get("/stories/{story_id}/images", response_model=list[schemas.ImageResponse])
def list_images(story_id: str, db: Session = Depends(get_db)) -> list[models.GeneratedImage]:
    _get_story_or_404(db, story_id)
    return (
        db.query(models.GeneratedImage)
        .filter(models.GeneratedImage.story_id == story_id)
        .order_by(models.GeneratedImage.created_at.desc())
        .all()
    )
