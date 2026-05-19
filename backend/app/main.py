from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.ai import AIService
from app.config import get_settings
from app.database import init_db
from app.image_service import ImageService
from app.routes.api import router as api_router
from app.vector_store import VectorStore

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    app.state.ai_service = AIService(settings)
    app.state.vector_store = VectorStore(settings)
    app.state.vector_store.ensure_collection()
    app.state.image_service = ImageService(settings)


app.include_router(api_router)

images_dir = Path(settings.generated_images_dir)
images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/generated-images", StaticFiles(directory=str(images_dir)), name="generated-images")
