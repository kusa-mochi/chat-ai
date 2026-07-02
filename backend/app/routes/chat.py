import asyncio
import json
import logging
from typing import Awaitable, Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.message import Message
from app.models.story import Story
from app.models.story_settings import StorySettings
from app.schemas.message import ChatSendIn, ChatSendOut, MessageListOut, MessageOut
from app.services.ollama_service import chat_story, chat_story_stream, embed_text
from app.services.vector_service import search_context, upsert_context


router = APIRouter(prefix="/api/stories/{story_id}", tags=["chat"])
logger = logging.getLogger(__name__)


def _format_sse(event: str, data: str) -> str:
    lines = data.splitlines() or [""]
    data_lines = "\n".join(f"data: {line}" for line in lines)
    return f"event: {event}\n{data_lines}\n\n"


def _resolve_generation_error(last_exc: Exception | None) -> tuple[str | None, list[tuple[str, str]], str]:
    if last_exc is None:
        return None, [], ""

    if isinstance(last_exc, httpx.ReadTimeout):
        generation_error = f"timeout(after-retry): {last_exc}"
        narration = "エラー：ウップス！物語の神様がちょっと居眠りしてしまったようです。しばらくしてからもう一度お試しください。"
        return generation_error, [], narration

    if isinstance(last_exc, httpx.HTTPError):
        generation_error = f"http-error(after-retry): {last_exc}"
        narration = "エラー：ウップス！通信の神様がちょっと具合が悪いようです。しばらくしてからもう一度お試しください。"
        return generation_error, [], narration

    generation_error = f"unexpected(after-retry): {last_exc}"
    narration = "物語の歯車が一瞬だけ軋み、場面は静かに止まった。"
    return generation_error, [], narration


