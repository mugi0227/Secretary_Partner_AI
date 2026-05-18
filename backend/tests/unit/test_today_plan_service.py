from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.enums import CreatedBy, Priority, TaskStatus
from app.models.task import Task
from app.models.today_plan import TodayPlanResponse
from app.services.today_plan_service import TodayPlanService
from app.utils.datetime_utils import user_date_to_utc


def _task(
    title: str,
    user_id: str,
    *,
    due_date: datetime | None = None,
    pinned_date: datetime | None = None,
    importance: Priority = Priority.MEDIUM,
    urgency: Priority = Priority.MEDIUM,
) -> Task:
    now = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    return Task(
        id=uuid4(),
        user_id=user_id,
        title=title,
        status=TaskStatus.TODO,
        importance=importance,
        urgency=urgency,
        estimated_minutes=30,
        due_date=due_date,
        pinned_date=pinned_date,
        created_by=CreatedBy.USER,
        created_at=now,
        updated_at=now,
    )


def _service(
    *,
    tasks: list[Task],
    user_timezone: str = "UTC",
) -> tuple[TodayPlanService, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    task_repo = AsyncMock()
    project_repo = AsyncMock()
    assignment_repo = AsyncMock()
    user_repo = AsyncMock()

    task_repo.list.return_value = tasks
    task_repo.get_by_id.return_value = None
    assignment_repo.list_for_assignee.return_value = []
    assignment_repo.list_all_for_user.return_value = []
    project_repo.list.return_value = []
    user_repo.get.return_value = SimpleNamespace(timezone=user_timezone)

    service = TodayPlanService(
        task_repo=task_repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
        user_repo=user_repo,
    )
    return service, task_repo, project_repo, assignment_repo, user_repo


@pytest.mark.asyncio
async def test_build_plan_separates_selected_tasks_from_recommendations() -> None:
    user_id = str(uuid4())
    today = date(2026, 1, 15)
    today_pin = user_date_to_utc(today, "UTC")
    selected_task = _task("Chosen by user", user_id, pinned_date=today_pin)
    urgent_task = _task(
        "Urgent recommendation",
        user_id,
        due_date=today_pin,
        importance=Priority.HIGH,
        urgency=Priority.HIGH,
    )
    service, *_ = _service(tasks=[selected_task, urgent_task])

    result = await service.build_plan(user_id, target_date=today)

    assert isinstance(result, TodayPlanResponse)
    assert [item.task.id for item in result.selected] == [selected_task.id]
    assert urgent_task.id in [item.task.id for item in result.recommendations]
    assert selected_task.id not in [item.task.id for item in result.recommendations]
    assert result.selected[0].selected is True
    assert "selected_for_today" in {reason.code for reason in result.selected[0].reasons}

    urgent_item = next(item for item in result.recommendations if item.task.id == urgent_task.id)
    component_codes = {component.code for component in urgent_item.score_breakdown}
    assert {"importance", "urgency", "due_date", "scope"}.issubset(component_codes)
    assert urgent_item.score == pytest.approx(
        sum(component.points for component in urgent_item.score_breakdown)
    )
    assert urgent_item.score_summary
    assert urgent_item.reasons[0].message


@pytest.mark.asyncio
async def test_update_selection_replaces_existing_today_pins() -> None:
    user_id = str(uuid4())
    today = date(2026, 1, 15)
    old_pin = user_date_to_utc(today, "UTC")
    old_selected = _task("Old selected", user_id, pinned_date=old_pin)
    new_selected = _task("New selected", user_id)
    service, task_repo, *_ = _service(tasks=[old_selected, new_selected])

    async def get_task(_user_id: str, task_id):
        if task_id == old_selected.id:
            return old_selected
        if task_id == new_selected.id:
            return new_selected
        return None

    task_repo.get.side_effect = get_task
    task_repo.update.return_value = new_selected

    await service.update_selection(user_id, [new_selected.id], target_date=today)

    update_calls = task_repo.update.await_args_list
    assert len(update_calls) == 2

    clear_call = update_calls[0]
    assert clear_call.args[1] == old_selected.id
    assert clear_call.args[2].pinned_date is None
    assert "pinned_date" in clear_call.args[2].model_fields_set

    pin_call = update_calls[1]
    assert pin_call.args[1] == new_selected.id
    assert pin_call.args[2].pinned_date == old_pin
