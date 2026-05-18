"""Unit tests for scheduler tools."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.collaboration import TaskAssignment
from app.models.enums import (
    CreatedBy,
    EnergyLevel,
    Priority,
    ProjectStatus,
    ProjectVisibility,
    TaskStatus,
)
from app.models.project import Project
from app.models.task import Task, TaskUpdate
from app.models.user import UserAccount
from app.tools.scheduler_tools import ApplyScheduleRequestInput, apply_schedule_request
from app.utils.datetime_utils import ensure_utc, get_user_today, user_date_to_utc


def _make_task(
    *,
    title: str,
    user_id: str,
    project_id: UUID | None = None,
    status: TaskStatus = TaskStatus.TODO,
    pinned_date: datetime | None = None,
) -> Task:
    now = datetime(2026, 2, 8, 9, 0, 0)
    return Task(
        id=uuid4(),
        user_id=user_id,
        title=title,
        status=status,
        project_id=project_id,
        pinned_date=pinned_date,
        importance=Priority.MEDIUM,
        urgency=Priority.MEDIUM,
        energy_level=EnergyLevel.LOW,
        estimated_minutes=30,
        dependency_ids=[],
        same_day_allowed=True,
        min_gap_days=0,
        progress=0,
        created_by=CreatedBy.USER,
        created_at=now,
        updated_at=now,
        touchpoint_steps=[],
    )


def _make_project(*, project_id: UUID, user_id: str, visibility: ProjectVisibility) -> Project:
    now = datetime(2026, 2, 8, 9, 0, 0)
    return Project(
        id=project_id,
        user_id=user_id,
        name="Project",
        visibility=visibility,
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _make_assignment(*, task_id: UUID, assignee_id: str, owner_id: str) -> TaskAssignment:
    now = datetime(2026, 2, 8, 9, 0, 0)
    return TaskAssignment(
        id=uuid4(),
        user_id=owner_id,
        task_id=task_id,
        assignee_id=assignee_id,
        created_at=now,
        updated_at=now,
    )


class MockTaskRepository:
    """Mock task repository with methods used by apply_schedule_request."""

    def __init__(self, tasks: list[Task]):
        self.tasks = {task.id: task for task in tasks}

    async def get(
        self,
        user_id: str,
        task_id: UUID,
        project_id: UUID | None = None,
    ) -> Task | None:
        task = self.tasks.get(task_id)
        if not task or task.user_id != user_id:
            return None
        if project_id is not None and task.project_id != project_id:
            return None
        return task

    async def get_by_id(self, user_id: str, task_id: UUID) -> Task | None:
        del user_id
        return self.tasks.get(task_id)

    async def list(
        self,
        user_id: str,
        project_id: UUID | None = None,
        status: str | None = None,
        parent_id: UUID | None = None,
        include_done: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        del project_id, status, parent_id
        tasks = [task for task in self.tasks.values() if task.user_id == user_id]
        if not include_done:
            tasks = [task for task in tasks if task.status != TaskStatus.DONE]
        return tasks[offset:offset + limit]

    async def update(
        self,
        user_id: str,
        task_id: UUID,
        update: TaskUpdate,
        project_id: UUID | None = None,
    ) -> Task:
        del user_id, project_id
        task = self.tasks[task_id]
        for field, value in update.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        return task

    async def get_many(self, task_ids: list[UUID]) -> list[Task]:
        return [self.tasks[task_id] for task_id in task_ids if task_id in self.tasks]


class MockTaskAssignmentRepository:
    """Mock assignment repository with list_for_assignee support."""

    def __init__(self, assignments: list[TaskAssignment]):
        self.assignments = assignments

    async def list_for_assignee(self, user_id: str) -> list[TaskAssignment]:
        return [assignment for assignment in self.assignments if assignment.assignee_id == user_id]


class MockProjectRepository:
    """Mock project repository with list support."""

    def __init__(self, projects: list[Project]):
        self.projects = projects

    async def get(self, user_id: str, project_id: UUID) -> Project | None:
        for project in self.projects:
            if project.id == project_id and project.user_id == user_id:
                return project
        return None

    async def list(
        self,
        user_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Project]:
        del status
        projects = [project for project in self.projects if project.user_id == user_id]
        return projects[offset:offset + limit]


class MockUserRepository:
    def __init__(self, timezone: str):
        self.timezone = timezone

    async def get(self, user_id: UUID) -> UserAccount:
        now = datetime(2026, 2, 8, 9, 0, 0)
        return UserAccount(
            id=user_id,
            provider_issuer="issuer",
            provider_sub="sub",
            email=None,
            display_name=None,
            first_name=None,
            last_name=None,
            username=None,
            password_hash=None,
            timezone=self.timezone,
            enable_weekly_meeting_reminder=False,
            created_at=now,
            updated_at=now,
        )


def _to_local_date(value: datetime | None, timezone: str):
    if value is None:
        return None
    utc_value = ensure_utc(value)
    if utc_value is None:
        return None
    return utc_value.astimezone(ZoneInfo(timezone)).date()


@pytest.mark.asyncio
async def test_apply_schedule_request_pins_focus_task_for_today() -> None:
    user_id = str(uuid4())
    timezone = "Asia/Tokyo"
    focus_task = _make_task(title="Prepare design proposal", user_id=user_id)
    other_task = _make_task(title="Clean inbox", user_id=user_id)
    task_repo = MockTaskRepository([focus_task, other_task])
    assignment_repo = MockTaskAssignmentRepository([])
    project_repo = MockProjectRepository([])
    user_repo = MockUserRepository(timezone)

    result = await apply_schedule_request(
        user_id=user_id,
        task_repo=task_repo,
        assignment_repo=assignment_repo,
        project_repo=project_repo,
        input_data=ApplyScheduleRequestInput(
            request="I want to focus on design today",
            focus_keywords=["design"],
            max_focus_tasks=1,
        ),
        user_repo=user_repo,
    )

    today = get_user_today(timezone)
    assert result["selected_count"] == 1
    assert result["updated_task_ids"] == [str(focus_task.id)]
    assert focus_task.pinned_date is not None
    assert _to_local_date(focus_task.pinned_date, timezone) == today
    assert other_task.pinned_date is None


@pytest.mark.asyncio
async def test_apply_schedule_request_excludes_unassigned_team_tasks() -> None:
    user_id = str(uuid4())
    team_project_id = uuid4()
    assigned_task = _make_task(title="API refactor", user_id=user_id, project_id=team_project_id)
    unassigned_task = _make_task(title="API docs", user_id=user_id, project_id=team_project_id)
    task_repo = MockTaskRepository([assigned_task, unassigned_task])
    assignment_repo = MockTaskAssignmentRepository(
        [_make_assignment(task_id=assigned_task.id, assignee_id=user_id, owner_id=user_id)]
    )
    project_repo = MockProjectRepository(
        [_make_project(project_id=team_project_id, user_id=user_id, visibility=ProjectVisibility.TEAM)]
    )

    result = await apply_schedule_request(
        user_id=user_id,
        task_repo=task_repo,
        assignment_repo=assignment_repo,
        project_repo=project_repo,
        input_data=ApplyScheduleRequestInput(
            request="Prioritize API work",
            focus_keywords=["api"],
            max_focus_tasks=10,
        ),
    )

    selected_ids = {item["task_id"] for item in result["selected_tasks"]}
    assert str(assigned_task.id) in selected_ids
    assert str(unassigned_task.id) not in selected_ids


@pytest.mark.asyncio
async def test_apply_schedule_request_unpins_avoided_tasks_for_today() -> None:
    user_id = str(uuid4())
    timezone = "Asia/Tokyo"
    today = get_user_today(timezone)
    today_datetime = user_date_to_utc(today, timezone)
    focus_task = _make_task(title="Design review", user_id=user_id)
    avoided_task = _make_task(title="Legacy bugfix", user_id=user_id, pinned_date=today_datetime)
    task_repo = MockTaskRepository([focus_task, avoided_task])
    assignment_repo = MockTaskAssignmentRepository([])
    project_repo = MockProjectRepository([])
    user_repo = MockUserRepository(timezone)

    result = await apply_schedule_request(
        user_id=user_id,
        task_repo=task_repo,
        assignment_repo=assignment_repo,
        project_repo=project_repo,
        input_data=ApplyScheduleRequestInput(
            request="Focus design today",
            focus_keywords=["design"],
            avoid_keywords=["bugfix"],
            unpin_avoided_today=True,
        ),
        user_repo=user_repo,
    )

    assert str(avoided_task.id) in result["unpinned_task_ids"]
    assert avoided_task.pinned_date is None
