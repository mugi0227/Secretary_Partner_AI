"""
Captures API endpoints.

Endpoints for storing and retrieving user input captures.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    CurrentUser,
    CaptureRepo,
    LLMProvider,
    TaskRepo,
    ProjectRepo,
    MemoryRepo,
    TaskRepo,
    MemoryRepo,
    AgentTaskRepo,
    StorageProvider,
    ChatRepo,
)
from app.core.exceptions import NotFoundError
from app.models.capture import Capture, CaptureCreate
from app.services.agent_service import AgentService

router = APIRouter()


@router.post("", response_model=Capture, status_code=status.HTTP_201_CREATED)
async def create_capture(
    capture: CaptureCreate,
    user: CurrentUser,
    repo: CaptureRepo,
    storage: StorageProvider,
):
    """Create a new capture."""
    import base64
    import json
    from uuid import uuid4
    from app.models.enums import ContentType

    # Process base64 image if provided
    if capture.base64_image:
        try:
            image_data_url = capture.base64_image
            if image_data_url and image_data_url.startswith("data:image"):
                # Decode base64 (remove prefix "data:image/jpeg;base64,")
                header, encoded = image_data_url.split(",", 1)
                image_bytes = base64.b64decode(encoded)
                
                # Generate filename
                ext = header.split(";")[0].split("/")[1]
                filename = f"captures/{uuid4()}.{ext}"
                
                # Save to storage
                file_path = await storage.upload(filename, image_bytes)
                
                # Update capture URL
                capture.content_url = storage.get_public_url(filename)
                
                # If content_type was TEXT but we have an image, should we update it?
                # The extension sends TEXT with metadata. Let's keep it as is, 
                # or maybe change to MIXED if we had such type. 
                # For now, having content_url implies it has an image.
                
                # Clear the base64 data so it's not stored or passed around in memory unnecessarily
                capture.base64_image = None
                
        except (ValueError, IndexError):
            # Invalid format, ignore image
            pass

    # Clean up raw_text if it was used for JSON metadata validation but effectively empty?
    # No, extension sends metadata in raw_text, so keep it.


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


@router.post("/{capture_id}/analyze")
async def analyze_capture(
    capture_id: UUID,
    user: CurrentUser,
    llm_provider: LLMProvider,
    task_repo: TaskRepo,
    project_repo: ProjectRepo,
    memory_repo: MemoryRepo,
    agent_task_repo: AgentTaskRepo,
    capture_repo: CaptureRepo,
    chat_repo: ChatRepo,
):
    """
    Analyze a capture using AI to suggest task details.
    
    Returns a TaskCreate-compatible JSON object.
    """
    agent_service = AgentService(
        llm_provider=llm_provider,
        task_repo=task_repo,
        project_repo=project_repo,
        memory_repo=memory_repo,
        agent_task_repo=agent_task_repo,
        capture_repo=capture_repo,
        chat_repo=chat_repo,
    )
    
    try:
        return await agent_service.analyze_capture(user.id, capture_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )
