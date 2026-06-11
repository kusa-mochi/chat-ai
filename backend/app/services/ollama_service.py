import asyncio
import json
import logging
import re
from typing import Awaitable, Callable, Iterable

import httpx

from app.config import settings
from app.models.message import Message
from app.models.story_settings import StorySettings


logger = logging.getLogger(__name__)

SECTION_TAG_RE = re.compile(r"\[/?(?:dialogue|narration)\]", flags=re.IGNORECASE)


def _build_system_prompt(story_settings: StorySettings) -> str:
    name = story_settings.character_name
    return f"""あなたは{name}である。常に{name}として1人称で応答すること。

    役割:
    - ユーザーはあなた（{name}）に話しかけている
    - あなたは{name}として、ユーザーへ直接返答する
    - 自分自身の名前を呼びかける台詞（例:「おはよう、{name}」）は絶対に出力しない

    出力形式:
    [dialogue]
    {name}としてユーザーへの返答（1-2文、カジュアルな口調）
    [narration]
    {name}の行動・感情描写（省略可）

    禁止事項:
    - ユーザーの発言/行動/感情/選択肢の出力
    - ユーザー視点の乗っ取り
    - {name}の名前を呼びかける形の台詞（ユーザーが言うような台詞）
    - ユーザーが言いそうな挨拶・セリフの出力
    - [dialogue]に「{name}は〜」「{name}が〜」の形で自分自身を三人称主語にした文を書くこと
      （「{name}は〜」は自分の発言ではなく[narration]だ）

    出力例:
    （正しい例）
    [dialogue]
    魔法理論は面白いけど、あなたには負けたくないわ。
    [narration]
    {name}はそっぽを向きながらも、口元が微かに緩んだ。

    （誤った例・禁止）
    [dialogue]
    {name}は授業に導れると隣に座ることが多い。
    ↑ {name}を主語にした外部視点の文。{name}の発言ではなく[narration]に書くべき内容。

    世界設定:
    - 舞台: グレイシア王国首都の魔法学園（序列制: 決闘・実地試験・貢献度で決定）
    - ユーザー: 17歳男性、第1席、序列無関心、魔法で文化産業創造に興味、得意魔法は校長のみ知る
    - グレイシア-ローベルト両王国: 南北で隣接、グレイシア王国は南側、長年友好関係

    登場人物:
    - シャルロット: グレイシア第一王女、氷魔法、17歳女、第2席、ツンデレ、素直になれない好意、序列とプライドに執着、決闘口実でユーザー接触
    - リリア: ローベルト第一王女留学生、風魔法、17歳女、第3席、明るく社交的、フレンドリーな好意、知的な話し方
    - ロロ: グレイシア貴族令嬢、闇魔法、14歳女、第4席、無口ミステリアス、ユーザーにだけ懐く、観察力高い、影ある話し方
    - アーサー: グレイシア第一王子、炎魔法、16歳男、第5席、シャルロットの弟、シスコン、ユーザー警戒、姉を奪われる恐怖、ぎこちない話し方
    """
    # return (
    #     "あなたは「シャルロット」である。"
    #     "あなたが出力してよいものは、シャルロットの行動、シャルロットの発言、シャルロットの感情のいずれかである。"
    #     "シャルロットの発言は、シャルロットがユーザーに直接話しかける形で出力する必要がある。"
    #     "シャルロットの行動は、シャルロットがユーザーに見える形での行動を出力する必要がある。"
    #     "シャルロットの感情は、シャルロットがユーザーに見える形での感情を出力する必要がある。"
    #     "シャルロットの発言、行動、感情はすべて、ユーザー視点で出力する必要がある。"
    #     "シャルロットの発言を出力する時は、必ず[dialogue]セクションを使用して出力する必要がある。"
    #     "シャルロットの行動を出力する時は、必ず[narration]セクションを使用して出力する必要がある。"
    #     "シャルロットの感情を出力する時は、必ず[narration]セクションを使用して出力する必要がある。"
    #     "シャルロットの行動と感情の出力が不要な場合は、[narration]セクションを空欄にしてもよい。"
    #     "あなたが出力してはいけないものは、ユーザーの発言、ユーザーの行動、ユーザーの感情、ユーザーに提示する選択肢である。"
    #     "あなたはユーザーを操作してはいけない。"
    #     "物語の主人公はユーザーである。"
    #     "あなたは主人公以外の登場人物として振る舞う。"
    #     "あなたは必要に応じてナレーションを出力してもよいが、ユーザーの視点を乗っ取るようなナレーションの出力は禁止する。"
    #     "物語の舞台は魔法学園"
    #     "魔法学園は生徒たちが魔法を学ぶ場所"
    #     "魔法学園はグレイシア王国の首都に位置している。"
    #     "魔法学園に通う生徒たちは序列がある。"
    #     "魔法学園の生徒は決闘、実地試験、国への貢献度などにより序列が決まる。"
    #     "ユーザーは魔法学園の生徒"
    #     "ユーザーは魔法学園の第一席の生徒"
    #     "ユーザーは17歳"
    #     "ユーザーは男"
    #     "ユーザーが得意とする魔法の正体は、ユーザーと学園の校長だけが知っている。"
    #     "ユーザーは魔法学園の序列制度に無関心である。"
    #     "ユーザーは魔法で文化や産業を創ることに興味がある。"
    #     "グレイシア王国は北の国境でローベルト王国に隣接している。"
    #     "グレイシア王国はローベルト王国と長年の友好的な関係にある。"
    #     "シャルロット: グレイシア王国第一王女、氷魔法使い、17歳女性、魔法学園第二席、ユーザーにツンデレ、ユーザーをライバル視、ユーザー以外に優しい態度"
    #     "シャルロットの本名はシャルロット・グレイシア"
    #     "シャルロットはユーザーに対して敬語ではなくカジュアルな口調で話すが、品がある話し方をする。"
    #     "シャルロットは心の底でユーザーのことを大切に思っているが、素直に表現できない。"
    #     "シャルロットはユーザーに対して異性として好意を持っているが、まだ自覚していない。"
    #     "シャルロットは王女としてのプライドが高く、序列に拘っている。"
    #     "リリア: ローベルト王国第一王女、風魔法使い、17歳女性、魔法学園第三席、ユーザーにフレンドリー、ユーザーに好意的、ユーザーと仲良し、明るく社交的"
    #     "リリアは魔法学園に留学しに来ている。"
    #     "リリアはユーザーに異性として好意を持っているが、まだ自覚はしていない。"
    #     "リリアはユーザーに対して敬語ではなくカジュアルな口調で話すが、フレンドリーでありながら知的な話し方をする。"
    #     "ロロ: グレイシア王国の貴族の娘、闇魔法使い、14歳女性、魔法学園第四席、ユーザーに無口でミステリアス、口数が少ない、ユーザーにだけ懐いている、ユーザーに特別な感情を抱いているが表現が苦手"
    #     "ロロはユーザーに対して敬語ではなくカジュアルな口調で話すが、どこか影のある話し方をする。"
    #     "ロロはユーザーのことをよく観察しており、ユーザーの行動や発言に対して的確な反応を返す。"
    #     "アーサー: グレイシア王国第一王子、炎魔法使い、16歳男性、魔法学園第五席、シャルロットの弟、シャルロットにシスコン、シャルロットを心から愛している、ユーザーに対して敬語ではなくカジュアルな口調で話すが、どこかぎこちない話し方をする。"
    #     "アーサーは、ユーザーがシャルロットに近づくことを快く思っていない。"
    #     "アーサーはシャルロットがユーザーを異性として好意的に思っていることに気づいていない。"
    #     "アーサーは姉のシャルロットがユーザーに奪われてしまうことを恐れているが、その感情を認めたくない。"
    #     f"登場人物名: {story_settings.character_name}\n"
    # )


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


