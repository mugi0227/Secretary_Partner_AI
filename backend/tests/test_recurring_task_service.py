"""
Tests for RecurringTaskService occurrence calculation logic.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import EnergyLevel, Priority, RecurringTaskFrequency
from app.models.recurring_task import RecurringTask
from app.services.recurring_task_service import RecurringTaskService


def _make_definition(
    frequency: RecurringTaskFrequency,
    weekday: int | None = None,
    day_of_month: int | None = None,
    custom_interval_days: int | None = None,
    anchor_date: date | None = None,
) -> RecurringTask:
    """Helper to create a RecurringTask definition for testing."""
    return RecurringTask(
        id=uuid4(),
        user_id="test_user",
        title="Test Recurring Task",
        frequency=frequency,
        weekday=weekday,
        day_of_month=day_of_month,
        custom_interval_days=custom_interval_days,
        anchor_date=anchor_date or date.today(),
        importance=Priority.MEDIUM,
        urgency=Priority.MEDIUM,
        energy_level=EnergyLevel.LOW,
        is_active=True,
        created_at="2025-01-01T00:00:00",
        updated_at="2025-01-01T00:00:00",
    )


class TestNextOccurrenceDaily:
    """Tests for DAILY frequency."""

    def test_daily_returns_next_day(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.DAILY)
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result == date(2025, 3, 11)

    def test_daily_year_boundary(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.DAILY)
        result = svc._next_occurrence_after(defn, date(2025, 12, 31))
        assert result == date(2026, 1, 1)


class TestNextOccurrenceWeekly:
    """Tests for WEEKLY frequency."""

    def test_weekly_next_occurrence_same_week(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        # Wednesday(2) after Monday(0), weekday=4 (Friday)
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=4)
        monday = date(2025, 3, 10)  # Monday
        result = svc._next_occurrence_after(defn, monday)
        assert result == date(2025, 3, 14)  # Friday

    def test_weekly_next_occurrence_next_week(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        # After Friday(4), weekday=1 (Tuesday) -> next Tuesday
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=1)
        friday = date(2025, 3, 14)  # Friday
        result = svc._next_occurrence_after(defn, friday)
        assert result == date(2025, 3, 18)  # Next Tuesday

    def test_weekly_after_same_weekday(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=0)
        monday = date(2025, 3, 10)  # Monday
        result = svc._next_occurrence_after(defn, monday)
        assert result == date(2025, 3, 17)  # Next Monday

    def test_weekly_no_weekday_returns_none(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=None)
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result is None


class TestNextOccurrenceBiweekly:
    """Tests for BIWEEKLY frequency."""

    def test_biweekly_aligned_to_anchor(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        # Anchor on Monday 2025-03-03, weekday=0 (Monday)
        anchor = date(2025, 3, 3)  # Monday
        defn = _make_definition(
            RecurringTaskFrequency.BIWEEKLY, weekday=0, anchor_date=anchor
        )
        # After anchor Monday, next is 2 weeks later
        result = svc._next_occurrence_after(defn, anchor)
        assert result == date(2025, 3, 17)  # 2 weeks later

    def test_biweekly_skips_off_weeks(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        anchor = date(2025, 3, 3)  # Monday
        defn = _make_definition(
            RecurringTaskFrequency.BIWEEKLY, weekday=0, anchor_date=anchor
        )
        # After 2025-03-10 (off week Monday), should jump to 2025-03-17
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result == date(2025, 3, 17)

    def test_biweekly_no_weekday_returns_none(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.BIWEEKLY, weekday=None)
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result is None


class TestNextOccurrenceMonthly:
    """Tests for MONTHLY frequency."""

    def test_monthly_same_month(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.MONTHLY, day_of_month=20)
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result == date(2025, 3, 20)

    def test_monthly_past_day_goes_next_month(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.MONTHLY, day_of_month=5)
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result == date(2025, 4, 5)

    def test_monthly_day_31_in_short_month(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.MONTHLY, day_of_month=31)
        # After Feb 28, should use March 31
        result = svc._next_occurrence_after(defn, date(2025, 2, 28))
        assert result == date(2025, 3, 31)

    def test_monthly_day_31_in_april(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.MONTHLY, day_of_month=31)
        # April has 30 days, so clamped to 30
        result = svc._next_occurrence_after(defn, date(2025, 3, 31))
        assert result == date(2025, 4, 30)

    def test_monthly_no_day_returns_none(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.MONTHLY, day_of_month=None)
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result is None


class TestNextOccurrenceBimonthly:
    """Tests for BIMONTHLY frequency."""

    def test_bimonthly_aligned_to_anchor(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        anchor = date(2025, 1, 15)
        defn = _make_definition(
            RecurringTaskFrequency.BIMONTHLY, day_of_month=15, anchor_date=anchor
        )
        # After Jan 15, next should be March 15
        result = svc._next_occurrence_after(defn, date(2025, 1, 15))
        assert result == date(2025, 3, 15)

    def test_bimonthly_between_months(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        anchor = date(2025, 1, 15)
        defn = _make_definition(
            RecurringTaskFrequency.BIMONTHLY, day_of_month=15, anchor_date=anchor
        )
        # After Feb 10, next should be March 15 (aligned to Jan + 2 months)
        result = svc._next_occurrence_after(defn, date(2025, 2, 10))
        assert result == date(2025, 3, 15)

    def test_bimonthly_no_day_returns_none(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.BIMONTHLY, day_of_month=None)
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result is None


class TestNextOccurrenceCustom:
    """Tests for CUSTOM frequency."""

    def test_custom_every_3_days(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        anchor = date(2025, 3, 1)
        defn = _make_definition(
            RecurringTaskFrequency.CUSTOM,
            custom_interval_days=3,
            anchor_date=anchor,
        )
        result = svc._next_occurrence_after(defn, date(2025, 3, 1))
        assert result == date(2025, 3, 4)

    def test_custom_between_intervals(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        anchor = date(2025, 3, 1)
        defn = _make_definition(
            RecurringTaskFrequency.CUSTOM,
            custom_interval_days=5,
            anchor_date=anchor,
        )
        # After Mar 3 (2 days in), next should be Mar 6
        result = svc._next_occurrence_after(defn, date(2025, 3, 3))
        assert result == date(2025, 3, 6)

    def test_custom_before_anchor_returns_anchor(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        anchor = date(2025, 3, 10)
        defn = _make_definition(
            RecurringTaskFrequency.CUSTOM,
            custom_interval_days=7,
            anchor_date=anchor,
        )
        result = svc._next_occurrence_after(defn, date(2025, 3, 5))
        assert result == anchor

    def test_custom_no_interval_returns_none(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(
            RecurringTaskFrequency.CUSTOM, custom_interval_days=None
        )
        result = svc._next_occurrence_after(defn, date(2025, 3, 10))
        assert result is None


class TestAlignToWeekday:
    """Tests for _align_to_weekday helper."""

    def test_align_forward(self):
        # Monday to Friday
        result = RecurringTaskService._align_to_weekday(date(2025, 3, 10), 4)
        assert result == date(2025, 3, 14)

    def test_align_same_day(self):
        # Monday to Monday
        result = RecurringTaskService._align_to_weekday(date(2025, 3, 10), 0)
        assert result == date(2025, 3, 10)

    def test_align_backward_wraps(self):
        # Friday to Monday wraps to next Monday
        result = RecurringTaskService._align_to_weekday(date(2025, 3, 14), 0)
        assert result == date(2025, 3, 17)


class TestComputeStartNotBefore:
    """Tests for _compute_start_not_before helper."""

    def test_daily_same_day(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.DAILY)
        result = svc._compute_start_not_before(defn, date(2025, 3, 12))
        assert result == datetime(2025, 3, 12, 0, 0, 0)

    def test_weekly_returns_monday(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=4)
        # Friday 2025-03-14 => Monday of that week is 2025-03-10
        result = svc._compute_start_not_before(defn, date(2025, 3, 14))
        assert result == datetime(2025, 3, 10, 0, 0, 0)

    def test_weekly_monday_occurrence(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=0)
        # Monday 2025-03-10 => start_not_before is same Monday
        result = svc._compute_start_not_before(defn, date(2025, 3, 10))
        assert result == datetime(2025, 3, 10, 0, 0, 0)

    def test_biweekly_returns_monday(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.BIWEEKLY, weekday=2)
        # Wednesday 2025-03-12 => Monday is 2025-03-10
        result = svc._compute_start_not_before(defn, date(2025, 3, 12))
        assert result == datetime(2025, 3, 10, 0, 0, 0)

    def test_monthly_returns_first_of_month(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.MONTHLY, day_of_month=20)
        result = svc._compute_start_not_before(defn, date(2025, 3, 20))
        assert result == datetime(2025, 3, 1, 0, 0, 0)

    def test_bimonthly_returns_first_of_month(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.BIMONTHLY, day_of_month=15)
        result = svc._compute_start_not_before(defn, date(2025, 5, 15))
        assert result == datetime(2025, 5, 1, 0, 0, 0)

    def test_custom_same_day(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(
            RecurringTaskFrequency.CUSTOM, custom_interval_days=10
        )
        result = svc._compute_start_not_before(defn, date(2025, 3, 15))
        assert result == datetime(2025, 3, 15, 0, 0, 0)


class TestComputeDueDate:
    """Tests for _compute_due_date helper."""

    def test_daily_same_day(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.DAILY)
        result = svc._compute_due_date(defn, date(2025, 3, 12))
        assert result == datetime(2025, 3, 12, 0, 0, 0)

    def test_weekly_returns_sunday(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=0)
        # Monday 2025-03-10 => Sunday is 2025-03-16
        result = svc._compute_due_date(defn, date(2025, 3, 10))
        assert result == datetime(2025, 3, 16, 0, 0, 0)

    def test_weekly_friday_returns_sunday(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=4)
        # Friday 2025-03-14 => Sunday is 2025-03-16
        result = svc._compute_due_date(defn, date(2025, 3, 14))
        assert result == datetime(2025, 3, 16, 0, 0, 0)

    def test_weekly_sunday_returns_same_sunday(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.WEEKLY, weekday=6)
        # Sunday 2025-03-16 => same Sunday
        result = svc._compute_due_date(defn, date(2025, 3, 16))
        assert result == datetime(2025, 3, 16, 0, 0, 0)

    def test_biweekly_returns_sunday(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.BIWEEKLY, weekday=2)
        # Wednesday 2025-03-12 => Sunday is 2025-03-16
        result = svc._compute_due_date(defn, date(2025, 3, 12))
        assert result == datetime(2025, 3, 16, 0, 0, 0)

    def test_monthly_same_day(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(RecurringTaskFrequency.MONTHLY, day_of_month=20)
        result = svc._compute_due_date(defn, date(2025, 3, 20))
        assert result == datetime(2025, 3, 20, 0, 0, 0)

    def test_custom_same_day(self):
        svc = RecurringTaskService(recurring_repo=None, task_repo=None)  # type: ignore
        defn = _make_definition(
            RecurringTaskFrequency.CUSTOM, custom_interval_days=5
        )
        result = svc._compute_due_date(defn, date(2025, 3, 15))
        assert result == datetime(2025, 3, 15, 0, 0, 0)


@pytest.mark.asyncio
async def test_ensure_upcoming_tasks_skips_duplicate_occurrence_on_recheck():
    today = datetime.now(timezone.utc).date()
    definition = _make_definition(
        RecurringTaskFrequency.DAILY,
        anchor_date=today - timedelta(days=1),
    )
    recurring_repo = AsyncMock()
    recurring_repo.list.return_value = [definition]

    task_repo = AsyncMock()
    existing_for_today = SimpleNamespace(due_date=datetime.combine(today, datetime.min.time()))
    task_repo.list_by_recurring_task.side_effect = [
        [],
        [existing_for_today],
    ]

    service = RecurringTaskService(
        recurring_repo=recurring_repo,
        task_repo=task_repo,
        lookahead_days=0,
    )
    result = await service.ensure_upcoming_tasks("test_user")

    assert result["created_count"] == 0
    task_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_upcoming_tasks_handles_unique_violation_as_duplicate():
    today = datetime.now(timezone.utc).date()
    definition = _make_definition(
        RecurringTaskFrequency.DAILY,
        anchor_date=today - timedelta(days=1),
    )
    recurring_repo = AsyncMock()
    recurring_repo.list.return_value = [definition]

    task_repo = AsyncMock()
    task_repo.list_by_recurring_task.side_effect = [
        [],
        [],
    ]
    task_repo.create.side_effect = IntegrityError(
        statement=None,
        params=None,
        orig=Exception("UNIQUE constraint failed"),
    )

    service = RecurringTaskService(
        recurring_repo=recurring_repo,
        task_repo=task_repo,
        lookahead_days=0,
    )
    result = await service.ensure_upcoming_tasks("test_user")

    assert result["created_count"] == 0
    assert task_repo.create.await_count == 1
    assert recurring_repo.update.await_count == 1
    update_call = recurring_repo.update.await_args
    assert update_call.args[0] == "test_user"
    assert update_call.args[1] == definition.id
    assert update_call.args[2].last_generated_date == today
