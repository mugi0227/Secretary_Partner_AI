"""
Memories API endpoints.

Endpoints for managing AI memories (user facts, project context, work rules).
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, MemoryRepo
from app.core.exceptions import NotFoundError
from app.models.memory import Memory, MemoryCreate, MemorySearchResult
from app.models.enums import MemoryScope, MemoryType

router = APIRouter()


@router.post("", response_model=Memory, status_code=status.HTTP_201_CREATED)
async def create_memory(
    memory: MemoryCreate,
    user: CurrentUser,
    repo: MemoryRepo,
):
    """Create a new memory."""
    return await repo.create(user.id, memory)


@router.get("/{memory_id}", response_model=Memory)
async def get_memory(
    memory_id: UUID,
    user: CurrentUser,
    repo: MemoryRepo,
):
    """Get a memory by ID."""
    memory = await repo.get(user.id, memory_id)
    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory {memory_id} not found",
        )
    return memory


@router.get("", response_model=list[Memory])
async def list_memories(
    user: CurrentUser,
    repo: MemoryRepo,
    scope: Optional[MemoryScope] = Query(None, description="Filter by scope"),
    memory_type: Optional[MemoryType] = Query(None, description="Filter by type"),
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List memories with optional filters."""
    return await repo.list(
        user.id,
        scope=scope,
        memory_type=memory_type,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=list[MemorySearchResult])
async def search_memories(
    user: CurrentUser,
    repo: MemoryRepo,
    query: str = Query(..., description="Search query"),
    scope: Optional[MemoryScope] = Query(None, description="Filter by scope"),
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    limit: int = Query(5, ge=1, le=20),
):
    """Search memories by content."""
    return await repo.search(
        user.id,
        query=query,
        scope=scope,
        project_id=project_id,
        limit=limit,
    )


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    user: CurrentUser,
    repo: MemoryRepo,
):
    """Delete a memory."""
    deleted = await repo.delete(user.id, memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory {memory_id} not found",
        )

