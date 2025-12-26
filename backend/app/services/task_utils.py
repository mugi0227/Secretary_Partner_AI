"""
Task utility functions.

Helper functions for task calculations and processing.
"""

from typing import Iterable

from app.models.task import Task


def get_effective_estimated_minutes(task: Task, all_tasks: Iterable[Task]) -> int:
    """
    Get the effective estimated minutes for a task.

    If the task has subtasks, returns the sum of subtask estimates.
    Otherwise, returns the task's own estimate.

    Args:
        task: The task to get the estimate for
        all_tasks: All tasks (needed to find subtasks)

    Returns:
        Effective estimated minutes (0 if no estimate available)
    """
    # Find all subtasks of this task
    subtasks = [t for t in all_tasks if t.parent_id == task.id]

    if subtasks:
        # If has subtasks: return sum of subtask estimates
        return sum(st.estimated_minutes or 0 for st in subtasks)
    else:
        # If no subtasks: return task's own estimate
        return task.estimated_minutes or 0


def is_parent_task(task: Task, all_tasks: Iterable[Task]) -> bool:
    """
    Check if a task is a parent task (has subtasks).

    Args:
        task: The task to check
        all_tasks: All tasks (needed to find subtasks)

    Returns:
        True if the task has at least one subtask
    """
    return any(t.parent_id == task.id for t in all_tasks)
