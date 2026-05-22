import asyncio
import threading
from queue import Queue

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.illustration_job import IllustrationJob
from app.models.story import Story
from app.schemas.illustration import IllustrationCreateIn, IllustrationOut
from app.services.image_service import generate_image


router = APIRouter(prefix="/api/stories/{story_id}/illustrations", tags=["illustrations"])


_JOB_QUEUE: Queue[str] = Queue()
_WORKER_GUARD = threading.Lock()
_WORKER_STARTED = False


def _serialize_job(job: IllustrationJob, request: Request) -> IllustrationOut:
    result = IllustrationOut.model_validate(job)
    if job.image_url:
        public_url = str(
            request.url_for(
                "get_illustration_image",
                story_id=job.story_id,
                job_id=job.id,
            )
        )
        result = result.model_copy(update={"image_url": public_url})
    return result


def _run_generation(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(IllustrationJob, job_id)
        if job is None:
            return

        job.status = "running"
        db.commit()

        image_url = asyncio.run(generate_image(job.source_text))
        job.status = "done"
        job.image_url = image_url
        job.error_message = None
        db.commit()
    except Exception as exc:
        job = db.get(IllustrationJob, job_id)
        if job is not None:
            job.status = "error"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()


def _worker_loop() -> None:
    while True:
        next_job_id = _JOB_QUEUE.get()
        try:
            _run_generation(next_job_id)
        finally:
            _JOB_QUEUE.task_done()


def _ensure_worker_started() -> None:
    global _WORKER_STARTED
    with _WORKER_GUARD:
        if _WORKER_STARTED:
            return

        worker = threading.Thread(target=_worker_loop, name="comfyui-job-worker", daemon=True)
        worker.start()
        _WORKER_STARTED = True


@router.post("", response_model=IllustrationOut)
def create_illustration_job(
    story_id: str,
    payload: IllustrationCreateIn,
    request: Request,
    db: Session = Depends(get_db),
) -> IllustrationOut:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    job = IllustrationJob(
        story_id=story_id,
        message_id=payload.message_id,
        source_text=payload.source_text,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    _ensure_worker_started()
    _JOB_QUEUE.put(job.id)
    return _serialize_job(job, request)


@router.get("/{job_id}", response_model=IllustrationOut)
def get_illustration_job(
    story_id: str,
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> IllustrationOut:
    job = db.get(IllustrationJob, job_id)
    if job is None or job.story_id != story_id:
        raise HTTPException(status_code=404, detail="Illustration job not found")
    return _serialize_job(job, request)


@router.get("/{job_id}/image")
async def get_illustration_image(story_id: str, job_id: str, db: Session = Depends(get_db)) -> Response:
    job = db.get(IllustrationJob, job_id)
    if job is None or job.story_id != story_id:
        raise HTTPException(status_code=404, detail="Illustration job not found")
    if job.status != "done" or not job.image_url:
        raise HTTPException(status_code=404, detail="Illustration image not ready")

    source_url = job.image_url.strip()
    if not source_url:
        raise HTTPException(status_code=404, detail="Illustration image not ready")

    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False, follow_redirects=True) as client:
            upstream = await client.get(source_url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch illustration image: {exc}") from exc

    if upstream.status_code >= 400:
        raise HTTPException(status_code=502, detail="Illustration image upstream returned an error")

    media_type = upstream.headers.get("content-type", "image/png")
    return Response(content=upstream.content, media_type=media_type)
