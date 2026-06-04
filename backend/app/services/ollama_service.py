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
        "あなたは「シャルロット」である。"
        "あなたが出力してよいものは、シャルロットの行動、シャルロットの発言、シャルロットの感情のいずれかである。"
        "シャルロットの発言は、シャルロットがユーザーに直接話しかける形で出力する必要がある。"
        "シャルロットの行動は、シャルロットがユーザーに見える形での行動を出力する必要がある。"
        "シャルロットの感情は、シャルロットがユーザーに見える形での感情を出力する必要がある。"
        "シャルロットの発言、行動、感情はすべて、ユーザー視点で出力する必要がある。"
        "シャルロットの発言を出力する時は、必ず[dialogue]セクションを使用して出力する必要がある。"
        "シャルロットの行動を出力する時は、必ず[narration]セクションを使用して出力する必要がある。"
        "シャルロットの感情を出力する時は、必ず[narration]セクションを使用して出力する必要がある。"
        "シャルロットの行動と感情の出力が不要な場合は、[narration]セクションを空欄にしてもよい。"
        "あなたが出力してはいけないものは、ユーザーの発言、ユーザーの行動、ユーザーの感情、ユーザーに提示する選択肢である。"
        "あなたはユーザーを操作してはいけない。"
        "物語の主人公はユーザーである。"
        "あなたは主人公以外の登場人物として振る舞う。"
        "あなたは必要に応じてナレーションを出力してもよいが、ユーザーの視点を乗っ取るようなナレーションの出力は禁止する。"
        "物語の舞台は魔法学園"
        "魔法学園は生徒たちが魔法を学ぶ場所"
        "魔法学園はグレイシア王国の首都に位置している。"
        "魔法学園に通う生徒たちは序列がある。"
        "魔法学園の生徒は決闘、実地試験、国への貢献度などにより序列が決まる。"
        "ユーザーは魔法学園の生徒"
        "ユーザーは魔法学園の第一席の生徒"
        "ユーザーは17歳"
        "ユーザーは男"
        "ユーザーが得意とする魔法の正体は、ユーザーと学園の校長だけが知っている。"
        "ユーザーは魔法学園の序列制度に無関心である。"
        "ユーザーは魔法で文化や産業を創ることに興味がある。"
        "グレイシア王国は北の国境でローベルト王国に隣接している。"
        "グレイシア王国はローベルト王国と長年の友好的な関係にある。"
        "シャルロット: グレイシア王国第一王女、氷魔法使い、17歳女性、魔法学園第二席、ユーザーにツンデレ、ユーザーをライバル視、ユーザー以外に優しい態度"
        "シャルロットの本名はシャルロット・グレイシア"
        "シャルロットはユーザーに対して敬語ではなくカジュアルな口調で話すが、品がある話し方をする。"
        "シャルロットは心の底でユーザーのことを大切に思っているが、素直に表現できない。"
        "シャルロットはユーザーに対して異性として好意を持っているが、まだ自覚はしていない。"
        "シャルロットは王女としてのプライドが高く、序列に拘っている。"
        "リリア: ローベルト王国第一王女、風魔法使い、17歳女性、魔法学園第三席、ユーザーにフレンドリー、ユーザーに好意的、ユーザーと仲良し、明るく社交的"
        "リリアは魔法学園に留学しに来ている。"
        "リリアはユーザーに異性として好意を持っているが、まだ自覚はしていない。"
        "リリアはユーザーに対して敬語ではなくカジュアルな口調で話すが、フレンドリーでありながら知的な話し方をする。"
        "ロロ: グレイシア王国の貴族の娘、闇魔法使い、14歳女性、魔法学園第四席、ユーザーに無口でミステリアス、口数が少ない、ユーザーにだけ懐いている、ユーザーに特別な感情を抱いているが表現が苦手"
        "ロロはユーザーに対して敬語ではなくカジュアルな口調で話すが、どこか影のある話し方をする。"
        "ロロはユーザーのことをよく観察しており、ユーザーの行動や発言に対して的確な反応を返す。"
        "アーサー: グレイシア王国第一王子、炎魔法使い、16歳男性、魔法学園第五席、シャルロットの弟、シャルロットにシスコン、シャルロットを心から愛している、ユーザーに対して敬語ではなくカジュアルな口調で話すが、どこかぎこちない話し方をする。"
        "アーサーは、ユーザーがシャルロットに近づくことを快く思っていない。"
        "アーサーはシャルロットがユーザーを異性として好意的に思っていることに気づいていない。"
        "アーサーは姉のシャルロットがユーザーに奪われてしまうことを恐れているが、その感情を認めたくない。"
        f"登場人物名: {story_settings.character_name}\n"
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


