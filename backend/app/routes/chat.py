from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.message import Message
from app.models.story import Story
from app.models.story_settings import StorySettings
from app.schemas.message import ChatSendIn, ChatSendOut, MessageListOut, MessageOut
from app.services.ollama_service import chat_story, embed_text
from app.services.vector_service import search_context, upsert_context


router = APIRouter(prefix="/api/stories/{story_id}", tags=["chat"])


@router.get("/messages", response_model=MessageListOut)
def list_messages(
    story_id: str,
    branch_id: str = "main",
    limit: int = 40,
    before_message_id: str | None = None,
    db: Session = Depends(get_db),
) -> MessageListOut:
    limit = max(1, min(limit, 200))

    query = select(Message).where(Message.story_id == story_id, Message.branch_id == branch_id)

    if before_message_id is not None:
        pivot = db.get(Message, before_message_id)
        if pivot is None or pivot.story_id != story_id or pivot.branch_id != branch_id:
            raise HTTPException(status_code=404, detail="Pivot message not found")
        query = query.where(Message.created_at < pivot.created_at)

    items_desc = list(db.scalars(query.order_by(Message.created_at.desc()).limit(limit + 1)).all())
    has_more = len(items_desc) > limit
    if has_more:
        items_desc = items_desc[:limit]

    items = list(reversed(items_desc))
    next_before_message_id = items[0].id if has_more and items else None
    return MessageListOut(
        items=[MessageOut.model_validate(item) for item in items],
        has_more=has_more,
        next_before_message_id=next_before_message_id,
    )


@router.post("/chat", response_model=ChatSendOut)
async def send_chat(story_id: str, payload: ChatSendIn, db: Session = Depends(get_db)) -> ChatSendOut:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    story.active_branch_id = payload.branch_id

    story_settings = db.scalar(select(StorySettings).where(StorySettings.story_id == story_id))
    if story_settings is None:
        story_settings = StorySettings(story_id=story_id)
        db.add(story_settings)
        db.flush()

    user_message = Message(
        story_id=story_id,
        branch_id=payload.branch_id,
        parent_message_id=payload.parent_message_id,
        role="user",
        kind="user",
        content=payload.content,
    )
    db.add(user_message)
    db.flush()

    history = list(
        db.scalars(
            select(Message)
            .where(Message.story_id == story_id, Message.branch_id == payload.branch_id)
            .order_by(Message.created_at.desc())
            .limit(30)
        ).all()
    )
    history.reverse()

    query_vector = await embed_text(payload.content)
    retrieved_context = await search_context(story_id=story_id, vector=query_vector, limit=5)

    dialogue, narration = await chat_story(
        story_settings=story_settings,
        llm_model=story.llm_model,
        history=history,
        user_input=payload.content,
        retrieved_context=retrieved_context,
    )

    dialogue_message = Message(
        story_id=story_id,
        branch_id=payload.branch_id,
        parent_message_id=user_message.id,
        role="assistant",
        kind="dialogue",
        content=dialogue,
    )
    db.add(dialogue_message)
    db.flush()

    result_messages = [user_message, dialogue_message]

    if narration:
        narration_message = Message(
            story_id=story_id,
            branch_id=payload.branch_id,
            parent_message_id=dialogue_message.id,
            role="assistant",
            kind="narration",
            content=narration,
        )
        db.add(narration_message)
        db.flush()
        result_messages.append(narration_message)

    db.commit()

    for item in result_messages:
        try:
            vector = await embed_text(item.content)
            await upsert_context(
                story_id=item.story_id,
                branch_id=item.branch_id,
                message_id=item.id,
                role=item.role,
                kind=item.kind,
                content=item.content,
                vector=vector,
            )
        except Exception:
            # Vector ingestion failures should not block chat continuation.
            pass

    return ChatSendOut(
        branch_id=payload.branch_id,
        messages=[MessageOut.model_validate(item) for item in result_messages],
    )
