import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.message import Message
from app.models.story import Story
from app.schemas.message import BranchListOut, BranchSummaryOut, MessageOut, RewindIn, RewindOut


router = APIRouter(prefix="/api/stories/{story_id}", tags=["branching"])


@router.get("/branches", response_model=BranchListOut)
def list_branches(story_id: str, db: Session = Depends(get_db)) -> BranchListOut:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    rows = db.execute(
        select(
            Message.branch_id,
            func.count(Message.id),
            func.max(Message.created_at),
        )
        .where(Message.story_id == story_id)
        .group_by(Message.branch_id)
    ).all()

    summaries = [
        BranchSummaryOut(
            branch_id=branch_id,
            message_count=message_count,
            last_message_at=last_message_at,
            is_active=(branch_id == story.active_branch_id),
        )
        for branch_id, message_count, last_message_at in rows
    ]

    known_branch_ids = {item.branch_id for item in summaries}
    if story.active_branch_id not in known_branch_ids:
        summaries.append(
            BranchSummaryOut(
                branch_id=story.active_branch_id,
                message_count=0,
                last_message_at=None,
                is_active=True,
            )
        )

    min_time = datetime.min.replace(tzinfo=timezone.utc)
    summaries.sort(key=lambda item: item.last_message_at or min_time, reverse=True)
    summaries.sort(key=lambda item: item.branch_id != story.active_branch_id)
    return BranchListOut(items=summaries)


@router.post("/rewind", response_model=RewindOut)
def rewind_story(story_id: str, payload: RewindIn, db: Session = Depends(get_db)) -> RewindOut:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    pivot = db.get(Message, payload.message_id)
    if pivot is None or pivot.story_id != story_id:
        raise HTTPException(status_code=404, detail="Pivot message not found")

    new_branch_id = str(uuid.uuid4())
    story.active_branch_id = new_branch_id
    db.commit()

    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.story_id == story_id,
                Message.branch_id == pivot.branch_id,
                Message.created_at <= pivot.created_at,
            )
            .order_by(Message.created_at.asc())
        ).all()
    )

    return RewindOut(
        new_branch_id=new_branch_id,
        from_message_id=pivot.id,
        messages=[MessageOut.model_validate(item) for item in messages],
    )
