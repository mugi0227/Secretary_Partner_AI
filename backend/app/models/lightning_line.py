"""
Lightning line response models.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class LightningLinePoint(BaseModel):
    """One point in the lightning line."""

    task_id: UUID
    row_key: str
    planned_progress: float = Field(ge=0, le=100)
    actual_progress: float = Field(ge=0, le=100)
    deviation_days: float


class LightningLineResponse(BaseModel):
    """Lightning line API response."""

    reference_date: date
    points: list[LightningLinePoint]
