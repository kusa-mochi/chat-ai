from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import httpx

from app.config import Settings


@dataclass
class StoryTurn:
    dialogue: str
    narration: str


class AIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed_text(self, text: str) -> list[float]:
        payload = {"model": self.settings.ollama_embedding_model, "prompt": text}
        try:
            with httpx.Client(timeout=self.settings.ollama_timeout_seconds) as client:
                response = client.post(f"{self.settings.ollama_base_url}/api/embeddings", json=payload)
                response.raise_for_status()
            embedding = response.json().get("embedding")
            if isinstance(embedding, list) and embedding:
                return [float(value) for value in embedding]
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        return self._hash_embedding(text)

    def generate_turn(
        self,
        story_title: str,
        story_settings: Any,
        recent_entries: list[Any],
        semantic_entries: list[dict[str, Any]],
        user_message: str,
    ) -> StoryTurn:
        prompt = self._build_system_prompt(story_title, story_settings)
        timeline = self._format_recent_entries(recent_entries)
        semantic = self._format_semantic_entries(semantic_entries)

        payload = {
            "model": self.settings.ollama_chat_model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "これまでの流れ:\n"
                        f"{timeline}\n\n"
                        "関連する過去文脈:\n"
                        f"{semantic}\n\n"
                        "最新のユーザー入力:\n"
                        f"{user_message}\n\n"
                        "JSON形式のみで返答してください。"
                    ),
                },
            ],
            "options": {"temperature": float(story_settings.temperature)},
        }

        try:
            with httpx.Client(timeout=self.settings.ollama_timeout_seconds) as client:
                response = client.post(f"{self.settings.ollama_base_url}/api/chat", json=payload)
                response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
        except (httpx.HTTPError, ValueError, TypeError):
            content = ""

        if not content.strip():
            return StoryTurn(
                dialogue=f"{story_settings.ai_character_name}はあなたの言葉を受け止め、静かに頷いた。『{user_message}、その気持ちを大切にしよう』",
                narration="部屋の空気がわずかに和らぎ、物語は次の場面へと進み始める。",
            )

        parsed = self._parse_json_response(content)
        dialogue = parsed.get("dialogue", "")
        narration = parsed.get("narration", "")
        if not dialogue.strip():
            dialogue = f"{story_settings.ai_character_name}は少し考え込み、次の言葉を探している。"
        if not narration.strip():
            narration = "静かな間が流れ、物語の景色がゆっくりと動く。"
        return StoryTurn(dialogue=dialogue.strip(), narration=narration.strip())

    def build_image_prompt(self, source_text: str, story_settings: Any) -> str:
        return (
            "以下の文章をもとに、物語の挿絵を生成するための描写を作成してください。"
            "日本のライトノベル挿絵に適した構図、感情、背景を含め、過度な暴力表現は避けます。\n\n"
            f"登場人物名: {story_settings.ai_character_name}\n"
            f"人格: {story_settings.ai_persona}\n"
            f"対象テキスト: {source_text}\n"
        )

    def _build_system_prompt(self, story_title: str, story_settings: Any) -> str:
        return (
            "あなたは対話型の物語生成AIです。"
            "必ず日本語で、ユーザー以外の登場人物のセリフとナレーションを生成します。"
            "ユーザーの言葉を否定せず、物語を前進させてください。\n"
            f"物語タイトル: {story_title}\n"
            f"事前プロンプト: {story_settings.pre_prompt}\n"
            f"AI登場人物名: {story_settings.ai_character_name}\n"
            f"人格設定: {story_settings.ai_persona}\n"
            "出力仕様: JSONオブジェクトで {\"dialogue\":\"...\", \"narration\":\"...\"} のみを返す。"
        )

    def _format_recent_entries(self, entries: list[Any]) -> str:
        if not entries:
            return "(履歴なし)"
        role_label = {
            "user": "ユーザー",
            "ai_character": "AI登場人物",
            "narration": "ナレーション",
        }
        return "\n".join(f"- {role_label.get(entry.role, entry.role)}: {entry.content}" for entry in entries)

    def _format_semantic_entries(self, semantic_entries: list[dict[str, Any]]) -> str:
        if not semantic_entries:
            return "(該当なし)"
        return "\n".join(f"- {item.get('role', 'unknown')}: {item.get('content', '')}" for item in semantic_entries)

    def _parse_json_response(self, content: str) -> dict[str, str]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {
                    "dialogue": str(parsed.get("dialogue", "")),
                    "narration": str(parsed.get("narration", "")),
                }
        except json.JSONDecodeError:
            pass
        return {"dialogue": text[:300], "narration": ""}

    def _hash_embedding(self, text: str) -> list[float]:
        dim = self.settings.embedding_dimension
        vector = [0.0] * dim
        normalized = text.strip() or "empty"
        for index, char in enumerate(normalized):
            digest = sha256(f"{index}:{char}".encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:2], "big") % dim
            value = (digest[2] / 255.0) * 2 - 1
            vector[bucket] += value
        norm = sum(v * v for v in vector) ** 0.5 or 1.0
        return [v / norm for v in vector]
