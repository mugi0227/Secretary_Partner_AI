"""Test breakdown with new format."""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.core.config import get_settings
from app.infrastructure.local.task_repository import SqliteTaskRepository
from app.infrastructure.local.memory_repository import SqliteMemoryRepository
from app.infrastructure.local.gemini_api_provider import GeminiAPIProvider
from app.infrastructure.local.database import get_session_factory, init_db
from app.models.enums import CreatedBy, Priority
from app.models.task import TaskCreate
from app.services.planner_service import PlannerService


async def main():
    settings = get_settings()
    if not settings.GOOGLE_API_KEY:
        print("GOOGLE_API_KEY not configured")
        return

    await init_db()
    session_factory = get_session_factory()
    
    task_repo = SqliteTaskRepository(session_factory=session_factory)
    memory_repo = SqliteMemoryRepository(session_factory=session_factory)
    llm_provider = GeminiAPIProvider(settings.GEMINI_MODEL)

    # Create a task
    task = await task_repo.create(
        "test_user",
        TaskCreate(
            title="プレゼン資料を作成する",
            description="来週の会議用のプレゼン資料を作る",
            importance=Priority.HIGH,
            created_by=CreatedBy.USER,
        ),
    )

    # Run breakdown
    service = PlannerService(
        llm_provider=llm_provider,
        task_repo=task_repo,
        memory_repo=memory_repo,
    )

    response = await service.breakdown_task(
        user_id="test_user",
        task_id=task.id,
        create_subtasks=False,
    )

    print("=" * 60)
    print(f"📋 {response.breakdown.original_task_title}")
    print(f"合計時間: {response.breakdown.total_estimated_minutes}分")
    print(f"ステップ数: {len(response.breakdown.steps)}個")
    print("=" * 60)
    print()

    for step in response.breakdown.steps:
        energy = "🔥" if step.energy_level.value == "HIGH" else "✨"
        print(f"## ステップ{step.step_number}: {step.title}")
        print(f"⏱️ {step.estimated_minutes}分 {energy} ({step.energy_level.value})")
        if step.description:
            print(f"💡 {step.description}")
        print()
        if step.guide:
            print("### 進め方ガイド:")
            print(step.guide)
        else:
            print("⚠️ ガイドなし")
        print()
        print("-" * 60)
        print()


if __name__ == "__main__":
    asyncio.run(main())

