"""Tests for member-child-task endpoints.

Verifies that:
1. Completed (DONE) tasks from child projects are included in the response.
2. The completed_at field is correctly passed through to MemberProjectTask.
3. Tasks without assignees are excluded.
4. Parent tasks (parent_id) are preserved in the response.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.projects import list_member_tasks_across_children, update_member_child_task
from app.models.enums import (
    CreatedBy,
    TaskStatus,
)
from app.models.task import Task, TaskUpdate


def _make_task(
    *,
    status: TaskStatus = TaskStatus.TODO,
    user_id: str = "owner",
    project_id=None,
    parent_id=None,
    completed_at=None,
) -> Task:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    return Task(
        id=uuid4(),
        user_id=user_id,
        project_id=project_id or uuid4(),
        parent_id=parent_id,
        title=f"Task {status.value}",
        status=status,
        completed_at=completed_at,
        created_by=CreatedBy.USER,
        created_at=now,
        updated_at=now,
        is_fixed_time=False,
    )


def _make_child_project(user_id: str = "owner"):
    """Create a minimal child project stub with required fields."""
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        name="Child Project",
    )


MEMBER_1_ID = "00000000-0000-0000-0000-000000000001"
MEMBER_2_ID = "00000000-0000-0000-0000-000000000002"


def _make_assignment(task_id, assignee_id: str = MEMBER_1_ID):
    return SimpleNamespace(
        task_id=str(task_id),
        assignee_id=assignee_id,
    )


async def _call_endpoint(
    children,
    tasks_by_child,
    assignments_by_child,
    user_names=None,
):
    """Helper to call the endpoint with mocked dependencies."""
    parent_project_id = uuid4()
    user = SimpleNamespace(id="caller-user")

    repo = AsyncMock()
    member_repo = AsyncMock()
    task_repo = AsyncMock()
    assignment_repo = AsyncMock()
    user_repo = AsyncMock()

    # require_project_member just needs to not raise
    repo.list_children_with_task_count.return_value = children

    # Map tasks and assignments per child
    task_repo.list.side_effect = [
        tasks_by_child.get(child.id, []) for child in children
    ]
    assignment_repo.list_by_project.side_effect = [
        assignments_by_child.get(child.id, []) for child in children
    ]

    # User name lookups
    if user_names:
        user_repo.get.side_effect = lambda uid: SimpleNamespace(
            display_name=user_names.get(str(uid), str(uid)),
            username=str(uid),
        )
    else:
        user_repo.get.return_value = SimpleNamespace(
            display_name="Test Member",
            username="test-member",
        )

    result = await list_member_tasks_across_children(
        project_id=parent_project_id,
        user=user,
        repo=repo,
        member_repo=member_repo,
        task_repo=task_repo,
        assignment_repo=assignment_repo,
        user_repo=user_repo,
    )

    return result, task_repo


@pytest.mark.asyncio
async def test_done_tasks_are_included():
    """Completed tasks from child projects should be returned."""
    child = _make_child_project()
    done_task = _make_task(
        status=TaskStatus.DONE,
        project_id=child.id,
        completed_at=datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc),
    )
    todo_task = _make_task(
        status=TaskStatus.TODO,
        project_id=child.id,
    )
    assignment_done = _make_assignment(done_task.id)
    assignment_todo = _make_assignment(todo_task.id)

    result, task_repo = await _call_endpoint(
        children=[child],
        tasks_by_child={child.id: [done_task, todo_task]},
        assignments_by_child={child.id: [assignment_done, assignment_todo]},
    )

    # Should have 1 member with 2 tasks (both TODO and DONE)
    assert len(result) == 1
    member = result[0]
    task_statuses = {t.task_status for t in member.tasks_by_project}
    assert TaskStatus.DONE in task_statuses
    assert TaskStatus.TODO in task_statuses
    assert len(member.tasks_by_project) == 2


@pytest.mark.asyncio
async def test_include_done_true_passed_to_repo():
    """The task_repo.list call should use include_done=True."""
    child = _make_child_project()

    result, task_repo = await _call_endpoint(
        children=[child],
        tasks_by_child={child.id: []},
        assignments_by_child={child.id: []},
    )

    task_repo.list.assert_awaited_once_with(
        child.user_id,
        project_id=child.id,
        include_done=True,
    )


@pytest.mark.asyncio
async def test_completed_at_is_passed_through():
    """The completed_at field should be present in MemberProjectTask."""
    child = _make_child_project()
    completed_time = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
    done_task = _make_task(
        status=TaskStatus.DONE,
        project_id=child.id,
        completed_at=completed_time,
    )
    assignment = _make_assignment(done_task.id)

    result, _ = await _call_endpoint(
        children=[child],
        tasks_by_child={child.id: [done_task]},
        assignments_by_child={child.id: [assignment]},
    )

    assert len(result) == 1
    task_entry = result[0].tasks_by_project[0]
    assert task_entry.completed_at == completed_time


@pytest.mark.asyncio
async def test_completed_at_none_for_open_task():
    """Open tasks should have completed_at=None."""
    child = _make_child_project()
    todo_task = _make_task(
        status=TaskStatus.TODO,
        project_id=child.id,
    )
    assignment = _make_assignment(todo_task.id)

    result, _ = await _call_endpoint(
        children=[child],
        tasks_by_child={child.id: [todo_task]},
        assignments_by_child={child.id: [assignment]},
    )

    assert len(result) == 1
    task_entry = result[0].tasks_by_project[0]
    assert task_entry.completed_at is None


@pytest.mark.asyncio
async def test_tasks_without_assignees_are_excluded():
    """Tasks that have no assignees should not appear in the response."""
    child = _make_child_project()
    unassigned_task = _make_task(project_id=child.id)

    result, _ = await _call_endpoint(
        children=[child],
        tasks_by_child={child.id: [unassigned_task]},
        assignments_by_child={child.id: []},  # no assignments
    )

    assert len(result) == 0


@pytest.mark.asyncio
async def test_parent_id_is_preserved():
    """Parent task relationships should be preserved in MemberProjectTask."""
    child = _make_child_project()
    parent_task_id = uuid4()
    parent_task = _make_task(
        status=TaskStatus.TODO,
        project_id=child.id,
    )
    # Override the ID
    parent_task.id = parent_task_id

    child_task = _make_task(
        status=TaskStatus.TODO,
        project_id=child.id,
        parent_id=parent_task_id,
    )

    result, _ = await _call_endpoint(
        children=[child],
        tasks_by_child={child.id: [parent_task, child_task]},
        assignments_by_child={
            child.id: [
                _make_assignment(parent_task.id),
                _make_assignment(child_task.id),
            ]
        },
    )

    assert len(result) == 1
    tasks = result[0].tasks_by_project
    child_entry = next(t for t in tasks if t.parent_id is not None)
    assert child_entry.parent_id == parent_task_id


@pytest.mark.asyncio
async def test_multiple_children_and_members():
    """Tasks across multiple child projects and members are grouped correctly."""
    child_a = _make_child_project()
    child_a.name = "Project A"
    child_b = _make_child_project()
    child_b.name = "Project B"

    task_a = _make_task(status=TaskStatus.IN_PROGRESS, project_id=child_a.id)
    task_b_done = _make_task(
        status=TaskStatus.DONE,
        project_id=child_b.id,
        completed_at=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
    )

    result, _ = await _call_endpoint(
        children=[child_a, child_b],
        tasks_by_child={
            child_a.id: [task_a],
            child_b.id: [task_b_done],
        },
        assignments_by_child={
            child_a.id: [_make_assignment(task_a.id, MEMBER_1_ID)],
            child_b.id: [_make_assignment(task_b_done.id, MEMBER_2_ID)],
        },
        user_names={},
    )

    member_ids = {m.member_user_id for m in result}
    assert MEMBER_1_ID in member_ids
    assert MEMBER_2_ID in member_ids

    member_1 = next(m for m in result if m.member_user_id == MEMBER_1_ID)
    assert len(member_1.tasks_by_project) == 1
    assert member_1.tasks_by_project[0].child_project_name == "Project A"

    member_2 = next(m for m in result if m.member_user_id == MEMBER_2_ID)
    assert len(member_2.tasks_by_project) == 1
    assert member_2.tasks_by_project[0].task_status == TaskStatus.DONE
    assert member_2.tasks_by_project[0].completed_at is not None


@pytest.mark.asyncio
async def test_no_children_returns_empty():
    """If the parent project has no children, the result should be empty."""
    result, _ = await _call_endpoint(
        children=[],
        tasks_by_child={},
        assignments_by_child={},
    )
    assert result == []


@pytest.mark.asyncio
async def test_update_member_child_task_updates_matching_child() -> None:
    parent_project_id = uuid4()
    child_project_id = uuid4()
    task_id = uuid4()
    task = _make_task(project_id=child_project_id)
    task.id = task_id
    task.status = TaskStatus.TODO
    user = SimpleNamespace(id="caller-user")

    repo = AsyncMock()
    member_repo = AsyncMock()
    task_repo = AsyncMock()

    child = SimpleNamespace(id=child_project_id, user_id="owner-user", name="Child")
    repo.list_children_with_task_count.return_value = [child]
    task_repo.get.return_value = task

    updated_task = _make_task(status=TaskStatus.DONE, project_id=child_project_id)
    updated_task.id = task_id
    task_repo.update.return_value = updated_task

    result = await update_member_child_task(
        project_id=parent_project_id,
        task_id=task_id,
        update=TaskUpdate(status=TaskStatus.DONE),
        user=user,
        repo=repo,
        member_repo=member_repo,
        task_repo=task_repo,
    )

    assert result.status == TaskStatus.DONE
    task_repo.get.assert_awaited_once_with("owner-user", task_id, project_id=child_project_id)
    task_repo.update.assert_awaited_once_with(
        "owner-user",
        task_id,
        TaskUpdate(status=TaskStatus.DONE),
        project_id=child_project_id,
    )


@pytest.mark.asyncio
async def test_update_member_child_task_returns_404_when_task_not_in_children() -> None:
    parent_project_id = uuid4()
    task_id = uuid4()
    user = SimpleNamespace(id="caller-user")

    repo = AsyncMock()
    member_repo = AsyncMock()
    task_repo = AsyncMock()

    repo.list_children_with_task_count.return_value = [
        SimpleNamespace(id=uuid4(), user_id="owner-a", name="Child A"),
        SimpleNamespace(id=uuid4(), user_id="owner-b", name="Child B"),
    ]
    task_repo.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await update_member_child_task(
            project_id=parent_project_id,
            task_id=task_id,
            update=TaskUpdate(status=TaskStatus.DONE),
            user=user,
            repo=repo,
            member_repo=member_repo,
            task_repo=task_repo,
        )

    assert exc_info.value.status_code == 404
