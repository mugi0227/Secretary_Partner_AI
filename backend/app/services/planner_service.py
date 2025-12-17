"""
Planner Service for task breakdown.

Handles task decomposition with Pydantic validation and retry logic.
"""

from __future__ import annotations

import json
import re
from typing import Optional
from uuid import UUID

from google.adk.runners import InMemoryRunner
from google.genai.types import Content, Part
from pydantic import ValidationError

from app.agents.planner_agent import create_planner_agent
from app.core.exceptions import LLMValidationError, NotFoundError
from app.core.logger import logger
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.task_repository import ITaskRepository
from app.models.breakdown import (
    BreakdownResponse,
    BreakdownStep,
    TaskBreakdown,
)
from app.models.enums import CreatedBy, EnergyLevel
from app.models.task import Task, TaskCreate


class PlannerService:
    """Service for breaking down tasks into micro-steps."""

    APP_NAME = "SecretaryPartnerAI_Planner"
    MAX_RETRIES = 2

    def __init__(
        self,
        llm_provider: ILLMProvider,
        task_repo: ITaskRepository,
        memory_repo: IMemoryRepository,
    ):
        """Initialize Planner Service."""
        self._llm_provider = llm_provider
        self._task_repo = task_repo
        self._memory_repo = memory_repo

    async def breakdown_task(
        self,
        user_id: str,
        task_id: UUID,
        create_subtasks: bool = True,
    ) -> BreakdownResponse:
        """
        Break down a task into micro-steps.

        Args:
            user_id: User ID
            task_id: Task ID to break down
            create_subtasks: Whether to create subtasks from breakdown

        Returns:
            BreakdownResponse with steps and optional subtask IDs

        Raises:
            NotFoundError: If task not found
            LLMValidationError: If LLM output validation fails after retries
        """
        # Get the task
        task = await self._task_repo.get(user_id, task_id)
        if not task:
            raise NotFoundError(f"Task {task_id} not found")

        # Create planner agent and runner
        agent = create_planner_agent(
            llm_provider=self._llm_provider,
            task_repo=self._task_repo,
            memory_repo=self._memory_repo,
            user_id=user_id,
        )
        runner = InMemoryRunner(agent=agent, app_name=self.APP_NAME)

        # Build prompt for breakdown
        prompt = self._build_breakdown_prompt(task)

        # Run with retry logic
        breakdown = await self._run_with_retry(runner, user_id, task, prompt)

        # Generate markdown guide
        markdown_guide = self._generate_markdown_guide(breakdown)

        # Create subtasks if requested
        subtask_ids = []
        if create_subtasks:
            subtask_ids = await self._create_subtasks(user_id, task, breakdown)

        return BreakdownResponse(
            breakdown=breakdown,
            subtasks_created=len(subtask_ids) > 0,
            subtask_ids=subtask_ids,
            markdown_guide=markdown_guide,
        )

    def _build_breakdown_prompt(self, task: Task) -> str:
        """Build the prompt for task breakdown."""
        prompt = f"""以下のタスクを**3-5個の大きなステップ**に分解してください。

## 対象タスク
- タイトル: {task.title}
- 説明: {task.description or "なし"}
- 重要度: {task.importance.value}
- 緊急度: {task.urgency.value}

まず、関連する作業手順をsearch_work_memoryで検索してから分解してください。

**重要**: 必ず3-5個のステップに分解してください。10個以上に分解してはいけません。

分解後、以下のJSON形式で結果を返してください:

```json
{{
  "steps": [
    {{
      "step_number": 1,
      "title": "大きなステップのタイトル",
      "description": "このステップで達成すること",
      "estimated_minutes": 30,
      "energy_level": "HIGH",
      "guide": "## 進め方ガイド\\n\\n1. まず〇〇を確認する\\n2. △△を準備する\\n3. □□を実行する\\n\\n**注意点**: ...\\n**完了の目安**: ..."
    }}
  ]
}}
```

- `estimated_minutes`: 15-120分の範囲で設定
- `energy_level`: "HIGH" または "LOW"
- `guide`: **必須**。Markdown形式で詳細な進め方ガイドを記述（3-7個の小さなステップを含む）
"""
        return prompt

    async def _run_with_retry(
        self,
        runner: InMemoryRunner,
        user_id: str,
        task: Task,
        prompt: str,
    ) -> TaskBreakdown:
        """Run agent with retry logic for validation failures."""
        last_error: Optional[Exception] = None
        raw_output = ""

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                # Create session
                session_id = f"breakdown-{task.id}-{attempt}"
                await runner.session_service.create_session(
                    app_name=self.APP_NAME,
                    user_id=user_id,
                    session_id=session_id,
                )

                # Run agent
                message = Content(role="user", parts=[Part(text=prompt)])
                response_parts: list[str] = []

                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=message,
                ):
                    if event.content and getattr(event.content, "parts", None):
                        for part in event.content.parts or []:
                            text = getattr(part, "text", None)
                            if text:
                                response_parts.append(text)

                raw_output = "".join(response_parts)

                # Parse and validate
                breakdown = self._parse_breakdown(raw_output, task)
                return breakdown

            except ValidationError as e:
                last_error = e
                logger.warning(
                    f"Breakdown validation failed (attempt {attempt}/{self.MAX_RETRIES}): {e}"
                )
                # Modify prompt for retry
                prompt = f"""前回の出力にエラーがありました。修正してください。

エラー: {str(e)}

{prompt}"""

            except Exception as e:
                last_error = e
                logger.error(f"Breakdown failed: {e}")
                break

        raise LLMValidationError(
            message=f"Breakdown validation failed after {self.MAX_RETRIES} attempts",
            raw_output=raw_output,
            attempts=self.MAX_RETRIES,
        )

    def _parse_breakdown(self, raw_output: str, task: Task) -> TaskBreakdown:
        """Parse LLM output into TaskBreakdown model."""
        # Extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_output)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find raw JSON
            json_match = re.search(r"\{[\s\S]*\}", raw_output)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValidationError.from_exception_data(
                    "TaskBreakdown",
                    [{"type": "value_error", "msg": "No JSON found in output"}],
                )

        # Parse JSON
        data = json.loads(json_str)

        # Build steps
        steps = []
        for step_data in data.get("steps", []):
            energy = step_data.get("energy_level", "LOW")
            if isinstance(energy, str):
                energy = EnergyLevel(energy.upper())

            steps.append(BreakdownStep(
                step_number=step_data.get("step_number", len(steps) + 1),
                title=step_data["title"],
                description=step_data.get("description"),
                estimated_minutes=step_data.get("estimated_minutes", 30),
                energy_level=energy,
                guide=step_data.get("guide", ""),  # 進め方ガイド
            ))

        # Calculate total time
        total_minutes = sum(s.estimated_minutes for s in steps)

        return TaskBreakdown(
            original_task_id=task.id,
            original_task_title=task.title,
            steps=steps,
            total_estimated_minutes=total_minutes,
            work_memory_used=data.get("work_memory_used", []),
        )

    def _generate_markdown_guide(self, breakdown: TaskBreakdown) -> str:
        """Generate a markdown execution guide from breakdown."""
        lines = [
            f"# {breakdown.original_task_title}",
            "",
            f"**合計見積もり時間**: {breakdown.total_estimated_minutes}分",
            f"**ステップ数**: {len(breakdown.steps)}個",
            "",
            "---",
            "",
        ]

        for step in breakdown.steps:
            energy_emoji = "🔥" if step.energy_level == EnergyLevel.HIGH else "✨"
            lines.append(f"## ステップ{step.step_number}: {step.title}")
            lines.append(f"- ⏱️ {step.estimated_minutes}分 {energy_emoji} ({step.energy_level.value})")
            if step.description:
                lines.append(f"- 💡 {step.description}")
            lines.append("")
            
            # Add detailed guide if provided
            if step.guide:
                lines.append(step.guide)
                lines.append("")
            else:
                lines.append("> ⚠️ 進め方ガイドが提供されていません")
                lines.append("")

        return "\n".join(lines)

    async def _create_subtasks(
        self,
        user_id: str,
        parent_task: Task,
        breakdown: TaskBreakdown,
    ) -> list[UUID]:
        """Create subtasks from breakdown steps."""
        subtask_ids = []

        for step in breakdown.steps:
            # Build description with guide
            # Format: description + separator + guide (Markdown)
            description_parts = []
            if step.description:
                description_parts.append(step.description)
            if step.guide:
                if description_parts:
                    description_parts.append("\n\n---\n\n## 進め方ガイド\n")
                else:
                    description_parts.append("## 進め方ガイド\n")
                description_parts.append(step.guide)

            subtask = TaskCreate(
                title=f"[{step.step_number}] {step.title}",
                description="".join(description_parts) if description_parts else None,
                project_id=parent_task.project_id,
                importance=parent_task.importance,
                urgency=parent_task.urgency,
                energy_level=step.energy_level,
                estimated_minutes=step.estimated_minutes,
                parent_id=parent_task.id,
                created_by=CreatedBy.AGENT,
            )
            created = await self._task_repo.create(user_id, subtask)
            subtask_ids.append(created.id)

        return subtask_ids

