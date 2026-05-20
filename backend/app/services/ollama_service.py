import json
from typing import Iterable

import httpx

from app.config import settings
from app.models.message import Message
from app.models.story_settings import StorySettings


def _build_system_prompt(story_settings: StorySettings) -> str:
    return (
        "あなたは物語生成AIです。ユーザーの入力を受けて、日本語で物語を継続してください。\n"
        "あなたはユーザー以外の登場人物とナレーションを担当します。\n"
        "出力形式は必ず次の2つの見出しを含めてください。\n"
        "[dialogue]\n"
        "(登場人物のセリフ)\n"
        "[narration]\n"
        "(情景や行動の地の文)\n"
        f"登場人物名: {story_settings.character_name}\n"
        f"人格設定: {story_settings.character_persona}\n"
        f"追加プレプロンプト: {story_settings.preprompt}\n"
    )


def _history_to_messages(history: Iterable[Message]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for message in history:
        role = "assistant" if message.role == "assistant" else "user"
        items.append({"role": role, "content": message.content})
    return items


def _parse_dual_response(raw_text: str) -> tuple[str, str]:
    dialogue = ""
    narration = ""

    if "[dialogue]" in raw_text and "[narration]" in raw_text:
        parts = raw_text.split("[dialogue]", 1)[1]
        dialogue_part, narration_part = parts.split("[narration]", 1)
        dialogue = dialogue_part.strip()
        narration = narration_part.strip()
    else:
        dialogue = raw_text.strip()
        narration = ""

    return dialogue, narration


async def chat_story(
    story_settings: StorySettings,
    llm_model: str,
    history: Iterable[Message],
    user_input: str,
    retrieved_context: list[str],
) -> tuple[str, str]:
    base_messages = [{"role": "system", "content": _build_system_prompt(story_settings)}]

    if retrieved_context:
        base_messages.append(
            {
                "role": "system",
                "content": "過去の関連文脈:\n" + "\n---\n".join(retrieved_context),
            }
        )

    base_messages.extend(_history_to_messages(history))
    base_messages.append({"role": "user", "content": user_input})

    payload = {
        "model": llm_model or settings.ollama_chat_model,
        "messages": base_messages,
        "stream": False,
        "options": {
            "temperature": story_settings.temperature,
            "top_p": story_settings.top_p,
            "num_ctx": story_settings.context_size,
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

    raw_text = data.get("message", {}).get("content", "")
    return _parse_dual_response(raw_text)


async def embed_text(text: str) -> list[float]:
    payload = {
        "model": settings.ollama_embedding_model,
        "prompt": text,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{settings.ollama_base_url}/api/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()

    embedding = data.get("embedding")
    if embedding is None:
        raise ValueError("Embedding was not returned by Ollama")

    if isinstance(embedding, str):
        embedding = json.loads(embedding)

    return embedding
