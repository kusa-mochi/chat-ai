import asyncio
import threading
from queue import Queue

from fastapi import APIRouter, Depends, HTTPException
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
    db: Session = Depends(get_db),
) -> IllustrationJob:
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
    return job


@router.get("/{job_id}", response_model=IllustrationOut)
def get_illustration_job(story_id: str, job_id: str, db: Session = Depends(get_db)) -> IllustrationJob:
    job = db.get(IllustrationJob, job_id)
    if job is None or job.story_id != story_id:
        raise HTTPException(status_code=404, detail="Illustration job not found")
    return job