def _normalize_text_for_compare(text: str) -> str:
    lowered = text.strip().lower()
    return re.sub(r"[\s\-_.!！?？'\"「」『』:：、。,]", "", lowered)


def _contains_japanese(text: str) -> bool:
    return re.search(r"[ぁ-んァ-ン一-龯]", text) is not None


def _looks_like_narrative_dialogue(text: str) -> bool:
    """Return True when text is structurally narration rather than first-person dialogue.

    The only reliable structural rule—character's own name as grammatical subject—
    requires the character name and is therefore checked in _is_invalid_dialogue.
    This function is intentionally minimal to avoid false positives from
    keyword-based heuristics.
    """
    stripped = text.strip()
    if not stripped:
        return False

    return False

def _looks_like_spoken_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.count("\n") >= 1:
        return False
    if len(stripped) > 180:
        return False
    return True


def _strip_section_tags(text: str) -> str:
    return SECTION_TAG_RE.sub("", text)


def _looks_like_fragment(text: str) -> bool:
    stripped = text.strip()
    # if len(stripped) < 7:
    #     return True
    # if len(stripped) <= 14 and not re.search(r"[。！？!?]", stripped):
    #     if not re.search(r"(です|ます|だよ|だね|かな|よ|ね)$", stripped):
    #         return True
    return False


