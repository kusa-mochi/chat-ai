import json
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Story Chat AI"
    database_url: str = "postgresql+psycopg://chat_ai:chat_ai@postgres:5432/chat_ai"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "story_context"

    ollama_base_url: str = "http://ollama:11434"
    ollama_chat_model: str = "gemma3:12b-it-qat"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_chat_timeout_seconds: float = 90.0
    ollama_chat_max_predict: int = 160
    ollama_embedding_timeout_seconds: float = 120.0
    ollama_embedding_num_ctx: int = 2048
    ollama_warmup_on_startup: bool = True

    comfyui_base_url: str = "http://comfyui:8188"
    comfyui_checkpoint: str = "v1-5-pruned-emaonly.safetensors"

    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def backend_cors_origins_list(self) -> List[str]:
        raw = self.backend_cors_origins.strip()
        if not raw:
            return []

        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]

        return [item.strip() for item in raw.split(",") if item.strip()]


settings = Settings()
