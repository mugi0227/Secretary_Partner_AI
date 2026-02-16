"""
Background scheduler service for periodic jobs.

Handles periodic tasks like weekly achievement auto-generation.
Uses APScheduler for in-process scheduling without external dependencies.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.logger import logger
from app.interfaces.achievement_repository import IAchievementRepository
from app.interfaces.chat_session_repository import IChatSessionRepository
from app.interfaces.heartbeat_event_repository import IHeartbeatEventRepository
from app.interfaces.heartbeat_settings_repository import IHeartbeatSettingsRepository
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.notification_repository import INotificationRepository
from app.interfaces.project_achievement_repository import IProjectAchievementRepository
from app.interfaces.project_member_repository import IProjectMemberRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.schedule_plan_repository import IDailySchedulePlanRepository
from app.interfaces.schedule_settings_repository import IScheduleSettingsRepository
from app.interfaces.schedule_snapshot_repository import IScheduleSnapshotRepository
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.enums import GenerationType
from app.services.achievement_service import generate_achievement
from app.services.daily_schedule_plan_service import DEFAULT_PLAN_DAYS, DailySchedulePlanService
from app.services.project_achievement_service import generate_project_achievement
from app.services.task_heartbeat_service import TaskHeartbeatService
from app.services.weekly_meeting_reminder_service import ensure_weekly_meeting_reminders
from app.utils.datetime_utils import get_user_today, normalize_timezone


class BackgroundScheduler:
    """
    Background scheduler for periodic jobs.

    Features:
    - Weekly achievement auto-generation (Friday 00:00)
    - Weekly project achievement auto-generation
    - Weekly meeting registration reminder tasks (Monday 00:00)
    - Startup check for missed runs (achievements + meeting reminders)
    - Staggered processing to avoid load spikes
    """

    def __init__(
        self,
        user_repo: IUserRepository,
        task_repo: ITaskRepository,
        achievement_repo: IAchievementRepository,
        project_repo: IProjectRepository,
        project_member_repo: IProjectMemberRepository,
        project_achievement_repo: IProjectAchievementRepository,
        notification_repo: INotificationRepository,
        llm_provider: ILLMProvider,
        schedule_settings_repo: IScheduleSettingsRepository,
        schedule_plan_repo: IDailySchedulePlanRepository,
        schedule_snapshot_repo: IScheduleSnapshotRepository,
        chat_repo: IChatSessionRepository,
        heartbeat_settings_repo: IHeartbeatSettingsRepository,
        heartbeat_event_repo: IHeartbeatEventRepository,
        task_assignment_repo: Optional[ITaskAssignmentRepository] = None,
    ):
        self._user_repo = user_repo
        self._task_repo = task_repo
        self._achievement_repo = achievement_repo
        self._project_repo = project_repo
        self._project_member_repo = project_member_repo
        self._project_achievement_repo = project_achievement_repo
        self._notification_repo = notification_repo
        self._llm_provider = llm_provider
        self._schedule_settings_repo = schedule_settings_repo
        self._schedule_plan_repo = schedule_plan_repo
        self._schedule_snapshot_repo = schedule_snapshot_repo
        self._chat_repo = chat_repo
        self._heartbeat_settings_repo = heartbeat_settings_repo
        self._heartbeat_event_repo = heartbeat_event_repo
        self._task_assignment_repo = task_assignment_repo
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._last_run: Optional[datetime] = None
        self._task_heartbeat_service = TaskHeartbeatService(
            task_repo=self._task_repo,
            chat_repo=self._chat_repo,
            settings_repo=self._heartbeat_settings_repo,
            event_repo=self._heartbeat_event_repo,
            user_repo=self._user_repo,
            project_repo=self._project_repo,
            llm_provider=self._llm_provider,
            task_assignment_repo=self._task_assignment_repo,
        )

    @staticmethod
    def _calculate_last_friday(now: Optional[datetime] = None) -> datetime:
        """
        Calculate the most recent Friday 00:00:00 UTC.

        If it is currently Friday before 01:00, returns the *previous* Friday
        to avoid racing with the scheduled cron job.
        """
        if now is None:
            now = datetime.utcnow()
        days_since_friday = (now.weekday() - 4) % 7  # 4 = Friday
        if days_since_friday == 0 and now.hour < 1:
            days_since_friday = 7
        return (now - timedelta(days=days_since_friday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    async def start(self):
        """Start the scheduler and check for missed runs."""
        settings = get_settings()

        # Only run scheduler in non-test environments
        if settings.ENVIRONMENT == "test":
            logger.info("Background scheduler disabled in test environment")
            return

        self._scheduler = AsyncIOScheduler()

        # Schedule weekly achievement generation for Friday at 00:00
        self._scheduler.add_job(
            self._run_weekly_achievement_generation,
            CronTrigger(day_of_week="fri", hour=0, minute=0),
            id="weekly_achievement_generation",
            name="Weekly Achievement Generation",
            replace_existing=True,
        )

        # Schedule weekly meeting reminder task creation for Monday at 00:00
        self._scheduler.add_job(
            self._run_weekly_meeting_reminder_generation,
            CronTrigger(day_of_week="mon", hour=0, minute=0),
            id="weekly_meeting_reminder_generation",
            name="Weekly Meeting Reminder Task Generation",
            replace_existing=True,
        )

        self._scheduler.add_job(
            self._run_daily_plan_generation,
            CronTrigger(minute=5),
            id="daily_schedule_plan_generation",
            name="Daily Schedule Plan Generation",
            replace_existing=True,
        )

        self._scheduler.add_job(
            self._run_task_heartbeat_checks,
            CronTrigger(minute="*/30"),
            id="task_heartbeat_checks",
            name="Task Heartbeat Checks",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info(
            "Background scheduler started:\n"
            "  - Weekly achievement generation: Friday 00:00\n"
            "  - Weekly meeting reminder tasks: Monday 00:00\n"
            "  - Daily schedule plan generation: every hour\n"
            "  - Task heartbeat checks: every 30 minutes"
        )

        # Check for missed runs in background (non-blocking)
        asyncio.create_task(self._check_and_run_missed_background())

    async def stop(self):
        """Stop the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("Background scheduler stopped")

    async def _check_and_run_missed_background(self):
        """Background wrapper for checking missed runs with error handling."""
        try:
            logger.info("Starting background check for missed scheduled jobs...")
            await self._check_and_run_missed()
            logger.info("Background check for missed scheduled jobs completed")
        except Exception as e:
            logger.error(f"Background check for missed scheduled jobs failed: {e}")

    async def _check_and_run_missed(self):
        """
        Check if a weekly run was missed and execute if needed.

        A run is considered missed if:
        - It's past Friday 00:00 of the current week
        - No AUTO achievement has been created since last Friday 00:00
        """
        now = datetime.utcnow()
        last_friday = self._calculate_last_friday(now)

        # Check personal achievements
        await self._check_and_run_missed_personal(now, last_friday)

        # Check project achievements
        await self._check_and_run_missed_projects(now, last_friday)

        # Check weekly meeting reminder tasks
        await self._check_and_run_missed_meeting_reminders()

    async def _check_and_run_missed_personal(self, now: datetime, last_friday: datetime):
        """Check and run missed personal achievement generation."""
        users = await self._user_repo.list_all()

        needs_run = False
        for user in users:
            latest = await self._achievement_repo.get_latest(str(user.id))
            if latest is None:
                # User never had an achievement - needs generation
                needs_run = True
                break
            if latest.generation_type == GenerationType.AUTO and latest.created_at >= last_friday:
                # Already ran this week for this user
                continue
            # Check if there are completed tasks since last achievement
            completed_tasks = await self._task_repo.list_completed_in_period(
                user_id=str(user.id),
                period_start=latest.period_end,
                period_end=now,
            )
            if completed_tasks:
                needs_run = True
                break

        if needs_run:
            logger.info("Missed weekly personal achievement generation detected, running now...")
            await self._run_weekly_achievement_generation(last_friday)
        else:
            logger.info("No missed weekly personal achievement generation detected")

    async def _check_and_run_missed_projects(self, now: datetime, last_friday: datetime):
        """Check and run missed project achievement generation."""
        # Collect all unique project IDs
        all_projects = set()
        users = await self._user_repo.list_all()
        for user in users:
            projects = await self._project_repo.list(str(user.id))
            for project in projects:
                all_projects.add(project.id)

        if not all_projects:
            logger.info("No projects found, skipping project achievement check")
            return

        needs_run = False
        for project_id in all_projects:
            latest = await self._project_achievement_repo.get_latest(project_id)
            if latest is None:
                # Project never had an achievement - check if it has any completed tasks
                # We'll let the generation function handle this check
                needs_run = True
                break
            if latest.generation_type == GenerationType.AUTO and latest.created_at >= last_friday:
                # Already ran this week for this project
                continue
            # If latest achievement is older than last Friday, needs run
            needs_run = True
            break

        if needs_run:
            logger.info("Missed weekly project achievement generation detected, running now...")
            await self._run_weekly_project_achievement_generation(last_friday)
        else:
            logger.info("No missed weekly project achievement generation detected")

    async def _check_and_run_missed_meeting_reminders(self):
        """
        Check if weekly meeting reminder tasks were missed and create if needed.

        This runs on startup and delegates to ensure_weekly_meeting_reminders(),
        which has built-in duplicate detection logic.
        """
        logger.info("Checking for missed weekly meeting reminder task generation...")

        try:
            results = await ensure_weekly_meeting_reminders(
                user_repo=self._user_repo,
                task_repo=self._task_repo,
            )

            if results["tasks_created"] > 0:
                logger.info(
                    f"Created {results['tasks_created']} missed weekly meeting reminder tasks "
                    f"({results['users_processed']} users processed)"
                )
            else:
                logger.info("No missed weekly meeting reminder tasks detected")

        except Exception as e:
            logger.error(f"Failed to check for missed weekly meeting reminder tasks: {e}")

    async def _run_weekly_achievement_generation(self, last_friday: Optional[datetime] = None):
        """
        Run weekly achievement generation for all users.

        Features:
        - Staggered processing with random delays (1-10 seconds between users)
        - Error isolation (one user's failure doesn't affect others)
        - Only generates if there are new completed tasks
        """
        if last_friday is None:
            last_friday = self._calculate_last_friday()

        logger.info("Starting weekly achievement generation...")

        try:
            users = await self._user_repo.list_all()
            logger.info(f"Processing {len(users)} users for weekly achievement generation")

            generated_count = 0
            skipped_count = 0
            error_count = 0

            for i, user in enumerate(users):
                # Staggered processing: random delay between 1-10 seconds
                if i > 0:
                    delay = random.uniform(1.0, 10.0)
                    logger.debug(f"Waiting {delay:.1f}s before processing next user")
                    await asyncio.sleep(delay)

                try:
                    result = await self._generate_weekly_for_user(str(user.id), last_friday)
                    if result:
                        generated_count += 1
                        logger.info(f"Generated weekly achievement for user {user.id}")
                    else:
                        skipped_count += 1
                        logger.debug(f"Skipped user {user.id} (no new tasks)")
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error generating achievement for user {user.id}: {e}")

            logger.info(
                f"Weekly personal achievement generation completed: "
                f"{generated_count} generated, {skipped_count} skipped, {error_count} errors"
            )

            # Also generate project achievements
            await self._run_weekly_project_achievement_generation(last_friday)

            self._last_run = datetime.utcnow()

        except Exception as e:
            logger.error(f"Weekly achievement generation failed: {e}")

    async def _run_weekly_project_achievement_generation(self, last_friday: Optional[datetime] = None):
        """
        Run weekly project achievement generation for all projects.
        """
        if last_friday is None:
            last_friday = self._calculate_last_friday()

        logger.info("Starting weekly project achievement generation...")

        try:
            # Get all projects (we need to iterate through unique projects)
            all_projects = set()
            users = await self._user_repo.list_all()
            for user in users:
                projects = await self._project_repo.list(str(user.id))
                for project in projects:
                    all_projects.add(project.id)

            logger.info(f"Processing {len(all_projects)} projects for weekly achievement generation")

            generated_count = 0
            skipped_count = 0
            error_count = 0

            period_end = last_friday
            period_start = last_friday - timedelta(days=7)

            for i, project_id in enumerate(all_projects):
                # Staggered processing
                if i > 0:
                    delay = random.uniform(1.0, 10.0)
                    await asyncio.sleep(delay)

                try:
                    # Check if latest achievement already covers this period
                    latest = await self._project_achievement_repo.get_latest(project_id)
                    if latest and latest.period_end >= last_friday:
                        skipped_count += 1
                        continue

                    # Generate project achievement
                    achievement = await generate_project_achievement(
                        llm_provider=self._llm_provider,
                        task_repo=self._task_repo,
                        project_repo=self._project_repo,
                        project_member_repo=self._project_member_repo,
                        user_repo=self._user_repo,
                        project_achievement_repo=self._project_achievement_repo,
                        notification_repo=self._notification_repo,
                        project_id=project_id,
                        period_start=period_start,
                        period_end=period_end,
                        period_label=f"週次振り返り ({period_start.strftime('%m/%d')} - {period_end.strftime('%m/%d')})",
                        generation_type=GenerationType.AUTO,
                        task_assignment_repo=self._task_assignment_repo,
                    )

                    if achievement:
                        generated_count += 1
                        logger.info(f"Generated weekly project achievement for project {project_id}")
                    else:
                        skipped_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"Error generating project achievement for {project_id}: {e}")

            logger.info(
                f"Weekly project achievement generation completed: "
                f"{generated_count} generated, {skipped_count} skipped, {error_count} errors"
            )

        except Exception as e:
            logger.error(f"Weekly project achievement generation failed: {e}")

    async def _run_weekly_meeting_reminder_generation(self):
        """
        Run weekly meeting reminder task generation for all users with the feature enabled.

        Creates reminder tasks for the next 4-5 weeks (approximately 1 month).
        """
        logger.info("Starting weekly meeting reminder task generation...")

        try:
            results = await ensure_weekly_meeting_reminders(
                user_repo=self._user_repo,
                task_repo=self._task_repo,
            )

            logger.info(
                f"Weekly meeting reminder task generation completed: "
                f"{results['tasks_created']} tasks created, "
                f"{results['tasks_skipped']} skipped, "
                f"{results['users_processed']} users processed"
            )

        except Exception as e:
            logger.error(f"Weekly meeting reminder task generation failed: {e}")

    async def _run_daily_plan_generation(self):
        logger.info("Starting daily schedule plan generation...")
        users = await self._user_repo.list_all()
        plan_service = DailySchedulePlanService(
            task_repo=self._task_repo,
            project_repo=self._project_repo,
            assignment_repo=self._task_assignment_repo,
            snapshot_repo=self._schedule_snapshot_repo,
            user_repo=self._user_repo,
            settings_repo=self._schedule_settings_repo,
            plan_repo=self._schedule_plan_repo,
        )

        for user in users:
            timezone = normalize_timezone(user.timezone)
            today = get_user_today(timezone)
            existing = await self._schedule_plan_repo.get_by_date(str(user.id), today)
            if existing:
                continue
            try:
                await plan_service.build_plan(
                    user_id=str(user.id),
                    start_date=today,
                    max_days=DEFAULT_PLAN_DAYS,
                    from_now=False,
                    filter_by_assignee=True,
                    apply_plan_constraints=True,
                )
            except Exception as exc:
                logger.error(f"Failed to generate daily plan for user {user.id}: {exc}")
            await asyncio.sleep(random.uniform(0.2, 0.8))
        logger.info("Daily schedule plan generation completed")

    async def _run_task_heartbeat_checks(self):
        logger.info("Starting task heartbeat checks...")
        users = await self._user_repo.list_all()
        if not users:
            logger.info("No users found for task heartbeat checks")
            return

        for user in users:
            try:
                await self._task_heartbeat_service.run(str(user.id))
            except Exception as exc:
                logger.error(f"Failed to run task heartbeat for user {user.id}: {exc}")
            await asyncio.sleep(random.uniform(0.2, 0.8))

        logger.info("Task heartbeat checks completed")
    async def _generate_weekly_for_user(self, user_id: str, last_friday: datetime) -> bool:
        """
        Generate weekly achievement for a single user.

        Args:
            user_id: The user ID to generate for.
            last_friday: The Friday 00:00 UTC boundary for this period's end.

        Returns:
            True if achievement was generated, False if skipped
        """
        # Get latest achievement to determine period
        latest = await self._achievement_repo.get_latest(user_id)

        if latest:
            # Skip if latest achievement already covers this period
            if latest.period_end >= last_friday:
                return False

            period_start = latest.period_end
        else:
            # First time: use last 7 days from last_friday
            period_start = last_friday - timedelta(days=7)

        period_end = last_friday

        # Check if there are new completed tasks
        completed_tasks = await self._task_repo.list_completed_in_period(
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
        )

        if not completed_tasks:
            return False  # No new completions

        # Generate achievement
        await generate_achievement(
            llm_provider=self._llm_provider,
            task_repo=self._task_repo,
            achievement_repo=self._achievement_repo,
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            period_label=f"週次振り返り ({period_start.strftime('%m/%d')} - {period_end.strftime('%m/%d')})",
            generation_type=GenerationType.AUTO,
        )

        return True


# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


async def get_background_scheduler() -> BackgroundScheduler:
    """Get the global background scheduler instance."""
    global _scheduler
    if _scheduler is None:
        from app.api.deps import (
            get_achievement_repository,
            get_chat_session_repository,
            get_daily_schedule_plan_repository,
            get_heartbeat_event_repository,
            get_heartbeat_settings_repository,
            get_llm_provider,
            get_notification_repository,
            get_project_achievement_repository,
            get_project_member_repository,
            get_project_repository,
            get_schedule_settings_repository,
            get_schedule_snapshot_repository,
            get_task_assignment_repository,
            get_task_repository,
            get_user_repository,
        )

        _scheduler = BackgroundScheduler(
            user_repo=get_user_repository(),
            task_repo=get_task_repository(),
            achievement_repo=get_achievement_repository(),
            project_repo=get_project_repository(),
            project_member_repo=get_project_member_repository(),
            project_achievement_repo=get_project_achievement_repository(),
            notification_repo=get_notification_repository(),
            llm_provider=get_llm_provider(),
            schedule_settings_repo=get_schedule_settings_repository(),
            schedule_plan_repo=get_daily_schedule_plan_repository(),
            schedule_snapshot_repo=get_schedule_snapshot_repository(),
            chat_repo=get_chat_session_repository(),
            heartbeat_settings_repo=get_heartbeat_settings_repository(),
            heartbeat_event_repo=get_heartbeat_event_repository(),
            task_assignment_repo=get_task_assignment_repository(),
        )
    return _scheduler


async def start_background_scheduler():
    """Start the global background scheduler."""
    scheduler = await get_background_scheduler()
    await scheduler.start()


async def stop_background_scheduler():
    """Stop the global background scheduler."""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None
