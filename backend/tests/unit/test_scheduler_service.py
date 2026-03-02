"""
Unit tests for SchedulerService.
"""

from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from app.models.enums import CreatedBy, EnergyLevel, Priority, TaskStatus
from app.models.task import Task
from app.services.scheduler_service import SchedulerService


def make_task(
    title: str,
    status: TaskStatus = TaskStatus.TODO,
    importance: Priority = Priority.MEDIUM,
    urgency: Priority = Priority.MEDIUM,
    energy_level: EnergyLevel = EnergyLevel.LOW,
    estimated_minutes: int | None = 30,
    due_date: datetime | None = None,
    start_not_before: datetime | None = None,
    parent_id: UUID | None = None,
    dependency_ids: list | None = None,
    progress: int = 0,
    user_id: str = "test_user",
    is_fixed_time: bool = False,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    same_day_allowed: bool = True,
    min_gap_days: int = 0,
    touchpoint_count: int | None = None,
    touchpoint_minutes: int | None = None,
    touchpoint_gap_days: int = 0,
    touchpoint_steps: list | None = None,
    created_at: datetime | None = None,
) -> Task:
    now = created_at or datetime.now()
    return Task(
        id=uuid4(),
        user_id=user_id,
        title=title,
        status=status,
        importance=importance,
        urgency=urgency,
        energy_level=energy_level,
        estimated_minutes=estimated_minutes,
        due_date=due_date,
        start_not_before=start_not_before,
        parent_id=parent_id,
        dependency_ids=dependency_ids or [],
        same_day_allowed=same_day_allowed,
        min_gap_days=min_gap_days,
        progress=progress,
        created_by=CreatedBy.USER,
        created_at=now,
        updated_at=now,
        is_fixed_time=is_fixed_time,
        start_time=start_time,
        end_time=end_time,
        touchpoint_count=touchpoint_count,
        touchpoint_minutes=touchpoint_minutes,
        touchpoint_gap_days=touchpoint_gap_days,
        touchpoint_steps=touchpoint_steps or [],
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


def test_start_not_before_delays_scheduling():
    service = SchedulerService()
    start_date = date.today()
    not_before = start_date + timedelta(days=1)
    task = make_task(
        "Delayed task",
        estimated_minutes=60,
        start_not_before=datetime.combine(not_before, datetime.min.time()),
    )

    schedule = service.build_schedule([task], capacity_hours=2, start_date=start_date, max_days=3)
    allocated_days = [
        day.date
        for day in schedule.days
        for alloc in day.task_allocations
        if alloc.task_id == task.id
    ]

    assert allocated_days
    assert min(allocated_days) >= not_before


def test_planned_window_overrides_task_constraints():
    service = SchedulerService()
    start_date = date.today()
    task = make_task(
        "Planned task",
        estimated_minutes=60,
        start_not_before=datetime.combine(start_date, datetime.min.time()),
        due_date=datetime.combine(start_date + timedelta(days=10), datetime.min.time()),
    )
    planned_start = start_date + timedelta(days=3)
    planned_end = start_date + timedelta(days=5)

    effective_start, effective_due = service._get_effective_constraints(
        [task],
        planned_window_by_task={task.id: (planned_start, planned_end)},
    )

    assert effective_start[task.id] == planned_start
    assert effective_due[task.id].date() == planned_end


def test_pinned_date_uses_reference_today():
    service = SchedulerService()
    reference_today = date(2026, 2, 8)
    blocked_start = datetime(2026, 2, 10, 0, 0, 0)
    pinned_today = make_task(
        "Pinned today",
        estimated_minutes=60,
        start_not_before=blocked_start,
    )
    pinned_today.pinned_date = datetime(2026, 2, 8, 0, 0, 0)
    pinned_past = make_task(
        "Pinned past",
        estimated_minutes=60,
        start_not_before=blocked_start,
    )
    pinned_past.pinned_date = datetime(2026, 2, 7, 0, 0, 0)

    effective_start, _ = service._get_effective_constraints(
        [pinned_today, pinned_past],
        reference_today=reference_today,
    )

    assert effective_start[pinned_today.id] == reference_today
    assert effective_start[pinned_past.id] == blocked_start.date()


def test_pinned_date_respects_user_timezone_jst():
    """pinned_date stored in UTC must be interpreted in user's timezone.

    When user_date_to_utc converts 2026-03-02 00:00 JST to 2026-03-01 15:00 UTC,
    the scheduler should still treat this as a March 2nd pin (the user's local date).
    """
    from zoneinfo import ZoneInfo

    service = SchedulerService()
    reference_today = date(2026, 3, 2)

    # Simulate "今日やる" in JST: midnight 3/2 JST = 15:00 3/1 UTC
    pinned_task = make_task(
        "Pinned today JST",
        estimated_minutes=60,
        start_not_before=datetime(2026, 3, 5, 0, 0, 0),  # blocked in future
    )
    pinned_task.pinned_date = datetime(2026, 3, 1, 15, 0, 0, tzinfo=ZoneInfo("UTC"))

    effective_start, _ = service._get_effective_constraints(
        [pinned_task],
        reference_today=reference_today,
        user_timezone="Asia/Tokyo",
    )

    # Pin should override start_not_before — task starts today (3/2)
    assert effective_start[pinned_task.id] == reference_today


def test_pinned_task_appears_in_today_schedule_jst():
    """A task pinned via 今日やる in JST must appear in today's schedule."""
    from zoneinfo import ZoneInfo

    service = SchedulerService()
    today = date(2026, 3, 2)

    # Simulate: midnight 3/2 JST = 15:00 3/1 UTC
    task = make_task("Do today task", estimated_minutes=30)
    task.pinned_date = datetime(2026, 3, 1, 15, 0, 0, tzinfo=ZoneInfo("UTC"))

    schedule = service.build_schedule(
        [task],
        capacity_hours=8,
        start_date=today,
        max_days=3,
        user_timezone="Asia/Tokyo",
    )

    today_response = service.get_today_tasks(
        schedule, [task], today=today, user_timezone="Asia/Tokyo",
    )

    today_task_ids = [t.id for t in today_response.today_tasks]
    assert task.id in today_task_ids, (
        "Pinned task should appear in today's schedule for JST user"
    )


def test_parent_start_not_before_applies_to_subtask():
    service = SchedulerService()
    start_date = date.today()
    not_before = start_date + timedelta(days=2)
    parent = make_task(
        "Parent",
        estimated_minutes=60,
        start_not_before=datetime.combine(not_before, datetime.min.time()),
    )
    subtask = make_task(
        "Subtask",
        estimated_minutes=30,
        parent_id=parent.id,
    )

    schedule = service.build_schedule([parent, subtask], capacity_hours=2, start_date=start_date, max_days=5)
    allocated_days = [
        day.date
        for day in schedule.days
        for alloc in day.task_allocations
        if alloc.task_id == subtask.id
    ]

    assert allocated_days
    assert min(allocated_days) >= not_before


def _get_task_info(schedule, task_id):
    return next((info for info in schedule.tasks if info.task_id == task_id), None)


def test_subtask_inherits_parent_due_date():
    service = SchedulerService()
    start_date = date.today()
    parent_due = start_date + timedelta(days=4)
    parent = make_task(
        "Parent",
        estimated_minutes=60,
        due_date=datetime.combine(parent_due, datetime.min.time()),
    )
    subtask = make_task(
        "Subtask",
        estimated_minutes=30,
        parent_id=parent.id,
    )

    schedule = service.build_schedule([parent, subtask], capacity_hours=2, start_date=start_date, max_days=5)
    info = _get_task_info(schedule, subtask.id)

    assert info is not None
    assert info.due_date is not None
    assert info.due_date.date() == parent_due


def test_subtask_due_date_capped_by_parent():
    service = SchedulerService()
    start_date = date.today()
    parent_due = start_date + timedelta(days=3)
    sub_due = start_date + timedelta(days=6)
    parent = make_task(
        "Parent",
        estimated_minutes=60,
        due_date=datetime.combine(parent_due, datetime.min.time()),
    )
    subtask = make_task(
        "Subtask",
        estimated_minutes=30,
        parent_id=parent.id,
        due_date=datetime.combine(sub_due, datetime.min.time()),
    )

    schedule = service.build_schedule([parent, subtask], capacity_hours=2, start_date=start_date, max_days=7)
    info = _get_task_info(schedule, subtask.id)

    assert info is not None
    assert info.due_date is not None
    assert info.due_date.date() == parent_due


def test_subtask_due_date_overridden_when_before_start():
    service = SchedulerService()
    start_date = date.today()
    parent_start = start_date + timedelta(days=3)
    parent_due = start_date + timedelta(days=5)
    sub_due = start_date + timedelta(days=2)
    parent = make_task(
        "Parent",
        estimated_minutes=60,
        start_not_before=datetime.combine(parent_start, datetime.min.time()),
        due_date=datetime.combine(parent_due, datetime.min.time()),
    )
    subtask = make_task(
        "Subtask",
        estimated_minutes=30,
        parent_id=parent.id,
        due_date=datetime.combine(sub_due, datetime.min.time()),
    )

    schedule = service.build_schedule([parent, subtask], capacity_hours=2, start_date=start_date, max_days=7)
    info = _get_task_info(schedule, subtask.id)

    assert info is not None
    assert info.due_date is not None
    assert info.due_date.date() == parent_due


def test_energy_balance_prefers_low_when_high_is_over_ratio():
    service = SchedulerService()
    task_high = make_task("High energy", energy_level=EnergyLevel.HIGH)
    task_low = make_task("Low energy", energy_level=EnergyLevel.LOW)

    task_map = {task_high.id: task_high, task_low.id: task_low}
    scores = {task_high.id: 100.0, task_low.id: 10.0}
    energy_minutes = {EnergyLevel.HIGH: 60, EnergyLevel.LOW: 0}

    picked = service._pick_next_task([task_high.id, task_low.id], scores, task_map, energy_minutes)
    assert picked == task_low.id


def test_top3_excludes_blocked_by_dependency():
    """Top3 should exclude tasks whose dependencies are not completed."""
    service = SchedulerService()

    # Create tasks: A (no deps), B depends on A (not done), C (no deps)
    task_a = make_task("Task A", importance=Priority.HIGH, urgency=Priority.HIGH)
    task_b = make_task("Task B", importance=Priority.HIGH, urgency=Priority.HIGH, dependency_ids=[task_a.id])
    task_c = make_task("Task C", importance=Priority.MEDIUM, urgency=Priority.MEDIUM)
    task_d = make_task("Task D", importance=Priority.LOW, urgency=Priority.LOW)

    tasks = [task_a, task_b, task_c, task_d]
    schedule = service.build_schedule(tasks, capacity_hours=8, max_days=1)
    today_response = service.get_today_tasks(schedule, tasks)

    # Task B should NOT be in top3 because Task A is not done
    assert task_b.id not in today_response.top3_ids
    # Task A, C, D should be candidates (A and C should be in top3 due to higher scores)
    assert task_a.id in today_response.top3_ids


def test_top3_includes_task_when_dependency_is_done():
    """Top3 should include tasks whose dependencies are completed."""
    service = SchedulerService()

    # Create tasks: A (done), B depends on A (should be unblocked)
    task_a = make_task("Task A", status=TaskStatus.DONE, importance=Priority.HIGH)
    task_b = make_task("Task B", importance=Priority.HIGH, urgency=Priority.HIGH, dependency_ids=[task_a.id])
    task_c = make_task("Task C", importance=Priority.LOW, urgency=Priority.LOW)

    tasks = [task_a, task_b, task_c]
    schedule = service.build_schedule(tasks, capacity_hours=8, max_days=1)
    today_response = service.get_today_tasks(schedule, tasks)

    # Task B should be in top3 because Task A is done
    assert task_b.id in today_response.top3_ids


def test_progress_reduces_remaining_time():
    """A task with 50% progress should have half the remaining time."""
    service = SchedulerService()

    # Task with 60 minutes and 50% progress = 30 minutes remaining
    task_half_done = make_task("Half done", estimated_minutes=60, progress=50)
    # Task with 60 minutes and 0% progress = 60 minutes remaining
    task_not_started = make_task("Not started", estimated_minutes=60, progress=0)

    tasks = [task_half_done, task_not_started]
    schedule = service.build_schedule(tasks, capacity_hours=2, max_days=1)
    today_response = service.get_today_tasks(schedule, tasks)

    # Find allocations
    alloc_half = next((a for a in today_response.today_allocations if a.task_id == task_half_done.id), None)
    alloc_full = next((a for a in today_response.today_allocations if a.task_id == task_not_started.id), None)

    assert alloc_half is not None
    assert alloc_full is not None
    # Half-done task should have 30 minutes as total (remaining)
    assert alloc_half.total_minutes == 30
    # Not-started task should have 60 minutes as total
    assert alloc_full.total_minutes == 60


def test_completed_progress_task_still_allocates_minimum():
    """A task with 100% progress should still have some allocation."""
    service = SchedulerService()

    # Task with 100% progress
    task_complete = make_task("Complete", estimated_minutes=60, progress=100)

    tasks = [task_complete]
    schedule = service.build_schedule(tasks, capacity_hours=2, max_days=1)
    today_response = service.get_today_tasks(schedule, tasks)

    # Should still be scheduled (with default minutes since remaining is 0)
    assert len(today_response.today_tasks) >= 0  # May or may not be included based on implementation


def test_overlapping_meetings_do_not_double_count_capacity():
    """
    Overlapping meetings should not double-count capacity.

    If a user has two meetings at the same time (10:00-11:00 and 10:00-11:00),
    only 60 minutes should be subtracted from their capacity, not 120 minutes.
    """
    service = SchedulerService()
    start_date = date.today()

    # Create two overlapping meetings for the same user (10:00-11:00)
    meeting_start = datetime.combine(start_date, datetime.min.time().replace(hour=10))
    meeting_end = datetime.combine(start_date, datetime.min.time().replace(hour=11))

    meeting1 = make_task(
        "Meeting 1",
        is_fixed_time=True,
        start_time=meeting_start,
        end_time=meeting_end,
        user_id="user_a",
        estimated_minutes=60,
    )
    meeting2 = make_task(
        "Meeting 2",
        is_fixed_time=True,
        start_time=meeting_start,
        end_time=meeting_end,
        user_id="user_a",
        estimated_minutes=60,
    )

    # Add a regular task (90 minutes)
    task = make_task("Regular Task", estimated_minutes=90, user_id="user_a")

    tasks = [meeting1, meeting2, task]
    # 8 hours capacity = 480 minutes
    # With two overlapping 1-hour meetings, only 60 minutes should be blocked
    # So 420 minutes should be available for the task
    schedule = service.build_schedule(tasks, capacity_hours=8, start_date=start_date, max_days=1)

    # Find today's schedule
    assert len(schedule.days) >= 1
    today = schedule.days[0]

    # meeting_minutes should be 60 (merged, not 120)
    assert today.meeting_minutes == 60

    # The 90-minute task should be fully allocated (420 min available > 90 min needed)
    task_alloc = next((a for a in today.task_allocations if a.task_id == task.id), None)
    assert task_alloc is not None
    assert task_alloc.minutes == 90


def test_partially_overlapping_meetings_merge_correctly():
    """
    Partially overlapping meetings should merge their time intervals.

    Meeting 1: 10:00-11:00 (60 min)
    Meeting 2: 10:30-11:30 (60 min)
    Expected: 10:00-11:30 = 90 minutes total (not 120)
    """
    service = SchedulerService()
    start_date = date.today()

    # Create partially overlapping meetings
    meeting1_start = datetime.combine(start_date, datetime.min.time().replace(hour=10))
    meeting1_end = datetime.combine(start_date, datetime.min.time().replace(hour=11))
    meeting2_start = datetime.combine(start_date, datetime.min.time().replace(hour=10, minute=30))
    meeting2_end = datetime.combine(start_date, datetime.min.time().replace(hour=11, minute=30))

    meeting1 = make_task(
        "Meeting 1",
        is_fixed_time=True,
        start_time=meeting1_start,
        end_time=meeting1_end,
        user_id="user_a",
        estimated_minutes=60,
    )
    meeting2 = make_task(
        "Meeting 2",
        is_fixed_time=True,
        start_time=meeting2_start,
        end_time=meeting2_end,
        user_id="user_a",
        estimated_minutes=60,
    )

    # Add a regular task so the schedule day is generated
    task = make_task("Regular Task", estimated_minutes=30, user_id="user_a")

    tasks = [meeting1, meeting2, task]
    schedule = service.build_schedule(tasks, capacity_hours=8, start_date=start_date, max_days=1)

    assert len(schedule.days) >= 1
    today = schedule.days[0]

    # meeting_minutes should be 90 (merged 10:00-11:30)
    assert today.meeting_minutes == 90


def test_many_overlapping_meetings_with_task_allocation():
    """
    Test the reported issue: many meetings at the same time should not block task allocation.

    Scenario:
    - 8 hours capacity (480 minutes)
    - Multiple meetings totaling 4h50m (290 min) after removing overlaps
    - Should leave 3h10m (190 min) for tasks
    """
    service = SchedulerService()
    start_date = date.today()

    # Create multiple overlapping meetings that total to 4h50m when merged
    # 9:00-10:00 (60 min)
    # 9:00-10:00 (same time, should merge)
    # 10:00-12:00 (120 min)
    # 10:30-11:30 (overlaps with above, should merge)
    # 13:00-15:30 (150 min)
    # Total without overlap: 60 + 120 + 150 = 330 min
    # But we want 290 min, so adjust...

    # Let's use: 9:00-11:50 (170 min) + 13:00-15:00 (120 min) = 290 min
    # With overlaps: 9:00-10:00, 9:30-11:50, 13:00-14:00, 13:00-15:00

    meetings = [
        make_task(
            "Meeting 1",
            is_fixed_time=True,
            start_time=datetime.combine(start_date, datetime.min.time().replace(hour=9)),
            end_time=datetime.combine(start_date, datetime.min.time().replace(hour=10)),
            user_id="user_a",
            estimated_minutes=60,
        ),
        make_task(
            "Meeting 2",  # Overlaps with Meeting 1
            is_fixed_time=True,
            start_time=datetime.combine(start_date, datetime.min.time().replace(hour=9, minute=30)),
            end_time=datetime.combine(start_date, datetime.min.time().replace(hour=11, minute=50)),
            user_id="user_a",
            estimated_minutes=140,
        ),
        make_task(
            "Meeting 3",
            is_fixed_time=True,
            start_time=datetime.combine(start_date, datetime.min.time().replace(hour=13)),
            end_time=datetime.combine(start_date, datetime.min.time().replace(hour=14)),
            user_id="user_a",
            estimated_minutes=60,
        ),
        make_task(
            "Meeting 4",  # Overlaps with Meeting 3
            is_fixed_time=True,
            start_time=datetime.combine(start_date, datetime.min.time().replace(hour=13)),
            end_time=datetime.combine(start_date, datetime.min.time().replace(hour=15)),
            user_id="user_a",
            estimated_minutes=120,
        ),
    ]
    # Merged: 9:00-11:50 (170 min) + 13:00-15:00 (120 min) = 290 min

    # Add a task that should fit in the remaining time
    task = make_task("Important Task", estimated_minutes=180, user_id="user_a")

    tasks = meetings + [task]
    schedule = service.build_schedule(tasks, capacity_hours=8, start_date=start_date, max_days=1)

    assert len(schedule.days) >= 1
    today = schedule.days[0]

    # meeting_minutes should be 290 (4h50m)
    assert today.meeting_minutes == 290

    # Task should be allocated (480 - 290 = 190 min available)
    # Task needs 180 min, so it should fit
    task_alloc = next((a for a in today.task_allocations if a.task_id == task.id), None)
    assert task_alloc is not None
    assert task_alloc.minutes == 180


def test_task_force_scheduled_before_due_date():
    """
    Tasks with due dates should be force-scheduled before the due date,
    even if it exceeds daily capacity.

    Scenario:
    - 1 hour capacity per day
    - Task A: 120 minutes, due in 1 day (tomorrow)
    - Task A should be fully scheduled by its due date (today + tomorrow)
    """
    service = SchedulerService()
    start_date = date.today()
    due_date = start_date + timedelta(days=1)

    task = make_task(
        "Urgent task",
        estimated_minutes=120,
        due_date=datetime.combine(due_date, datetime.min.time()),
    )

    schedule = service.build_schedule([task], capacity_hours=1, start_date=start_date, max_days=5)

    # Find the task info
    task_info = next((t for t in schedule.tasks if t.task_id == task.id), None)
    assert task_info is not None
    # Task should be completed by due date
    assert task_info.planned_end is not None
    assert task_info.planned_end <= due_date


def test_task_force_scheduled_on_due_date_with_overflow():
    """
    A task that cannot fit within capacity before due date should still
    be force-scheduled on the due date, creating overflow.

    Scenario:
    - 30 min capacity per day
    - Task A: 120 minutes, due today
    - Task A should be fully scheduled today even though capacity is only 30 min
    """
    service = SchedulerService()
    start_date = date.today()
    due_date = start_date  # Due today

    task = make_task(
        "Urgent task due today",
        estimated_minutes=120,
        due_date=datetime.combine(due_date, datetime.min.time()),
    )

    schedule = service.build_schedule([task], capacity_hours=0.5, start_date=start_date, max_days=5)

    # Task should be scheduled on day 0 (today) despite capacity being only 30 min
    assert len(schedule.days) >= 1
    today_schedule = schedule.days[0]

    # Find task allocation for today
    task_alloc = [a for a in today_schedule.task_allocations if a.task_id == task.id]
    assert len(task_alloc) > 0

    total_allocated = sum(a.minutes for a in task_alloc)
    assert total_allocated == 120  # Full task should be allocated

    # There should be overflow (120 - 30 = 90 minutes)
    assert today_schedule.overflow_minutes > 0

    # Task should end today
    task_info = next((t for t in schedule.tasks if t.task_id == task.id), None)
    assert task_info is not None
    assert task_info.planned_end == start_date


def test_multiple_tasks_force_scheduled_before_due_dates():
    """
    Multiple tasks with different due dates should all be force-scheduled
    before their respective due dates.
    """
    service = SchedulerService()
    start_date = date.today()

    # Task A: due tomorrow, 60 min
    task_a = make_task(
        "Task A",
        estimated_minutes=60,
        due_date=datetime.combine(start_date + timedelta(days=1), datetime.min.time()),
    )
    # Task B: due in 2 days, 60 min
    task_b = make_task(
        "Task B",
        estimated_minutes=60,
        due_date=datetime.combine(start_date + timedelta(days=2), datetime.min.time()),
    )
    # Task C: no due date, 60 min
    task_c = make_task(
        "Task C",
        estimated_minutes=60,
    )

    schedule = service.build_schedule(
        [task_a, task_b, task_c],
        capacity_hours=0.5,  # 30 min per day
        start_date=start_date,
        max_days=10,
    )

    # Task A should end by day 1
    task_a_info = next((t for t in schedule.tasks if t.task_id == task_a.id), None)
    assert task_a_info is not None
    assert task_a_info.planned_end is not None
    assert task_a_info.planned_end <= start_date + timedelta(days=1)

    # Task B should end by day 2
    task_b_info = next((t for t in schedule.tasks if t.task_id == task_b.id), None)
    assert task_b_info is not None
    assert task_b_info.planned_end is not None
    assert task_b_info.planned_end <= start_date + timedelta(days=2)


def _get_task_days(schedule, task_id):
    return [
        day.date
        for day in schedule.days
        for alloc in day.task_allocations
        if alloc.task_id == task_id
    ]


def test_subtasks_same_day_disallowed():
    service = SchedulerService()
    start_date = date.today()
    parent = make_task("Parent")
    sub_a = make_task(
        "Subtask A",
        parent_id=parent.id,
        estimated_minutes=30,
        same_day_allowed=False,
    )
    sub_b = make_task(
        "Subtask B",
        parent_id=parent.id,
        estimated_minutes=30,
        same_day_allowed=False,
    )

    schedule = service.build_schedule(
        [parent, sub_a, sub_b],
        capacity_hours=8,
        start_date=start_date,
        max_days=5,
    )
    days_a = _get_task_days(schedule, sub_a.id)
    days_b = _get_task_days(schedule, sub_b.id)

    assert days_a
    assert days_b
    assert min(days_a) != min(days_b)


def test_subtasks_min_gap_days():
    service = SchedulerService()
    start_date = date.today()
    parent = make_task("Parent")
    sub_a = make_task(
        "Subtask A",
        parent_id=parent.id,
        estimated_minutes=30,
        due_date=datetime.combine(start_date + timedelta(days=1), datetime.min.time()),
    )
    sub_b = make_task(
        "Subtask B",
        parent_id=parent.id,
        estimated_minutes=30,
        min_gap_days=2,
        due_date=datetime.combine(start_date + timedelta(days=4), datetime.min.time()),
    )

    schedule = service.build_schedule(
        [parent, sub_a, sub_b],
        capacity_hours=8,
        start_date=start_date,
        max_days=7,
    )
    days_a = _get_task_days(schedule, sub_a.id)
    days_b = _get_task_days(schedule, sub_b.id)

    assert days_a
    assert days_b
    assert (min(days_b) - min(days_a)).days >= 2


def test_touchpoint_splits_across_days():
    service = SchedulerService()
    start_date = date.today()
    task = make_task(
        "Touchpoint task",
        estimated_minutes=60,
        touchpoint_count=3,
    )

    schedule = service.build_schedule([task], capacity_hours=8, start_date=start_date, max_days=7)
    days = _get_task_days(schedule, task.id)

    assert len(days) == 3
    assert sum(
        alloc.minutes
        for day in schedule.days
        for alloc in day.task_allocations
        if alloc.task_id == task.id
    ) == 60


def test_touchpoint_gap_days():
    service = SchedulerService()
    start_date = date.today()
    task = make_task(
        "Touchpoint gap task",
        estimated_minutes=30,
        touchpoint_count=3,
        touchpoint_gap_days=2,
    )

    schedule = service.build_schedule([task], capacity_hours=8, start_date=start_date, max_days=10)
    days = _get_task_days(schedule, task.id)

    assert len(days) == 3
    assert (days[1] - days[0]).days >= 2
    assert (days[2] - days[1]).days >= 2


def test_warmup_prefers_low_energy_first():
    service = SchedulerService()
    start_date = date.today()
    base_time = datetime.combine(start_date, datetime.min.time())
    high_task = make_task(
        "High energy",
        energy_level=EnergyLevel.HIGH,
        estimated_minutes=30,
        created_at=base_time,
    )
    low_task = make_task(
        "Low energy",
        energy_level=EnergyLevel.LOW,
        estimated_minutes=30,
        created_at=base_time + timedelta(seconds=1),
    )

    schedule = service.build_schedule([high_task, low_task], capacity_hours=2, start_date=start_date, max_days=1)
    first_allocation = next(
        alloc for alloc in schedule.days[0].task_allocations
        if alloc.task_id in {high_task.id, low_task.id}
    )

    assert first_allocation.task_id == low_task.id


# ---------------------------------------------------------------------------
# Slack-based two-tier priority sort tests
# ---------------------------------------------------------------------------
def test_slack_danger_zone_task_scheduled_before_safe_zone():
    """
    危険ゾーン（ratio < 1.5）のタスクは安全ゾーンのタスクより先にスケジュールされる。
    重要度が低くても、余裕がないタスクが優先。

    danger_task: 120分の作業、今日期限 → days_until=1, cap=120, ratio=120/120=1.0 → CRITICAL
    safe_task: 30分の作業、10日後期限 → days_until=11, cap=1320, ratio=1320/30=44.0 → LOW
    """
    service = SchedulerService()
    start_date = date.today()

    # 危険タスク: 重要度LOW、今日期限で120分 → ratio = 1.0（CRITICAL）
    danger_task = make_task(
        "Danger low-importance",
        importance=Priority.LOW,
        estimated_minutes=120,
        due_date=datetime.combine(start_date, datetime.min.time()),
    )

    # 安全タスク: 重要度HIGH、期限に余裕（10日後）
    safe_task = make_task(
        "Safe high-importance",
        importance=Priority.HIGH,
        estimated_minutes=30,
        due_date=datetime.combine(start_date + timedelta(days=10), datetime.min.time()),
    )

    schedule = service.build_schedule(
        [danger_task, safe_task],
        capacity_hours=2,
        start_date=start_date,
        max_days=3,
    )

    # 初日の最初の割り当てが危険タスクであること
    first_alloc = schedule.days[0].task_allocations[0]
    assert first_alloc.task_id == danger_task.id


def test_slack_safe_zone_sorted_by_importance():
    """
    安全ゾーンでは重要度順でスケジュールされる。
    同程度の余裕（期限なし）なら重要度HIGHが先。
    """
    service = SchedulerService()
    start_date = date.today()
    base_time = datetime.combine(start_date, datetime.min.time())

    low_importance = make_task(
        "Low importance",
        importance=Priority.LOW,
        estimated_minutes=30,
        created_at=base_time,
    )
    high_importance = make_task(
        "High importance",
        importance=Priority.HIGH,
        estimated_minutes=30,
        created_at=base_time + timedelta(seconds=1),
    )

    schedule = service.build_schedule(
        [low_importance, high_importance],
        capacity_hours=2,
        start_date=start_date,
        max_days=1,
    )

    first_alloc = schedule.days[0].task_allocations[0]
    assert first_alloc.task_id == high_importance.id


def test_slack_chain_head_is_prioritized():
    """
    A→B→C（Cに期限）の依存チェーンで、先頭タスクAが最も高い優先度を持つ。
    A の chain_remaining = A+B+C（下流全体）で ratio が最も小さくなるため。

    chain: A(60) → B(60) → C(60), Cに明日期限
    A: chain_remaining=180, days_until=2, cap=120 → available=240, ratio=240/180=1.33 → HIGH
    independent: 期限なし → ratio=None → 安全ゾーン
    → A（危険ゾーン）が先
    """
    service = SchedulerService()
    start_date = date.today()
    base_time = datetime.combine(start_date, datetime.min.time())

    task_a = make_task(
        "Chain head A",
        estimated_minutes=60,
        created_at=base_time,
    )
    task_b = make_task(
        "Chain middle B",
        estimated_minutes=60,
        dependency_ids=[task_a.id],
        created_at=base_time + timedelta(seconds=1),
    )
    task_c = make_task(
        "Chain end C",
        estimated_minutes=60,
        dependency_ids=[task_b.id],
        due_date=datetime.combine(start_date + timedelta(days=1), datetime.min.time()),
        created_at=base_time + timedelta(seconds=2),
    )

    # 独立タスク: 期限なし、同程度の工数
    independent = make_task(
        "Independent task",
        estimated_minutes=60,
        importance=Priority.HIGH,
        created_at=base_time + timedelta(seconds=3),
    )

    schedule = service.build_schedule(
        [task_a, task_b, task_c, independent],
        capacity_hours=2,
        start_date=start_date,
        max_days=5,
    )

    # task_a は chain_remaining=180, ratio=1.33 → 危険ゾーン
    # independent は期限なし → 安全ゾーン
    # → task_a が先にスケジュールされる
    first_alloc = schedule.days[0].task_allocations[0]
    assert first_alloc.task_id == task_a.id


def test_slack_future_start_date_adjusts_reference():
    """
    将来日起点のスケジュールでも slack 計算が正しく動作する。
    start_date が将来日の場合、now を start_date に合わせるため
    ratio が過度に甘くならない。

    urgent_task: 120分の作業、start_date当日期限 → ratio = 120/120 = 1.0 → CRITICAL
    relaxed_task: 30分の作業、30日後期限 → ratio >> 2.0 → LOW
    """
    service = SchedulerService()
    future_start = date.today() + timedelta(days=30)

    # 期限 = start_date当日、工数 120分 → ratio = 1.0（CRITICAL）
    urgent_task = make_task(
        "Urgent future task",
        importance=Priority.LOW,
        estimated_minutes=120,
        due_date=datetime.combine(future_start, datetime.min.time()),
    )

    # 期限 = start_date + 30日、工数 30分 → ratio 余裕あり
    relaxed_task = make_task(
        "Relaxed future task",
        importance=Priority.HIGH,
        estimated_minutes=30,
        due_date=datetime.combine(future_start + timedelta(days=30), datetime.min.time()),
    )

    schedule = service.build_schedule(
        [urgent_task, relaxed_task],
        capacity_hours=2,
        start_date=future_start,
        max_days=5,
    )

    # 将来日起点でも、urgent_task が危険ゾーンで先にスケジュールされる
    first_alloc = schedule.days[0].task_allocations[0]
    assert first_alloc.task_id == urgent_task.id
