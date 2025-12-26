"""
Unit tests for SchedulerService.
"""

from datetime import datetime, timedelta, date
from uuid import uuid4

import pytest

from app.models.task import Task
from app.models.enums import TaskStatus, Priority, EnergyLevel, CreatedBy
from app.services.scheduler_service import SchedulerService


def make_task(
    title: str,
    status: TaskStatus = TaskStatus.TODO,
    importance: Priority = Priority.MEDIUM,
    urgency: Priority = Priority.MEDIUM,
    energy_level: EnergyLevel = EnergyLevel.LOW,
    estimated_minutes: int | None = 30,
    due_date: datetime | None = None,
    dependency_ids: list | None = None,
) -> Task:
    now = datetime.now()
    return Task(
        id=uuid4(),
        user_id="test_user",
        title=title,
        status=status,
        importance=importance,
        urgency=urgency,
        energy_level=energy_level,
        estimated_minutes=estimated_minutes,
        due_date=due_date,
        dependency_ids=dependency_ids or [],
        created_by=CreatedBy.USER,
        created_at=now,
        updated_at=now,
    )


def test_due_bonus_monotonic_increase():
    service = SchedulerService()
    due = date.today() + timedelta(days=5)
    task = make_task("Due task", due_date=datetime.combine(due, datetime.min.time()))

    bonuses = []
    for offset in range(0, 6):
        ref_date = date.today() + timedelta(days=offset)
        bonuses.append(service._calculate_due_bonus(task, ref_date))

    assert all(bonuses[i] <= bonuses[i + 1] for i in range(len(bonuses) - 1))
    assert bonuses[-1] == 30.0


def test_dependency_missing_reason():
    service = SchedulerService()
    missing_id = uuid4()
    task_a = make_task("Task A", estimated_minutes=30)
    task_b = make_task("Task B", estimated_minutes=30, dependency_ids=[missing_id])

    schedule = service.build_schedule([task_a, task_b], capacity_hours=1, max_days=3)
    reasons = {item.task_id: item.reason for item in schedule.unscheduled_task_ids}

    assert task_b.id in reasons
    assert reasons[task_b.id] == "dependency_missing"


def test_dependency_unresolved_reason():
    service = SchedulerService()
    task_waiting = make_task("Waiting", status=TaskStatus.WAITING)
    task_blocked = make_task("Blocked", dependency_ids=[task_waiting.id])

    schedule = service.build_schedule([task_waiting, task_blocked], capacity_hours=1, max_days=3)
    reasons = {item.task_id: item.reason for item in schedule.unscheduled_task_ids}

    assert task_blocked.id in reasons
    assert reasons[task_blocked.id] == "dependency_unresolved"


def test_split_across_days():
    service = SchedulerService()
    task = make_task("Big task", estimated_minutes=120)

    schedule = service.build_schedule([task], capacity_hours=1, max_days=3)
    allocations = [
        alloc.minutes
        for day in schedule.days
        for alloc in day.task_allocations
        if alloc.task_id == task.id
    ]

    assert sum(allocations) == 120
    assert len(allocations) == 2


def test_energy_balance_prefers_low_when_high_is_over_ratio():
    service = SchedulerService()
    task_high = make_task("High energy", energy_level=EnergyLevel.HIGH)
    task_low = make_task("Low energy", energy_level=EnergyLevel.LOW)

    task_map = {task_high.id: task_high, task_low.id: task_low}
    scores = {task_high.id: 100.0, task_low.id: 10.0}
    energy_minutes = {EnergyLevel.HIGH: 60, EnergyLevel.LOW: 0}

    picked = service._pick_next_task([task_high.id, task_low.id], scores, task_map, energy_minutes)
    assert picked == task_low.id
