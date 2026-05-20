import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stories_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(branching_router)
app.include_router(illustrations_router)


@app.on_event("startup")
async def on_startup() -> None:
    Base.metadata.create_all(bind=engine)

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

    async with httpx.AsyncClient(timeout=5.0) as client:
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
