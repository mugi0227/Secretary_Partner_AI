"""
Heartbeat service for autonomous agent actions.

Processes pending AgentTasks and respects Quiet Hours.
"""

from datetime import datetime, time
from typing import Any

from app.core.config import get_settings
from app.core.logger import setup_logger
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.models.agent_task import AgentTask
from app.models.enums import ActionType

logger = setup_logger(__name__)


class HeartbeatService:
    """
    Service for processing autonomous agent tasks.

    Handles:
    - Checking pending AgentTasks
    - Respecting Quiet Hours
    - Executing scheduled actions
    - Error handling and retry logic
    """

    def __init__(self, agent_task_repo: IAgentTaskRepository):
        self.agent_task_repo = agent_task_repo
        settings = get_settings()

        # Parse quiet hours from config
        self.quiet_hours_start = self._parse_time(settings.QUIET_HOURS_START)
        self.quiet_hours_end = self._parse_time(settings.QUIET_HOURS_END)

    def _parse_time(self, time_str: str) -> time:
        """Parse time string (HH:MM) to time object."""
        hour, minute = map(int, time_str.split(":"))
        return time(hour, minute)

    def _is_quiet_hours(self, current_time: time) -> bool:
        """
        Check if current time is within quiet hours.

        Args:
            current_time: Time to check

        Returns:
            True if within quiet hours
        """
        return self.quiet_hours_start <= current_time < self.quiet_hours_end

    async def process_heartbeat(self, user_id: str) -> dict[str, Any]:
        """
        Process pending agent tasks for a user.

        This method should be called periodically by a scheduler.

        Args:
            user_id: Target user ID

        Returns:
            dict with status, processed count, and failed count
        """
        now = datetime.now()

        # Check quiet hours
        if self._is_quiet_hours(now.time()):
            logger.info(f"Heartbeat skipped for {user_id}: quiet hours")
            return {"status": "quiet_hours", "processed": 0, "failed": 0}

        # Get pending tasks
        pending_tasks = await self.agent_task_repo.get_pending(
            user_id=user_id,
            before=now,
            limit=10,
        )

        if not pending_tasks:
            logger.debug(f"No pending tasks for {user_id}")
            return {"status": "success", "processed": 0, "failed": 0}

        logger.info(f"Processing {len(pending_tasks)} pending tasks for {user_id}")

        processed = 0
        failed = 0

        for task in pending_tasks:
            try:
                # Execute the task
                await self._execute_agent_task(user_id, task)

                # Mark as completed
                await self.agent_task_repo.mark_completed(task.id)
                processed += 1

                logger.info(
                    f"Completed agent task {task.id} "
                    f"(type={task.action_type.value}, user={user_id})"
                )

            except Exception as e:
                # Mark as failed and increment retry
                error_msg = str(e)
                await self.agent_task_repo.mark_failed(task.id, error_msg)
                failed += 1

                logger.error(
                    f"Failed to execute agent task {task.id}: {error_msg}",
                    exc_info=True,
                )

        return {"status": "success", "processed": processed, "failed": failed}

    async def _execute_agent_task(self, user_id: str, task: AgentTask) -> dict[str, Any]:
        """
        Execute a specific agent task.

        Args:
            user_id: User ID
            task: Agent task to execute

        Returns:
            Execution result
        """
        logger.debug(f"Executing {task.action_type.value} for user {user_id}")

        if task.action_type == ActionType.CHECK_PROGRESS:
            return await self._check_progress(user_id, task)

        elif task.action_type == ActionType.ENCOURAGE:
            return await self._encourage(user_id, task)

        elif task.action_type == ActionType.WEEKLY_REVIEW:
            return await self._weekly_review(user_id, task)

        elif task.action_type == ActionType.DEADLINE_REMINDER:
            return await self._deadline_reminder(user_id, task)

        elif task.action_type == ActionType.MORNING_BRIEFING:
            return await self._morning_briefing(user_id, task)

        else:
            logger.warning(f"Unknown action type: {task.action_type}")
            return {"status": "unknown_action", "action_type": task.action_type.value}

    async def _check_progress(self, user_id: str, task: AgentTask) -> dict[str, Any]:
        """
        Check progress on a specific task.

        TODO: Implement task progress checking logic.
        This would:
        1. Get the target task
        2. Check its status
        3. Generate a gentle reminder if needed
        """
        logger.info(f"CHECK_PROGRESS action for user {user_id}")
        return {
            "action": "check_progress",
            "user_id": user_id,
            "target_task_id": str(task.payload.target_task_id)
            if task.payload.target_task_id
            else None,
        }

    async def _encourage(self, user_id: str, task: AgentTask) -> dict[str, Any]:
        """
        Send encouragement message.

        TODO: Implement encouragement logic.
        This would generate a supportive message based on:
        1. User's recent activity
        2. Task completion rate
        3. Time of day
        """
        logger.info(f"ENCOURAGE action for user {user_id}")
        return {
            "action": "encourage",
            "user_id": user_id,
            "tone": task.payload.message_tone,
        }

    async def _weekly_review(self, user_id: str, task: AgentTask) -> dict[str, Any]:
        """
        Generate weekly review.

        TODO: Implement weekly review logic.
        This would:
        1. Summarize tasks completed this week
        2. Highlight achievements
        3. Suggest improvements
        """
        logger.info(f"WEEKLY_REVIEW action for user {user_id}")
        return {"action": "weekly_review", "user_id": user_id}

    async def _deadline_reminder(self, user_id: str, task: AgentTask) -> dict[str, Any]:
        """
        Send deadline reminder.

        TODO: Implement deadline reminder logic.
        This would:
        1. Get tasks with upcoming deadlines
        2. Generate reminder message
        3. Suggest prioritization
        """
        logger.info(f"DEADLINE_REMINDER action for user {user_id}")
        return {
            "action": "deadline_reminder",
            "user_id": user_id,
            "target_task_id": str(task.payload.target_task_id)
            if task.payload.target_task_id
            else None,
        }

    async def _morning_briefing(self, user_id: str, task: AgentTask) -> dict[str, Any]:
        """
        Generate morning briefing.

        TODO: Implement morning briefing logic.
        This would:
        1. Get today's top 3 tasks
        2. Check calendar events (if integrated)
        3. Weather/news (optional)
        4. Generate briefing message
        """
        logger.info(f"MORNING_BRIEFING action for user {user_id}")
        return {"action": "morning_briefing", "user_id": user_id}
