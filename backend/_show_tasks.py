"""Temporary script to show tasks in DB."""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import select
from app.infrastructure.local.database import get_session_factory, TaskORM, init_db


async def main():
    await init_db()
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(TaskORM).order_by(TaskORM.created_at))
        tasks = result.scalars().all()
        
        # Group by parent
        parents = [t for t in tasks if t.parent_id is None]
        children = {}
        for t in tasks:
            if t.parent_id:
                if t.parent_id not in children:
                    children[t.parent_id] = []
                children[t.parent_id].append(t)
        
        print(f"=== 全タスク ({len(tasks)}件) ===\n")
        
        for parent in parents:
            print(f"📋 {parent.title}")
            if parent.description:
                print(f"   説明: {parent.description}")
            print(f"   ステータス: {parent.status}")
            
            if parent.id in children:
                print(f"   └─ サブタスク ({len(children[parent.id])}件):")
                for child in sorted(children[parent.id], key=lambda x: x.title):
                    energy = "🔥" if child.energy_level == "HIGH" else "✨"
                    mins = child.estimated_minutes or 10
                    print(f"      • {child.title}")
                    print(f"        ⏱️ {mins}分 {energy} ({child.energy_level})")
            print()


if __name__ == "__main__":
    asyncio.run(main())