async def _generate_speakers_and_narration(
    *,
    story_id: str,
    branch_id: str,
    story_settings: StorySettings,
    llm_model: str,
    history: list[Message],
    user_input: str,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[list[tuple[str, str]], str, str | None, bool, list[float] | None]:
    speakers: list[tuple[str, str]] = []
    narration = ""
    generation_error: str | None = None
    last_exc: Exception | None = None
    retry_attempted = False
    query_vector: list[float] | None = None
    retrieved_context: list[str] | None = None

    for attempt in range(2):
        try:
            if query_vector is None:
                query_vector = await embed_text(user_input)
            if retrieved_context is None:
                retrieved_context = await search_context(story_id=story_id, vector=query_vector, limit=5)

            if on_chunk is None:
                speakers, narration = await chat_story(
                    story_settings=story_settings,
                    llm_model=llm_model,
                    history=history,
                    user_input=user_input,
                    retrieved_context=retrieved_context,
                )
            else:
                speakers, narration = await chat_story_stream(
                    story_settings=story_settings,
                    llm_model=llm_model,
                    history=history,
                    user_input=user_input,
                    retrieved_context=retrieved_context,
                    on_chunk=on_chunk,
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
                    branch_id,
                    exc,
                )
                await asyncio.sleep(0.7)
                continue

    generation_error, fallback_speakers, fallback_narration = _resolve_generation_error(last_exc)
    if generation_error is not None:
        speakers = fallback_speakers
        narration = fallback_narration

    return speakers, narration, generation_error, retry_attempted, query_vector


async def _index_single_message_context(message: dict, precomputed_vector: list[float] | None = None) -> None:
    content = str(message.get("content") or "")
    if not content:
        return

    vector = precomputed_vector if precomputed_vector is not None else await embed_text(content)
    await upsert_context(
        story_id=str(message.get("story_id") or ""),
        branch_id=str(message.get("branch_id") or ""),
        message_id=str(message.get("id") or ""),
        role=str(message.get("role") or ""),
        kind=str(message.get("kind") or ""),
        speaker_name=str(message.get("speaker_name") or ""),
        content=content,
        vector=vector,
    )


async def _index_messages_context(
    messages: list[dict],
    *,
    user_message_id: str | None = None,
    user_vector: list[float] | None = None,
) -> None:
    if not messages:
        return

    tasks: list[Awaitable[None]] = []
    for message in messages:
        message_id = str(message.get("id") or "")
        precomputed_vector = user_vector if user_vector is not None and message_id == user_message_id else None
        tasks.append(_index_single_message_context(message, precomputed_vector=precomputed_vector))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            # Vector ingestion failures should not block chat continuation.
            pass


def _create_assistant_messages(
    *,
    db: Session,
    story_id: str,
    branch_id: str,
    initial_parent_message_id: str,
    speakers: list[tuple[str, str]],
    narration: str,
) -> list[Message]:
    result_messages: list[Message] = []
    parent_message_id = initial_parent_message_id

    for speaker_name, line in speakers:
        dialogue_message = Message(
            story_id=story_id,
            branch_id=branch_id,
            parent_message_id=parent_message_id,
            role="assistant",
            kind="dialogue",
            speaker_name=speaker_name,
            content=line,
        )
        db.add(dialogue_message)
        db.flush()
        result_messages.append(dialogue_message)
        parent_message_id = str(dialogue_message.id)

    if narration:
        narration_message = Message(
            story_id=story_id,
            branch_id=branch_id,
            parent_message_id=parent_message_id,
            role="assistant",
            kind="narration",
            content=narration,
        )
        db.add(narration_message)
        db.flush()
        result_messages.append(narration_message)

    return result_messages


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
    user_message_id = str(user_message.id)

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

    speakers, narration, generation_error, retry_attempted, user_query_vector = await _generate_speakers_and_narration(
        story_id=story_id,
        branch_id=payload.branch_id,
        story_settings=story_settings,
        llm_model=story.llm_model,
        history=history,
        user_input=payload.content,
    )

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

    assistant_messages = _create_assistant_messages(
        db=db,
        story_id=story_id,
        branch_id=payload.branch_id,
        initial_parent_message_id=str(user_message.id),
        speakers=speakers,
        narration=narration,
    )
    result_messages = [user_message, *assistant_messages]

    result_payload_messages = [
        MessageOut.model_validate(result_message).model_dump(mode="json")
        for result_message in result_messages
    ]

    db.commit()

    await _index_messages_context(
        result_payload_messages,
        user_message_id=user_message_id,
        user_vector=user_query_vector,
    )

    return ChatSendOut(
        branch_id=payload.branch_id,
        messages=[MessageOut.model_validate(item) for item in result_payload_messages],
    )


@router.post("/chat/stream")
async def send_chat_stream_sse(
    story_id: str,
    payload: ChatSendIn,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    llm_model = story.llm_model

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
    user_message_id = str(user_message.id)
    user_message_payload = MessageOut.model_validate(user_message).model_dump(mode="json")

    generation_settings = StorySettings(
        story_id=story_id,
        context_size=story_settings.context_size,
        characters_text=story_settings.characters_text,
        temperature=story_settings.temperature,
        top_p=story_settings.top_p,
    )

    # Persist the parent message before streaming generation starts.
    # This avoids FK violations when assistant messages reference user_message_id.
    db.commit()

    history = list(
        db.scalars(
            select(Message)
            .where(Message.story_id == story_id, Message.branch_id == payload.branch_id)
            .order_by(Message.created_at.desc())
            .limit(30)
        ).all()
    )
    history.reverse()

    if history and history[-1].id == user_message_id:
        history = history[:-1]

    context_state: dict[str, list[float] | None] = {"user_query_vector": None}

    queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

    async def push_event(event: str, data: str) -> None:
        await queue.put((event, data))

    async def worker() -> None:
        try:
            async def on_chunk(chunk: str) -> None:
                await push_event("delta", chunk)

            speakers, narration, generation_error, retry_attempted, user_query_vector = await _generate_speakers_and_narration(
                story_id=story_id,
                branch_id=payload.branch_id,
                story_settings=generation_settings,
                llm_model=llm_model,
                history=history,
                user_input=payload.content,
                on_chunk=on_chunk,
            )
            context_state["user_query_vector"] = user_query_vector
            await push_event(
                "generated",
                json.dumps(
                    {
                        "speakers": [{"name": name, "line": line} for name, line in speakers],
                        "narration": narration,
                        "generation_error": generation_error,
                        "retry_attempted": retry_attempted,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.exception("SSE chat failed story_id=%s branch_id=%s", story_id, payload.branch_id)
            await push_event("error", json.dumps({"message": "送信に失敗しました", "detail": str(exc)}, ensure_ascii=False))
        finally:
            await queue.put(None)

    async def event_stream():
        task = asyncio.create_task(worker())
        try:
            yield _format_sse(
                "user",
                json.dumps(user_message_payload, ensure_ascii=False),
            )

            while True:
                item = await queue.get()
                if item is None:
                    break

                event, data = item
                if event == "generated":
                    generated = json.loads(data)
                    speakers_payload = generated.get("speakers")
                    narration = str(generated.get("narration") or "")
                    generation_error = generated.get("generation_error")
                    retry_attempted = bool(generated.get("retry_attempted"))

                    speakers: list[tuple[str, str]] = []
                    if isinstance(speakers_payload, list):
                        for item in speakers_payload:
                            if not isinstance(item, dict):
                                continue
                            name = str(item.get("name") or "").strip()
                            line = str(item.get("line") or "").strip()
                            if not name or not line:
                                continue
                            speakers.append((name, line))

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

                    try:
                        assistant_messages = _create_assistant_messages(
                            db=db,
                            story_id=story_id,
                            branch_id=payload.branch_id,
                            initial_parent_message_id=user_message_id,
                            speakers=speakers,
                            narration=narration,
                        )
                        persisted_user = db.get(Message, user_message_id)
                        if persisted_user is None:
                            raise RuntimeError("Failed to load persisted user message")

                        result_messages = [persisted_user, *assistant_messages]

                        result_payload_messages = [
                            MessageOut.model_validate(result_message).model_dump(mode="json")
                            for result_message in result_messages
                        ]

                        db.commit()

                        await _index_messages_context(
                            result_payload_messages,
                            user_message_id=user_message_id,
                            user_vector=context_state.get("user_query_vector"),
                        )

                        result = {
                            "branch_id": payload.branch_id,
                            "messages": result_payload_messages,
                        }
                        yield _format_sse("done", json.dumps(result, ensure_ascii=False))
                    except Exception as exc:
                        db.rollback()
                        logger.exception("Failed to persist streamed chat story_id=%s branch_id=%s", story_id, payload.branch_id)
                        yield _format_sse(
                            "error",
                            json.dumps({"message": "送信に失敗しました", "detail": str(exc)}, ensure_ascii=False),
                        )
                    continue

                yield _format_sse(event, data)
        finally:
            if not task.done():
                task.cancel()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
