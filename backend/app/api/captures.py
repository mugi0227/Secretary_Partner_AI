"""
Captures API endpoints.

Endpoints for storing and retrieving user input captures.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, CaptureRepo
from app.core.exceptions import NotFoundError
from app.models.capture import Capture, CaptureCreate

router = APIRouter()


@router.post("", response_model=Capture, status_code=status.HTTP_201_CREATED)
async def create_capture(
    capture: CaptureCreate,
    user: CurrentUser,
    repo: CaptureRepo,
):
    """Create a new capture."""
    return await repo.create(user.id, capture)


@router.get("/{capture_id}", response_model=Capture)
async def get_capture(
    capture_id: UUID,
    user: CurrentUser,
    repo: CaptureRepo,
):
    """Get a capture by ID."""
    capture = await repo.get(user.id, capture_id)
    if not capture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capture {capture_id} not found",
        )
    return capture


@router.get("", response_model=list[Capture])
async def list_captures(
    user: CurrentUser,
    repo: CaptureRepo,
    processed: Optional[bool] = Query(None, description="Filter by processed status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List captures with optional filters."""
    return await repo.list(
        user.id,
        processed=processed,
        limit=limit,
        offset=offset,
    )


@router.post("/{capture_id}/process", response_model=Capture)
async def mark_capture_processed(
    capture_id: UUID,
    user: CurrentUser,
    repo: CaptureRepo,
):
    """Mark a capture as processed."""
    try:
        return await repo.mark_processed(user.id, capture_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/{capture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_capture(
    capture_id: UUID,
    user: CurrentUser,
    repo: CaptureRepo,
):
    """Delete a capture."""
    deleted = await repo.delete(user.id, capture_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capture {capture_id} not found",
        )

