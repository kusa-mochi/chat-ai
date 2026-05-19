from __future__ import annotations

import json
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Story Chat AI"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://chatai:chatai@postgres:5432/chatai"

    cors_origins: str = "http://localhost:3000"

    llm_provider: str = "ollama"
    ollama_base_url: str = "http://ollama:11434"
    ollama_chat_model: str = "qwen2.5:7b-instruct"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_timeout_seconds: float = 120.0

    embedding_dimension: int = 768
    semantic_search_limit: int = 5

    vector_url: str = "http://qdrant:6333"
    vector_collection: str = "story_context"

    generated_images_dir: str = "generated-images"

    @property
    def cors_origins_list(self) -> List[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return ["http://localhost:3000"]

        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass

        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