def _is_invalid_dialogue(dialogue: str, character_name: str, user_input: str) -> bool:
    if not dialogue:
        return True

    stripped = dialogue.strip()
    if len(stripped) < 4:
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

    if _looks_like_narrative_dialogue(stripped):
        return True

    if _looks_like_fragment(stripped):
        return True

    if stripped.startswith(("(", "（")) and re.search(r"[A-Za-z]{3,}", stripped):
        return True

    return False


def _sanitize_narration(narration: str) -> str:
    cleaned = _strip_section_tags(narration).strip()
    if not cleaned:
        return ""

    if len(cleaned) > 420:
        return ""

    return cleaned


def _extract_first_spoken_line(text: str) -> str:
    quote_match = re.search(r"[「『](.+?)[」』]", text, flags=re.DOTALL)
    if quote_match:
        return quote_match.group(1).strip()

    for line in text.splitlines():
        candidate = _strip_section_tags(line.strip().lstrip("-* ")).strip()
        if not candidate:
            continue
        if _looks_like_spoken_line(candidate):
            return candidate
    return ""


def _parse_dual_response(raw_text: str, character_name: str, user_input: str) -> tuple[str, str]:
    dialogue = ""
    narration = ""
    used_dual_sections = False

    dialogue_match = re.search(
        r"\[dialogue\](.*?)(?:\[/?dialogue\]|\[narration\]|$)",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    narration_match = re.search(
        r"\[narration\](.*?)(?:\[/?narration\]|$)",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if dialogue_match or narration_match:
        used_dual_sections = True
        dialogue = (dialogue_match.group(1) if dialogue_match else "").strip()
        narration = (narration_match.group(1) if narration_match else "").strip()
    else:
        narration = raw_text.strip()
        dialogue = _extract_first_spoken_line(raw_text)

    dialogue = _strip_section_tags(dialogue).strip()

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
    dialogue, narration = _parse_dual_response(raw_text, story_settings.character_name, user_input)

    # One corrective retry when parser had to fallback, to reduce low-quality
    # or role-drifted responses without relying on generic fallback text.
    fallback_text = _fallback_dialogue(user_input)
    if allow_repair and dialogue == fallback_text:
        repair_messages = list(base_messages)
        repair_messages.append(
            {
                "role": "system",
                "content": (
                    "直前の出力は規則違反でした。\n"
                    "再生成では次を必ず守ってください。\n"
                    "- [dialogue] は登場人物として1〜2文で直接返答\n"
                    "- ユーザー視点（私/僕/俺）を乗っ取らない\n"
                    "- [narration] は空欄でもよい\n"
                    "- 要約/解説/選択肢化をしない"
                ),
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
        repaired_dialogue, repaired_narration = _parse_dual_response(
            repair_raw_text,
            story_settings.character_name,
            user_input,
        )
        if repaired_dialogue != fallback_text:
            dialogue = repaired_dialogue
            narration = repaired_narration

    return dialogue, narration


async def chat_story(
    story_settings: StorySettings,
    llm_model: str,
    history: Iterable[Message],
    user_input: str,
    retrieved_context: list[str],
) -> tuple[str, str]:
    return await _chat_story_impl(
        story_settings,
        llm_model,
        history,
        user_input,
        retrieved_context,
        on_chunk=None,
        allow_repair=True,
    )


async def chat_story_stream(
    story_settings: StorySettings,
    llm_model: str,
    history: Iterable[Message],
    user_input: str,
    retrieved_context: list[str],
    on_chunk: Callable[[str], Awaitable[None]],
) -> tuple[str, str]:
    return await _chat_story_impl(
        story_settings,
        llm_model,
        history,
        user_input,
        retrieved_context,
        on_chunk=on_chunk,
        allow_repair=False,
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
