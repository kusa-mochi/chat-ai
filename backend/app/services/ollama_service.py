import asyncio
import json
import re
from typing import Iterable

import httpx

from app.config import settings
from app.models.message import Message
from app.models.story_settings import StorySettings


def _build_system_prompt(story_settings: StorySettings) -> str:
    return (
        "あなたは物語生成AIです。ユーザーの入力を受けて、日本語で物語を継続してください。\n"
        "あなたはユーザー以外の登場人物とナレーションを担当します。\n"
        "最重要: [dialogue] では登場人物名として自然な話し言葉で返答してください。\n"
        "ユーザーの直前の問いや依頼に、まず短く直接答えてください。\n"
        "ユーザー発話の言い換え・要約・採点・選択肢問題化は禁止です。\n"
        "『という問いは』『想像上のシチュエーション』のような解説文で始めないでください。\n"
        "説明口調・翻訳調・ガイド口調は禁止です。\n"
        "出力形式は必ず次の2つの見出しを含めてください。\n"
        "[dialogue]\n"
        "(登場人物のセリフのみ。地の文や解説は書かない)\n"
        "[narration]\n"
        "(情景や行動の地の文。不要なら空で可)\n"
        f"登場人物名: {story_settings.character_name}\n"
        f"人格設定: {story_settings.character_persona}\n"
        f"追加プレプロンプト: {story_settings.preprompt}\n"
    )


def _history_to_messages(history: Iterable[Message]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for message in history:
        if message.role != "assistant":
            items.append({"role": "user", "content": message.content})
            continue

        if message.kind == "dialogue":
            content = f"[dialogue]\n{message.content}\n[narration]\n"
        elif message.kind == "narration":
            content = f"[dialogue]\n\n[narration]\n{message.content}"
        else:
            content = message.content
        items.append({"role": "assistant", "content": content})
    return items


def _fallback_dialogue(user_input: str) -> str:
    if "?" in user_input or "？" in user_input:
        return "うん、できる範囲で答えるね。もう少し詳しく教えて。"
    return "ごめんね、もう少し詳しく教えてくれる？"


def _looks_like_meta_text(text: str) -> bool:
    markers = (
        "この文章を",
        "文章にした",
        "日本語の文章",
        "以下は",
        "結論",
        "台詞を",
        "翻訳",
        "英語",
        "You are",
        "helpful assistant",
        "meaning",
        "という問い",
        "推測すると",
        "想像上のシチュエーション",
        "最も適切",
        "選んでください",
        "選択肢",
        "答案",
        "解説",
        "文脈から",
    )
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _normalize_text_for_compare(text: str) -> str:
    lowered = text.strip().lower()
    return re.sub(r"[\s\-_.!！?？'\"「」『』:：、。,]", "", lowered)


def _contains_japanese(text: str) -> bool:
    return re.search(r"[ぁ-んァ-ン一-龯]", text) is not None


def _looks_like_choice_or_template(text: str) -> bool:
    if re.search(r"(?m)^[A-EＡ-Ｅ][\.:\)]\s", text):
        return True
    if "[解説]" in text or "[答案]" in text:
        return True
    if re.search(r"(?m)^[-*]\s", text):
        return True
    return False


def _is_invalid_dialogue(dialogue: str, character_name: str, user_input: str) -> bool:
    if not dialogue:
        return True

    stripped = dialogue.strip()
    if len(stripped) < 4:
        return True

    if _looks_like_meta_text(stripped):
        return True

    normalized_dialogue = _normalize_text_for_compare(stripped)
    normalized_name = _normalize_text_for_compare(character_name)
    if normalized_name and normalized_dialogue == normalized_name:
        return True

    normalized_input = _normalize_text_for_compare(user_input)
    if normalized_input and normalized_dialogue == normalized_input:
        return True

    if not _contains_japanese(stripped):
        return True

    if _looks_like_choice_or_template(stripped):
        return True

    if stripped.startswith(("(", "（")) and re.search(r"[A-Za-z]{3,}", stripped):
        return True

    return False


def _sanitize_narration(narration: str) -> str:
    cleaned = narration.strip()
    cleaned = cleaned.replace("[dialogue]", "").replace("[narration]", "").strip()
    if not cleaned:
        return ""

    if _looks_like_meta_text(cleaned):
        return ""

    if len(cleaned) > 280 and ("以下" in cleaned or re.search(r"\b[1-3][\.)]", cleaned)):
        return ""

    if len(cleaned) > 420:
        return ""

    if _looks_like_choice_or_template(cleaned):
        return ""

    return cleaned


def _extract_first_spoken_line(text: str) -> str:
    quote_match = re.search(r"[「『](.+?)[」』]", text, flags=re.DOTALL)
    if quote_match:
        return quote_match.group(1).strip()

    for line in text.splitlines():
        candidate = line.strip().lstrip("-* ")
        if candidate in {"[dialogue]", "[narration]"}:
            continue
        if candidate:
            return candidate
    return ""


def _parse_dual_response(raw_text: str, character_name: str, user_input: str) -> tuple[str, str]:
    dialogue = ""
    narration = ""
    used_dual_sections = False

    if "[dialogue]" in raw_text and "[narration]" in raw_text:
        parts = raw_text.split("[dialogue]", 1)[1]
        if "[narration]" in parts:
            used_dual_sections = True
            dialogue_part, narration_part = parts.split("[narration]", 1)
            dialogue = dialogue_part.strip()
            narration = narration_part.strip()
        else:
            narration = raw_text.strip()
            dialogue = _extract_first_spoken_line(raw_text)
    else:
        narration = raw_text.strip()
        dialogue = _extract_first_spoken_line(raw_text)

    if len(dialogue) > 180:
        dialogue = ""

    used_fallback_dialogue = False
    if _is_invalid_dialogue(dialogue, character_name, user_input):
        dialogue = _fallback_dialogue(user_input)
        used_fallback_dialogue = True

    if used_fallback_dialogue and not used_dual_sections:
        narration = ""

    narration = _sanitize_narration(narration)
    if narration and dialogue:
        normalized_dialogue = _normalize_text_for_compare(dialogue)
        normalized_narration = _normalize_text_for_compare(narration)
        if normalized_dialogue and normalized_dialogue in normalized_narration:
            narration = ""

    return dialogue, narration


async def _post_ollama(path: str, payload: dict, timeout_seconds: float) -> httpx.Response:
    last_exc: httpx.HTTPError | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(f"{settings.ollama_base_url}{path}", json=payload)
                response.raise_for_status()
                return response
        except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(0.6)
                continue
            raise
        except httpx.HTTPError as exc:
            last_exc = exc
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Unexpected Ollama request failure")


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

    response = await _post_ollama(
        "/api/chat",
        payload,
        timeout_seconds=settings.ollama_chat_timeout_seconds,
    )
    data = response.json()

    raw_text = data.get("message", {}).get("content", "")
    return _parse_dual_response(raw_text, story_settings.character_name, user_input)


async def embed_text(text: str) -> list[float]:
    payload = {
        "model": settings.ollama_embedding_model,
        "prompt": text,
    }
    response = await _post_ollama(
        "/api/embeddings",
        payload,
        timeout_seconds=settings.ollama_embedding_timeout_seconds,
    )
    data = response.json()

    embedding = data.get("embedding")
    if embedding is None:
        raise ValueError("Embedding was not returned by Ollama")

    if isinstance(embedding, str):
        embedding = json.loads(embedding)

    return embedding
