import asyncio
import logging
import httpx
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
logger = logging.getLogger(__name__)


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

    # user_input is appended separately in chat_story; drop the just-saved
    # user message from history to avoid sending the same utterance twice.
    if history and history[-1].id == user_message.id:
        history = history[:-1]

    generation_error: str | None = None
    dialogue = ""
    narration = ""
    last_exc: Exception | None = None
    retry_attempted = False
    for attempt in range(2):
        try:
            query_vector = await embed_text(payload.content)
            retrieved_context = await search_context(story_id=story_id, vector=query_vector, limit=5)

            dialogue, narration = await chat_story(
                story_settings=story_settings,
                llm_model=story.llm_model,
                history=history,
                user_input=payload.content,
                retrieved_context=retrieved_context,
            )
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                retry_attempted = True
                logger.info(
                    "Retrying chat generation story_id=%s branch_id=%s after error=%s",
                    story_id,
                    payload.branch_id,
                    exc,
                )
                await asyncio.sleep(0.7)
                continue

    if last_exc is not None:
        if isinstance(last_exc, httpx.ReadTimeout):
            generation_error = f"timeout(after-retry): {last_exc}"
            dialogue = "ごめん、いま応答生成に時間がかかりすぎています。少し待ってから再送するか、入力を短くして試してみてください。"
            narration = "湯けむりの向こうで、会話は一度途切れた。もう一度、落ち着いて言葉を選び直せば物語は続けられる。"
        elif isinstance(last_exc, httpx.HTTPError):
            generation_error = f"http-error(after-retry): {last_exc}"
            dialogue = "ごめん、いまAIモデルとの通信が不安定みたい。少し時間をおいて、もう一度送ってくれる？"
            narration = "通信が揺らぎ、物語はひと呼吸だけ足踏みした。"
        else:
            generation_error = f"unexpected(after-retry): {last_exc}"
            dialogue = "ごめん、いま返答を作る途中で問題が起きました。入力を少し変えてもう一度試してみてください。"
            narration = "物語の歯車が一瞬きしみ、場面は静かに止まった。"

    if generation_error is not None:
        logger.warning(
            "Chat generation fallback used story_id=%s branch_id=%s reason=%s retry_attempted=%s",
            story_id,
            payload.branch_id,
            generation_error,
            retry_attempted,
        )
    elif retry_attempted:
        logger.info(
            "Chat generation succeeded after retry story_id=%s branch_id=%s",
            story_id,
            payload.branch_id,
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
