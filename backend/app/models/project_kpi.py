"""
Project KPI models.

These models define KPI templates and per-project KPI configuration.
"""

from typing import Optional, Literal

from pydantic import BaseModel, Field


KpiDirection = Literal["up", "down", "neutral"]
KpiStrategy = Literal["template", "ai", "custom"]


class ProjectKpiMetric(BaseModel):
    """Single KPI definition."""

    key: str = Field(..., min_length=1, max_length=100, description="Stable KPI key")
    label: str = Field(..., min_length=1, max_length=200, description="Display label")
    description: Optional[str] = Field(None, max_length=500, description="KPI description")
    unit: Optional[str] = Field(None, max_length=20, description="Unit label")
    target: Optional[float] = Field(None, description="Target value")
    current: Optional[float] = Field(None, description="Current value")
    direction: KpiDirection = Field("neutral", description="Better direction")
    source: Optional[str] = Field(None, max_length=50, description="Data source hint")


class ProjectKpiConfig(BaseModel):
    """KPI configuration stored on the project."""

    strategy: KpiStrategy = Field("custom", description="How KPIs were selected")
    template_id: Optional[str] = Field(None, max_length=100, description="Template ID")
    metrics: list[ProjectKpiMetric] = Field(default_factory=list, description="KPI list")


class ProjectKpiTemplate(BaseModel):
    """KPI template definition."""

    id: str = Field(..., min_length=1, max_length=100, description="Template ID")
    name: str = Field(..., min_length=1, max_length=200, description="Template name")
    description: str = Field(..., min_length=1, max_length=500, description="Template description")
    category: str = Field(..., min_length=1, max_length=50, description="Template category")
    metrics: list[ProjectKpiMetric] = Field(default_factory=list, description="Template KPI list")
