"""
Shared achievements API - public endpoints (no auth required).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import AchievementRepo
from app.models.achievement import Achievement, SkillAnalysis

router = APIRouter()


class SharedAchievementResponse(BaseModel):
    """Public achievement response (excludes user_id, task_snapshots, project_ids)."""

    id: str
    period_start: datetime
    period_end: datetime
    period_label: Optional[str]
    summary: str
    weekly_activities: list[str]
    growth_points: list[str]
    skill_analysis: SkillAnalysis
    next_suggestions: list[str]
    task_count: int
    created_at: datetime

    @classmethod
    def from_model(cls, achievement: Achievement) -> "SharedAchievementResponse":
        return cls(
            id=str(achievement.id),
            period_start=achievement.period_start,
            period_end=achievement.period_end,
            period_label=achievement.period_label,
            summary=achievement.summary,
            weekly_activities=achievement.weekly_activities,
            growth_points=achievement.growth_points,
            skill_analysis=achievement.skill_analysis,
            next_suggestions=achievement.next_suggestions,
            task_count=achievement.task_count,
            created_at=achievement.created_at,
        )


@router.get("/{share_token}", response_model=SharedAchievementResponse)
async def get_shared_achievement(
    share_token: str,
    achievement_repo: AchievementRepo,
):
    """
    Get a shared achievement by token.

    This is a public endpoint - no authentication required.
    Returns a limited subset of achievement data.
    """
    achievement = await achievement_repo.get_by_share_token(share_token)
    if not achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared achievement not found",
        )
    return SharedAchievementResponse.from_model(achievement)
