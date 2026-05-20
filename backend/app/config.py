from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Story Chat AI"
    database_url: str = "postgresql+psycopg://chat_ai:chat_ai@postgres:5432/chat_ai"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "story_context"

    ollama_base_url: str = "http://ollama:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embedding_model: str = "nomic-embed-text"

    comfyui_base_url: str = "http://comfyui:8188"
    comfyui_checkpoint: str = "v1-5-pruned-emaonly.safetensors"

    backend_cors_origins: List[str] = ["http://localhost:3000"]

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _split_csv_origins(cls, value: str | List[str]) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()
