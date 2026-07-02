import asyncio
import json
import logging
import re
from typing import Awaitable, Callable, Iterable

import httpx

from app.config import settings
from app.models.message import Message
from app.models.story_settings import DEFAULT_CHARACTERS_TEXT, StorySettings


logger = logging.getLogger(__name__)

TURN_MARKER_RE = re.compile(
    r"</?end_of_turn>|<start_of_turn>\s*(?:user|assistant|system|model)?",
    flags=re.IGNORECASE,
)
ROLE_LINE_RE = re.compile(r"(?mi)^\s*(?:user|assistant|system|model)\s*$")

MAX_SPEAKERS = 6
MAX_DIALOGUE_CHARS = 520
MAX_NARRATION_CHARS = 1400

SpeakerLine = tuple[str, str]


def _normalized_characters_text(story_settings: StorySettings) -> str:
    text = (story_settings.characters_text or "").strip()
    if text:
        return text
    return DEFAULT_CHARACTERS_TEXT


def _build_system_prompt(story_settings: StorySettings) -> str:
    characters_text = _normalized_characters_text(story_settings)

    return f"""あなたは物語チャットの進行AIです。文脈に応じて、キャラクター1人または複数人の発話を返してください。

出力は必ずJSONオブジェクト1つのみとし、余計な文字・解説・Markdown・コードフェンスを付けてはいけません。

JSONスキーマ:
{{
  "speakers": [
    {{"name": "発話者名", "line": "セリフ"}}
  ],
  "narration": "ナレーション(不要なら空文字)"
}}

必須ルール:
- speakers は配列。各要素は name と line を持つ。
- narration は文字列（不要なら ""）。
- ユーザーの発言・行動・感情・選択肢を勝手に決めない。
- ユーザー入力の特定フレーズを条件に分岐しない。文脈全体で応答を決める。
- キャラクターを固定しない。場面に合う人物を選ぶ。
- セリフは自然な会話体で、説明文だけの羅列にしない。

世界設定:
- 舞台: グレイシア王国首都の魔法学園（序列制: 決闘・実地試験・貢献度で決定）
- ユーザー: 17歳男性、第1席、序列無関心、魔法で文化産業創造に興味、得意魔法は校長のみ知る
- グレイシア-ローベルト両王国: 南北で隣接、グレイシア王国は南側、長年友好関係

キャラクター一覧:
{characters_text}
"""


