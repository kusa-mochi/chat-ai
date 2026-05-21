import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db.session import engine
from app.models import Base
from app.routes.branching import router as branching_router
from app.routes.chat import router as chat_router
from app.routes.illustrations import router as illustrations_router
from app.routes.settings import router as settings_router
from app.routes.stories import router as stories_router
from app.services.vector_service import ensure_collection


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stories_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(branching_router)
app.include_router(illustrations_router)


def _apply_legacy_schema_patches() -> None:
    if engine.dialect.name != "postgresql":
        return

    statements = [
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS active_branch_id VARCHAR(36) NOT NULL DEFAULT 'main'",
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS llm_model VARCHAR(120) NOT NULL DEFAULT 'qwen2.5-7b-instruct-uncensored-q4km:latest'",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS branch_id VARCHAR(36) NOT NULL DEFAULT 'main'",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS parent_message_id VARCHAR(36)",
        "ALTER TABLE story_settings ADD COLUMN IF NOT EXISTS id VARCHAR(36)",
        "ALTER TABLE story_settings ADD COLUMN IF NOT EXISTS preprompt TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE story_settings ADD COLUMN IF NOT EXISTS character_name VARCHAR(80) NOT NULL DEFAULT '語り部の相棒'",
        "ALTER TABLE story_settings ADD COLUMN IF NOT EXISTS character_persona TEXT NOT NULL DEFAULT '親密で文学的、比喩を交えつつ物語を前へ進める。'",
        "ALTER TABLE story_settings ADD COLUMN IF NOT EXISTS temperature DOUBLE PRECISION NOT NULL DEFAULT 0.9",
        "ALTER TABLE story_settings ADD COLUMN IF NOT EXISTS top_p DOUBLE PRECISION NOT NULL DEFAULT 0.9",
        "UPDATE story_settings SET id = story_id WHERE id IS NULL OR id = ''",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_story_settings_id ON story_settings (id)",
        "ALTER TABLE illustration_jobs ADD COLUMN IF NOT EXISTS error_message TEXT",
        "CREATE INDEX IF NOT EXISTS ix_messages_branch_id ON messages (branch_id)",
    ]

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

        story_settings_columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'story_settings'"
                )
            )
        }

        legacy_defaults: list[tuple[str, str]] = [
            ("context_size", "4096"),
            ("temperature", "0.9"),
            ("pre_prompt", "''"),
            ("ai_character_name", "''"),
            ("ai_persona", "''"),
        ]
        for column_name, default_sql in legacy_defaults:
            if column_name in story_settings_columns:
                conn.execute(text(f"ALTER TABLE story_settings ALTER COLUMN {column_name} SET DEFAULT {default_sql}"))
                conn.execute(text(f"UPDATE story_settings SET {column_name} = {default_sql} WHERE {column_name} IS NULL"))


@app.on_event("startup")
async def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    _apply_legacy_schema_patches()

    # Initialize the vector collection with a typical 768-dim embedding size.
    try:
        await ensure_collection(vector_size=768)
    except Exception:
        pass


@app.get("/api/health")
async def health() -> dict:
    checks = {
        "api": "ok",
        "ollama": "down",
        "qdrant": "down",
        "comfyui": "down",
    }

    async with httpx.AsyncClient(timeout=5.0, trust_env=False, follow_redirects=False) as client:
        try:
            ollama = await client.get(f"{settings.ollama_base_url}/api/tags")
            if ollama.status_code < 400:
                checks["ollama"] = "ok"
        except Exception:
            pass

        try:
            qdrant = await client.get(f"{settings.qdrant_url}/collections")
            if qdrant.status_code < 400:
                checks["qdrant"] = "ok"
        except Exception:
            pass

        try:
            comfyui = await client.get(f"{settings.comfyui_base_url}/system_stats")
            if comfyui.status_code < 400:
                checks["comfyui"] = "ok"
        except Exception:
            pass

    status = "ok" if all(v == "ok" or k == "api" for k, v in checks.items()) else "degraded"
    return {
        "status": status,
        "checks": checks,
    }