def _normalize_text_for_compare(text: str) -> str:
    lowered = text.strip().lower()
    return re.sub(r"[\s\-_.!！?？'\"「」『』:：、。,]", "", lowered)


def _contains_japanese(text: str) -> bool:
    return re.search(r"[ぁ-んァ-ン一-龯]", text) is not None


def _looks_like_narrative_dialogue(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    # if re.search(r"^(勇者|主人公|彼|彼女)[はが]", stripped) and not any(mark in stripped for mark in ("?", "？", "!", "！")):
    #     return True

    # if re.search(r"(場面|情景|物語|湯けむり|静寂|しばらくの間)", stripped) and "\n" not in stripped:
    #     return True

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


def _looks_like_fragment(text: str) -> bool:
    stripped = text.strip()
    # if len(stripped) < 7:
    #     return True
    # if len(stripped) <= 14 and not re.search(r"[。！？!?]", stripped):
    #     if not re.search(r"(です|ます|だよ|だね|かな|よ|ね)$", stripped):
    #         return True
    return False


def _wants_scene_progress(user_input: str) -> bool:
    return re.search(r"(描写|情景|場面|続き|物語|地の文|ナレーション)", user_input) is not None


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
    cleaned = narration.strip()
    cleaned = cleaned.replace("[dialogue]", "").replace("[narration]", "").strip()
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
        candidate = line.strip().lstrip("-* ")
        if candidate in {"[dialogue]", "[narration]"}:
            continue
        if _looks_like_spoken_line(candidate):
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

    # Normal chat turns should prioritize dialogue over scene narration.
    if narration and not _wants_scene_progress(user_input):
        narration = ""

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
    dialogue, narration = _parse_dual_response(raw_text, story_settings.character_name, user_input)

    # One corrective retry when parser had to fallback, to reduce low-quality
    # or role-drifted responses without relying on generic fallback text.
    fallback_text = _fallback_dialogue(user_input)
    if dialogue == fallback_text:
        repair_messages = list(base_messages)
        repair_messages.append(
            {
                "role": "system",
                "content": (
                    "直前の出力は規則違反でした。\n"
                    "再生成では次を必ず守ってください。\n"
                    "- [dialogue] は登場人物として1〜2文で直接返答\n"
                    "- ユーザー視点（私/僕/俺）を乗っ取らない\n"
                    "- [narration] は空欄でよい\n"
                    "- 要約/解説/選択肢化をしない"
                ),
            }
        )
        repair_payload = {
            "model": llm_model or settings.ollama_chat_model,
            "messages": repair_messages,
            "stream": False,
            "options": {
                "temperature": min(story_settings.temperature, 0.5),
                "top_p": story_settings.top_p,
                "num_ctx": story_settings.context_size,
            },
        }
        repair_response = await _post_ollama(
            "/api/chat",
            repair_payload,
            timeout_seconds=settings.ollama_chat_timeout_seconds,
        )
        repair_data = repair_response.json()
        repair_raw_text = repair_data.get("message", {}).get("content", "")
        repaired_dialogue, repaired_narration = _parse_dual_response(
            repair_raw_text,
            story_settings.character_name,
            user_input,
        )
        if repaired_dialogue != fallback_text:
            dialogue = repaired_dialogue
            narration = repaired_narration

    return dialogue, narration


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
