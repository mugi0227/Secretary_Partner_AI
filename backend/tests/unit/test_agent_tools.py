"""
Unit tests for agent tools.

Tests tool functions with mocked repositories.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from app.tools.task_tools import (
    create_task,
    update_task,
    delete_task,
    search_similar_tasks,
    CreateTaskInput,
    UpdateTaskInput,
    DeleteTaskInput,
    SearchSimilarTasksInput,
)
from app.models.task import Task, TaskCreate
from app.models.enums import Priority, EnergyLevel, CreatedBy, TaskStatus
from app.core.exceptions import NotFoundError


class MockTaskRepository:
    """Mock task repository for testing."""

    def __init__(self):
        self.tasks = {}

    async def create(self, user_id: str, task: TaskCreate) -> Task:
        """Create a task."""
        task_id = uuid4()
        now = datetime.utcnow()
        task_obj = Task(
            id=task_id,
            user_id=user_id,
            title=task.title,
            description=task.description,
            project_id=task.project_id,
            status=TaskStatus.TODO,
            importance=task.importance,
            urgency=task.urgency,
            energy_level=task.energy_level,
            estimated_minutes=task.estimated_minutes,
            due_date=task.due_date,
            parent_id=task.parent_id,
            source_capture_id=task.source_capture_id,
            created_by=task.created_by,
            created_at=now,
            updated_at=now,
        )
        self.tasks[task_id] = task_obj
        return task_obj

    async def get(self, user_id: str, task_id) -> Task | None:
        """Get a task."""
        task = self.tasks.get(task_id)
        if task and task.user_id == user_id:
            return task
        return None

    async def update(self, user_id: str, task_id, update) -> Task:
        """Update a task."""
        task = self.tasks.get(task_id)
        if not task or task.user_id != user_id:
            raise NotFoundError(f"Task {task_id} not found")

        update_data = update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                if hasattr(value, "value"):  # Enum
                    value = value.value
                setattr(task, field, value)

        task.updated_at = datetime.utcnow()
        return task

    async def delete(self, user_id: str, task_id) -> bool:
        """Delete a task."""
        task = self.tasks.get(task_id)
        if not task or task.user_id != user_id:
            return False
        del self.tasks[task_id]
        return True

    async def find_similar(self, user_id: str, title: str, project_id=None, threshold: float = 0.8, limit: int = 5):
        """Find similar tasks within the same project."""
        from app.models.task import SimilarTask
        from difflib import SequenceMatcher

        similar = []
        for task in self.tasks.values():
            if task.user_id != user_id:
                continue
            # Filter by project_id (None = Inbox)
            if task.project_id != project_id:
                continue
            score = SequenceMatcher(None, title.lower(), task.title.lower()).ratio()
            if score >= threshold:
                similar.append(SimilarTask(task=task, similarity_score=score))

        similar.sort(key=lambda x: x.similarity_score, reverse=True)
        return similar[:limit]


@pytest.mark.asyncio
async def test_create_task_tool():
    """Test create_task tool function."""
    repo = MockTaskRepository()
    user_id = "test_user"

    input_data = CreateTaskInput(
        title="テストタスク",
        description="テスト説明",
        importance=Priority.HIGH,
        urgency=Priority.MEDIUM,
        energy_level=EnergyLevel.LOW,
    )

    result = await create_task(user_id, repo, input_data)

    assert result["title"] == "テストタスク"
    assert result["description"] == "テスト説明"
    assert result["importance"] == Priority.HIGH
    assert len(repo.tasks) == 1


@pytest.mark.asyncio
async def test_update_task_tool():
    """Test update_task tool function."""
    repo = MockTaskRepository()
    user_id = "test_user"

    # Create a task first
    create_input = CreateTaskInput(title="元のタイトル")
    created = await create_task(user_id, repo, create_input)
    task_id = created["id"]

    # Update it
    update_input = UpdateTaskInput(
        task_id=str(task_id),
        title="更新されたタイトル",
        status="IN_PROGRESS",
    )

    result = await update_task(user_id, repo, update_input)

    assert result["title"] == "更新されたタイトル"
    assert result["status"] == TaskStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_delete_task_tool():
    """Test delete_task tool function."""
    repo = MockTaskRepository()
    user_id = "test_user"

    # Create a task first
    create_input = CreateTaskInput(title="削除するタスク")
    created = await create_task(user_id, repo, create_input)
    task_id = created["id"]

    # Delete it
    delete_input = DeleteTaskInput(task_id=str(task_id))
    result = await delete_task(user_id, repo, delete_input)

    assert result["success"] is True
    assert len(repo.tasks) == 0


@pytest.mark.asyncio
async def test_search_similar_tasks_tool():
    """Test search_similar_tasks tool function."""
    repo = MockTaskRepository()
    user_id = "test_user"

    # Create a task
    create_input = CreateTaskInput(title="買い物リストを作る")
    await create_task(user_id, repo, create_input)

    # Search for similar (in Inbox)
    search_input = SearchSimilarTasksInput(
        task_title="買い物リストを作成する",
        project_id=None,  # Search in Inbox
    )

    result = await search_similar_tasks(user_id, repo, search_input)

    assert result["count"] >= 1
    assert len(result["similar_tasks"]) >= 1
    assert result["similar_tasks"][0]["similarity_score"] > 0.8

