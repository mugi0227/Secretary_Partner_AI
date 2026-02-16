"""
Recurring task service.

Generates upcoming task instances from recurring task definitions.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from app.core.logger import setup_logger
from app.interfaces.recurring_task_repository import IRecurringTaskRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.enums import CreatedBy, RecurringTaskFrequency
from app.models.recurring_task import RecurringTask, RecurringTaskUpdate
from app.models.task import TaskCreate
from app.utils.datetime_utils import ensure_utc, normalize_timezone, now_utc, user_date_to_utc

logger = setup_logger(__name__)


class RecurringTaskService:
    """Service for generating task instances from recurring definitions."""

    def __init__(
        self,
        recurring_repo: IRecurringTaskRepository,
        task_repo: ITaskRepository,
        lookahead_days: int = 30,
        user_repo: Optional[IUserRepository] = None,
    ):
        self.recurring_repo = recurring_repo
        self.task_repo = task_repo
        self.lookahead_days = lookahead_days
        self.user_repo = user_repo

    async def ensure_upcoming_tasks(self, user_id: str) -> dict:
        """Ensure upcoming task instances exist within the lookahead window.

        Generates ALL occurrences within the lookahead period.
        Skips creation if a task already exists for that occurrence (by due_date match).
        """
        user_timezone = await self._resolve_user_timezone(user_id)
        local_tz = ZoneInfo(user_timezone)
        now = now_utc()
        today = now.astimezone(local_tz).date()
        upcoming_limit = today + timedelta(days=self.lookahead_days)
        created: list[dict] = []

        definitions = await self.recurring_repo.list(
            user_id, include_inactive=False, limit=200
        )
        for definition in definitions:
            existing_tasks = await self.task_repo.list_by_recurring_task(
                user_id,
                definition.id,
                start_after=now - timedelta(days=1),
                end_before=user_date_to_utc(upcoming_limit + timedelta(days=1), user_timezone),
            )
            existing_due_dates = {
                ensure_utc(task.due_date).astimezone(local_tz).date()
                for task in existing_tasks
                if task.due_date
            }
            seen_due_dates = set(existing_due_dates)

            base_reference = today - timedelta(days=1)
            reference_date = max(base_reference, definition.last_generated_date or base_reference)
            latest_date: Optional[date] = None

            while True:
                next_date = self._next_occurrence_after(definition, reference_date)
                if not next_date or next_date > upcoming_limit:
                    break

                if next_date < today:
                    reference_date = next_date
                    continue

                if next_date in seen_due_dates:
                    reference_date = next_date
                    latest_date = next_date
                    continue

                if await self._has_existing_occurrence(
                    user_id,
                    definition.id,
                    next_date,
                    user_timezone,
                ):
                    seen_due_dates.add(next_date)
                    reference_date = next_date
                    latest_date = next_date
                    continue

                due_datetime = self._compute_due_date(definition, next_date, user_timezone)
                start_not_before = self._compute_start_not_before(
                    definition, next_date, user_timezone
                )
                task_data = TaskCreate(
                    title=definition.title,
                    description=definition.description,
                    purpose=definition.purpose,
                    project_id=definition.project_id,
                    phase_id=definition.phase_id,
                    importance=definition.importance,
                    urgency=definition.urgency,
                    energy_level=definition.energy_level,
                    estimated_minutes=definition.estimated_minutes,
                    due_date=due_datetime,
                    start_not_before=start_not_before,
                    recurring_task_id=definition.id,
                    created_by=CreatedBy.AGENT,
                )
                try:
                    task = await self.task_repo.create(user_id, task_data)
                except IntegrityError:
                    # Another concurrent worker already created this occurrence.
                    seen_due_dates.add(next_date)
                    reference_date = next_date
                    latest_date = next_date
                    continue

                created.append(task.model_dump(mode="json"))
                seen_due_dates.add(next_date)

                reference_date = next_date
                latest_date = next_date

            if latest_date:
                await self.recurring_repo.update(
                    user_id,
                    definition.id,
                    RecurringTaskUpdate(last_generated_date=latest_date),
                )

        return {"created_count": len(created), "tasks": created}

    async def _has_existing_occurrence(
        self,
        user_id: str,
        recurring_task_id: UUID,
        occurrence_date: date,
        user_timezone: str,
    ) -> bool:
        local_tz = ZoneInfo(user_timezone)
        day_start = user_date_to_utc(occurrence_date, user_timezone)
        day_end = user_date_to_utc(occurrence_date + timedelta(days=1), user_timezone)
        existing = await self.task_repo.list_by_recurring_task(
            user_id=user_id,
            recurring_task_id=recurring_task_id,
            start_after=day_start,
            end_before=day_end,
        )
        return any(
            task.due_date and ensure_utc(task.due_date).astimezone(local_tz).date() == occurrence_date
            for task in existing
        )

    def _next_occurrence_after(
        self, definition: RecurringTask, after_date: date
    ) -> Optional[date]:
        """Calculate the next occurrence date after the given date."""
        freq = definition.frequency

        if freq == RecurringTaskFrequency.DAILY:
            candidate = after_date + timedelta(days=1)
            if definition.weekdays:
                # Skip days not in the allowed weekdays list
                for _ in range(7):
                    if candidate.weekday() in definition.weekdays:
                        return candidate
                    candidate += timedelta(days=1)
                return None  # should not reach here
            return candidate

        elif freq == RecurringTaskFrequency.WEEKLY:
            if definition.weekday is None:
                return None
            candidate = self._align_to_weekday(after_date, definition.weekday)
            if candidate <= after_date:
                candidate += timedelta(days=7)
            return candidate

        elif freq == RecurringTaskFrequency.BIWEEKLY:
            if definition.weekday is None:
                return None
            candidate = self._align_to_weekday(after_date, definition.weekday)
            if candidate <= after_date:
                candidate += timedelta(days=7)
            # Align to biweekly rhythm from anchor
            while True:
                weeks_diff = (candidate - definition.anchor_date).days // 7
                if weeks_diff % 2 == 0:
                    return candidate
                candidate += timedelta(days=7)

        elif freq == RecurringTaskFrequency.MONTHLY:
            if definition.day_of_month is None:
                return None
            return self._next_monthly(after_date, definition.day_of_month, interval=1)

        elif freq == RecurringTaskFrequency.BIMONTHLY:
            if definition.day_of_month is None:
                return None
            return self._next_monthly_from_anchor(
                after_date, definition.day_of_month, definition.anchor_date, interval=2
            )

        elif freq == RecurringTaskFrequency.CUSTOM:
            if definition.custom_interval_days is None:
                return None
            days_since = (after_date - definition.anchor_date).days
            if days_since < 0:
                return definition.anchor_date
            intervals = days_since // definition.custom_interval_days + 1
            return definition.anchor_date + timedelta(
                days=intervals * definition.custom_interval_days
            )

        return None

    @staticmethod
    def _align_to_weekday(current: date, target_weekday: int) -> date:
        """Align a date to the target weekday (0=Monday)."""
        delta = (target_weekday - current.weekday()) % 7
        return current + timedelta(days=delta)

    def _compute_due_date(
        self,
        definition: RecurringTask,
        occurrence_date: date,
        user_timezone: Optional[str] = None,
    ) -> datetime:
        """Compute due_date for a generated task instance.

        For weekly/biweekly tasks, the due_date is the end of the week (Sunday).
        For all other frequencies, the due_date is the occurrence date itself.
        """
        freq = definition.frequency
        if freq in (
            RecurringTaskFrequency.WEEKLY,
            RecurringTaskFrequency.BIWEEKLY,
        ):
            days_to_sunday = 6 - occurrence_date.weekday()
            target_date = occurrence_date + timedelta(days=days_to_sunday)
        else:
            target_date = occurrence_date

        if user_timezone is None:
            return datetime.combine(target_date, datetime.min.time())
        return user_date_to_utc(target_date, user_timezone)

    def _compute_start_not_before(
        self,
        definition: RecurringTask,
        occurrence_date: date,
        user_timezone: Optional[str] = None,
    ) -> datetime:
        """Compute start_not_before for a generated task instance.

        DAILY / CUSTOM: same as occurrence date (only actionable that day).
        WEEKLY / BIWEEKLY: Monday of the week containing the occurrence.
        MONTHLY / BIMONTHLY: 1st of the month containing the occurrence.
        """
        freq = definition.frequency
        if freq in (
            RecurringTaskFrequency.WEEKLY,
            RecurringTaskFrequency.BIWEEKLY,
        ):
            target_date = occurrence_date - timedelta(days=occurrence_date.weekday())
        elif freq in (
            RecurringTaskFrequency.MONTHLY,
            RecurringTaskFrequency.BIMONTHLY,
        ):
            target_date = occurrence_date.replace(day=1)
        else:
            target_date = occurrence_date

        if user_timezone is None:
            return datetime.combine(target_date, datetime.min.time())
        return user_date_to_utc(target_date, user_timezone)

    async def _resolve_user_timezone(self, user_id: str) -> str:
        if self.user_repo is None:
            return normalize_timezone(None)
        try:
            user = await self.user_repo.get(UUID(user_id))
        except (ValueError, TypeError):
            user = None
        return normalize_timezone(user.timezone if user else None)

    @staticmethod
    def _next_monthly(after_date: date, day_of_month: int, interval: int) -> date:
        """Find the next monthly occurrence after the given date."""
        year, month = after_date.year, after_date.month
        max_day = min(day_of_month, calendar.monthrange(year, month)[1])
        candidate = date(year, month, max_day)
        if candidate <= after_date:
            # Move to next month(s)
            for _ in range(interval):
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            max_day = min(day_of_month, calendar.monthrange(year, month)[1])
            candidate = date(year, month, max_day)
        return candidate

    @staticmethod
    def _next_monthly_from_anchor(
        after_date: date, day_of_month: int, anchor_date: date, interval: int
    ) -> date:
        """Find the next bimonthly occurrence aligned to the anchor date."""
        anchor_month_index = anchor_date.year * 12 + anchor_date.month - 1
        current_month_index = after_date.year * 12 + after_date.month - 1

        months_diff = current_month_index - anchor_month_index
        if months_diff < 0:
            target_month_index = anchor_month_index
        else:
            # Find next aligned month
            remainder = months_diff % interval
            if remainder == 0:
                # Check if we're past the day in this month
                year = current_month_index // 12
                month = current_month_index % 12 + 1
                max_day = min(day_of_month, calendar.monthrange(year, month)[1])
                if date(year, month, max_day) <= after_date:
                    target_month_index = current_month_index + interval
                else:
                    target_month_index = current_month_index
            else:
                target_month_index = current_month_index + (interval - remainder)

        year = target_month_index // 12
        month = target_month_index % 12 + 1
        max_day = min(day_of_month, calendar.monthrange(year, month)[1])
        return date(year, month, max_day)