def _history_to_messages(history: Iterable[Message]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for message in history:
        if message.role != "assistant":
            items.append({"role": "user", "content": message.content})
            continue

        if message.kind == "dialogue":
            payload = {
                "type": "dialogue",
                "speaker": message.speaker_name or "登場人物",
                "text": message.content,
            }
            items.append({"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)})
            continue

        if message.kind == "narration":
            payload = {
                "type": "narration",
                "text": message.content,
            }
            items.append({"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)})
            continue

        items.append({"role": "assistant", "content": message.content})
    return items


def _strip_turn_markers(text: str) -> str:
    without_turn_markers = TURN_MARKER_RE.sub("", text)
    without_role_lines = ROLE_LINE_RE.sub("", without_turn_markers)
    return re.sub(r"\n{3,}", "\n\n", without_role_lines)


def _extract_json_object(text: str) -> str | None:
    sanitized = _strip_turn_markers(text).strip()

    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", sanitized, flags=re.IGNORECASE)
    if fence_match:
        sanitized = fence_match.group(1).strip()

    start = sanitized.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(sanitized)):
        ch = sanitized[idx]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                return sanitized[start : idx + 1]

    return None


def _sanitize_text(text: str, max_chars: int) -> str:
    cleaned = _strip_turn_markers(text).strip()
    if not cleaned:
        return ""
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip()
    return cleaned


def _sanitize_speaker_name(text: str) -> str:
    cleaned = _strip_turn_markers(text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""
    return cleaned[:80]


def _parse_structured_response(raw_text: str) -> tuple[list[SpeakerLine], str, bool]:
    candidate = _extract_json_object(raw_text)
    if candidate is None:
        return [], "", False

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return [], "", False

    if not isinstance(data, dict):
        return [], "", False

    speakers: list[SpeakerLine] = []
    speakers_raw = data.get("speakers")
    if isinstance(speakers_raw, list):
        for item in speakers_raw[:MAX_SPEAKERS]:
            if not isinstance(item, dict):
                continue
            name = _sanitize_speaker_name(str(item.get("name") or ""))
            line = _sanitize_text(str(item.get("line") or ""), MAX_DIALOGUE_CHARS)
            if not name or not line:
                continue
            speakers.append((name, line))

    narration = _sanitize_text(str(data.get("narration") or ""), MAX_NARRATION_CHARS)

    if not speakers and not narration:
        return [], "", False

    return speakers, narration, True


def _fallback_structured_response(*, opening: bool) -> tuple[list[SpeakerLine], str]:
    if opening:
        return (
            [],
            "朝靄の中、魔法学園の鐘が静かに鳴る。廊下の先で気配が交差し、物語はまだ名もない会話の直前で息を潜めた。",
        )

    return (
        [],
        "言葉を整え直している。次の一言でもう一度場面を動かそう。",
    )


def _build_repair_instruction(*, opening: bool) -> str:
    if opening:
        return (
            "直前の出力はJSON形式違反でした。"
            "次は必ず指定スキーマに一致するJSONオブジェクト1つだけを返し、"
            "新しい物語の導入として、複数人のセリフまたはナレーションで開始してください。"
        )

    return (
        "直前の出力はJSON形式違反でした。"
        "次は必ず指定スキーマに一致するJSONオブジェクト1つだけを返し、"
        "文脈に応じて1人または複数人の自然な返答を生成してください。"
    )


def _build_user_prompt(*, user_input: str, opening: bool) -> str:
    if opening:
        return (
            "新規物語の冒頭シーンを生成してください。"
            "ユーザーの最初の入力を待たずに読み始められる導入にし、"
            "キャラクター複数名のセリフまたはナレーションで始めてください。"
        )

    return user_input


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


async def _post_ollama_chat_stream(payload: dict, timeout_seconds: float) -> str:
    return await _post_ollama_chat_stream_with_callback(payload, timeout_seconds, on_chunk=None)


async def _post_ollama_chat_stream_with_callback(
    payload: dict,
    timeout_seconds: float,
    on_chunk: Callable[[str], Awaitable[None]] | None,
) -> str:
    last_exc: httpx.HTTPError | None = None
    for attempt in range(2):
        try:
            timeout = httpx.Timeout(timeout_seconds, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    chunks: list[str] = []
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        message = item.get("message")
                        if isinstance(message, dict):
                            content_part = message.get("content", "")
                            if content_part:
                                chunks.append(content_part)
                                if on_chunk is not None:
                                    await on_chunk(content_part)

                        if item.get("done"):
                            break

                    return "".join(chunks)
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
    raise RuntimeError("Unexpected Ollama stream request failure")


async def _chat_story_impl(
    story_settings: StorySettings,
    llm_model: str,
    history: Iterable[Message],
    user_input: str,
    retrieved_context: list[str],
    *,
    on_chunk: Callable[[str], Awaitable[None]] | None,
    allow_repair: bool,
    opening: bool,
) -> tuple[list[SpeakerLine], str]:
    base_messages = [{"role": "system", "content": _build_system_prompt(story_settings)}]

    if retrieved_context:
        base_messages.append(
            {
                "role": "system",
                "content": "過去の関連文脈:\n" + "\n---\n".join(retrieved_context),
            }
        )

    base_messages.extend(_history_to_messages(history))
    base_messages.append({"role": "user", "content": _build_user_prompt(user_input=user_input, opening=opening)})

    payload = {
        "model": llm_model or settings.ollama_chat_model,
        "messages": base_messages,
        "stream": True,
        "options": {
            "temperature": story_settings.temperature,
            "top_p": story_settings.top_p,
            "num_ctx": story_settings.context_size,
            "num_predict": settings.ollama_chat_max_predict,
        },
    }

    raw_text = await _post_ollama_chat_stream_with_callback(
        payload,
        timeout_seconds=settings.ollama_chat_timeout_seconds,
        on_chunk=on_chunk,
    )
    speakers, narration, parsed_ok = _parse_structured_response(raw_text)

    if allow_repair and not parsed_ok:
        repair_messages = list(base_messages)
        repair_messages.append(
            {
                "role": "system",
                "content": _build_repair_instruction(opening=opening),
            }
        )
        repair_payload = {
            "model": llm_model or settings.ollama_chat_model,
            "messages": repair_messages,
            "stream": True,
            "options": {
                "temperature": min(story_settings.temperature, 0.5),
                "top_p": story_settings.top_p,
                "num_ctx": story_settings.context_size,
                "num_predict": settings.ollama_chat_max_predict,
            },
        }
        repair_raw_text = await _post_ollama_chat_stream(
            repair_payload,
            timeout_seconds=settings.ollama_chat_timeout_seconds,
        )
        repaired_speakers, repaired_narration, repaired_ok = _parse_structured_response(repair_raw_text)
        if repaired_ok:
            speakers = repaired_speakers
            narration = repaired_narration
            parsed_ok = True

    if not parsed_ok:
        speakers, narration = _fallback_structured_response(opening=opening)

    return speakers, narration


async def chat_story(
    story_settings: StorySettings,
    llm_model: str,
    history: Iterable[Message],
    user_input: str,
    retrieved_context: list[str],
) -> tuple[list[SpeakerLine], str]:
    return await _chat_story_impl(
        story_settings,
        llm_model,
        history,
        user_input,
        retrieved_context,
        on_chunk=None,
        allow_repair=True,
        opening=False,
    )


async def chat_story_stream(
    story_settings: StorySettings,
    llm_model: str,
    history: Iterable[Message],
    user_input: str,
    retrieved_context: list[str],
    on_chunk: Callable[[str], Awaitable[None]],
) -> tuple[list[SpeakerLine], str]:
    return await _chat_story_impl(
        story_settings,
        llm_model,
        history,
        user_input,
        retrieved_context,
        on_chunk=on_chunk,
        allow_repair=False,
        opening=False,
    )


async def generate_story_opening(story_settings: StorySettings, llm_model: str) -> tuple[list[SpeakerLine], str]:
    return await _chat_story_impl(
        story_settings,
        llm_model,
        history=[],
        user_input="",
        retrieved_context=[],
        on_chunk=None,
        allow_repair=True,
        opening=True,
    )


async def warmup_ollama() -> None:
    warmup_payload = {
        "model": settings.ollama_chat_model,
        "messages": [
            {
                "role": "user",
                "content": "準備完了なら「OK」だけ返してください。",
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 1024,
            "num_predict": 8,
        },
    }

    try:
        await _post_ollama(
            "/api/chat",
            warmup_payload,
            timeout_seconds=min(settings.ollama_chat_timeout_seconds, 45.0),
        )
    except Exception as exc:
        # Warmup is best-effort and should never block startup.
        logger.info("Ollama warmup skipped: %s", exc)


async def embed_text(text: str) -> list[float]:
    payload = {
        "model": settings.ollama_embedding_model,
        "prompt": text,
        "options": {
            "num_ctx": settings.ollama_embedding_num_ctx,
        },
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
