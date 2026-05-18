from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api.tasks import create_task, get_subtasks, list_tasks, update_task
from app.models.enums import CreatedBy, ProjectVisibility, TaskStatus
from app.models.task import Task, TaskCreate, TaskUpdate
from app.services import task_application_service as task_app_service


def _make_task(
    index: int,
    *,
    is_fixed_time: bool,
    user_id: str = "owner-user",
    project_id: UUID | None = None,
    parent_id: UUID | None = None,
    task_id: UUID | None = None,
) -> Task:
    timestamp = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc) - timedelta(minutes=index)
    start_time = timestamp if is_fixed_time else None
    end_time = (timestamp + timedelta(minutes=30)) if is_fixed_time else None
    return Task(
        id=task_id or uuid4(),
        user_id=user_id,
        project_id=project_id,
        parent_id=parent_id,
        title=f"Task {index}",
        status=TaskStatus.TODO,
        created_by=CreatedBy.USER,
        created_at=timestamp,
        updated_at=timestamp,
        is_fixed_time=is_fixed_time,
        start_time=start_time,
        end_time=end_time,
    )


@pytest.mark.asyncio
async def test_list_tasks_exclude_meetings_filters_before_pagination() -> None:
    user = SimpleNamespace(id="owner-user")
    repo = AsyncMock()
    project_repo = AsyncMock()
    assignment_repo = AsyncMock()

    # Meetings dominate the newest items. Pagination should still return a full page
    # of non-meeting tasks when enough exist.
    repo.list.return_value = [_make_task(i, is_fixed_time=i < 50) for i in range(180)]
    repo.get_many.return_value = []
    project_repo.list.return_value = []
    assignment_repo.list_for_assignee.return_value = []

    result = await list_tasks(
        user=user,
        repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
        project_id=None,
        status=None,
        include_done=True,
        only_meetings=False,
        exclude_meetings=True,
        limit=100,
        offset=0,
    )

    assert len(result) == 100
    assert all(not task.is_fixed_time for task in result)


@pytest.mark.asyncio
async def test_get_subtasks_uses_owner_scope_for_project_task() -> None:
    owner_id = "owner-user"
    member_id = "member-user"
    project_id = uuid4()
    parent_id = uuid4()
    parent_task = _make_task(
        0,
        is_fixed_time=False,
        user_id=owner_id,
        project_id=project_id,
        task_id=parent_id,
    )

    user = SimpleNamespace(id=member_id)
    repo = AsyncMock()
    project_repo = AsyncMock()
    repo.get.return_value = None
    repo.get_by_id.return_value = parent_task
    repo.get_subtasks.return_value = []
    project_repo.get.return_value = SimpleNamespace(id=project_id, user_id=owner_id)

    result = await get_subtasks(
        task_id=parent_id,
        user=user,
        repo=repo,
        project_repo=project_repo,
    )

    assert result == []
    repo.get_subtasks.assert_awaited_once_with(owner_id, parent_id, project_id=project_id)


@pytest.mark.asyncio
async def test_create_task_in_project_uses_owner_scope() -> None:
    owner_id = "owner-user"
    member_id = "member-user"
    project_id = uuid4()

    user = SimpleNamespace(id=member_id)
    repo = AsyncMock()
    project_repo = AsyncMock()
    assignment_repo = AsyncMock()
    task = TaskCreate(title="New Task", project_id=project_id, created_by=CreatedBy.USER)
    created = _make_task(
        0,
        is_fixed_time=False,
        user_id=owner_id,
        project_id=project_id,
    )

    repo.create.return_value = created
    project_repo.get.return_value = SimpleNamespace(
        id=project_id,
        user_id=owner_id,
        visibility=ProjectVisibility.TEAM,
    )

    result = await create_task(
        task=task,
        user=user,
        repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
    )

    assert result == created
    repo.create.assert_awaited_once_with(owner_id, task)
    assignment_repo.assign_multiple.assert_not_called()


@pytest.mark.asyncio
async def test_create_task_private_project_auto_assigns_owner_scope() -> None:
    owner_id = "owner-user"
    project_id = uuid4()
    user = SimpleNamespace(id=owner_id)
    repo = AsyncMock()
    project_repo = AsyncMock()
    assignment_repo = AsyncMock()
    task = TaskCreate(title="Private Task", project_id=project_id, created_by=CreatedBy.USER)
    created = _make_task(
        0,
        is_fixed_time=False,
        user_id=owner_id,
        project_id=project_id,
    )
    repo.create.return_value = created
    project_repo.get.return_value = SimpleNamespace(
        id=project_id,
        user_id=owner_id,
        visibility=ProjectVisibility.PRIVATE,
    )

    await create_task(
        task=task,
        user=user,
        repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
    )

    call = assignment_repo.assign_multiple.await_args
    assert call.args[0] == owner_id
    assert call.args[1] == created.id
    assert call.args[2].assignee_ids == [owner_id]


@pytest.mark.asyncio
async def test_create_task_rejects_inaccessible_project() -> None:
    user = SimpleNamespace(id="member-user")
    repo = AsyncMock()
    project_repo = AsyncMock()
    assignment_repo = AsyncMock()
    project_repo.get.return_value = None

    with pytest.raises(HTTPException) as error:
        await create_task(
            task=TaskCreate(
                title="Should Fail",
                project_id=uuid4(),
                created_by=CreatedBy.USER,
            ),
            user=user,
            repo=repo,
            project_repo=project_repo,
            assignment_repo=assignment_repo,
        )

    assert error.value.status_code == 404
    repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_update_task_parent_validation_uses_owner_scope(monkeypatch: Any) -> None:
    owner_id = "owner-user"
    member_id = "member-user"
    project_id = uuid4()
    task_id = uuid4()
    new_parent_id = uuid4()
    user = SimpleNamespace(id=member_id)

    current_task = _make_task(
        0,
        is_fixed_time=False,
        user_id=owner_id,
        project_id=project_id,
        task_id=task_id,
    )
    repo = AsyncMock()
    project_repo = AsyncMock()
    assignment_repo = AsyncMock()

    repo.get.return_value = None
    repo.get_by_id.return_value = current_task
    repo.update.return_value = current_task
    project_repo.get.return_value = SimpleNamespace(id=project_id, user_id=owner_id)

    calls: dict[str, tuple[Any, ...]] = {}

    class StubDependencyValidator:
        def __init__(self, _repo: Any):
            pass

        async def validate_dependencies(self, *args: Any, **kwargs: Any) -> None:
            calls["dependencies"] = (*args, kwargs)

        async def validate_parent_child_consistency(self, *args: Any, **kwargs: Any) -> None:
            calls["parent"] = args

    monkeypatch.setattr(task_app_service, "DependencyValidator", StubDependencyValidator)

    await update_task(
        task_id=task_id,
        update=TaskUpdate(parent_id=new_parent_id),
        user=user,
        repo=repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
    )

    assert "parent" in calls
    assert calls["parent"][2] == owner_id
