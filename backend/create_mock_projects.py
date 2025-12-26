"""
Create mock projects with proper UTF-8 encoding.
"""
import asyncio
import sys
from datetime import datetime
from uuid import uuid4

sys.path.insert(0, ".")

from app.infrastructure.local.project_repository import SqliteProjectRepository
from app.models.project import ProjectCreate


async def create_mock_projects():
    """Create mock projects."""
    repo = SqliteProjectRepository()
    user_id = "dev_user"

    # Delete existing projects first
    print("Deleting existing projects...")
    from app.infrastructure.local.database import get_session_factory
    from sqlalchemy import text
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(text("DELETE FROM projects WHERE user_id = :user_id"), {"user_id": user_id})
        await session.commit()

    print("Creating mock projects...")

    # Project 1: ブログ執筆
    project1 = ProjectCreate(
        name="ブログ執筆",
        description="テック系ブログの記事を執筆するプロジェクト",
        priority=8,
        goals=[
            "週1本のペースで記事を公開",
            "SEO最適化された記事を作成",
            "読者エンゲージメントを高める"
        ],
        key_points=[
            "競合分析を忘れずに",
            "画像は必ず最適化すること",
            "記事は2000文字以上を目安に"
        ],
        context="""# ブログ執筆プロジェクト

## 概要
テック系ブログの記事を週1本のペースで執筆・公開していくプロジェクト。

## 記事のテーマ
- Web開発のベストプラクティス
- 最新のフレームワーク・ライブラリ紹介
- 実装ノウハウの共有

## ワークフロー
1. テーマ選定
2. 競合記事リサーチ
3. アウトライン作成
4. 執筆
5. 画像作成・最適化
6. 校正
7. 公開
"""
    )
    created1 = await repo.create(user_id, project1)
    print(f"✓ Created: {created1.name} (priority: {created1.priority})")

    # Project 2: 確定申告準備
    project2 = ProjectCreate(
        name="確定申告準備",
        description="2024年度の確定申告に向けた準備プロジェクト",
        priority=10,
        goals=[
            "期限までに申告完了",
            "控除を最大化する",
            "書類を整理保管"
        ],
        key_points=[
            "領収書は月別に分類",
            "医療費控除の対象を確認",
            "freeeで記帳を最新に保つ"
        ],
        context="""# 確定申告準備

## 期限
2025年3月15日（厳守）

## 必要書類
- 源泉徴収票
- 医療費の領収書
- 寄付金受領証明書
- 経費の領収書

## 注意点
- 青色申告なので複式簿記が必要
- e-Taxで提出予定
"""
    )
    created2 = await repo.create(user_id, project2)
    print(f"✓ Created: {created2.name} (priority: {created2.priority})")

    # Project 3: 英語学習
    project3 = ProjectCreate(
        name="英語学習",
        description="英語力向上のための継続学習プロジェクト",
        priority=5,
    )
    created3 = await repo.create(user_id, project3)
    print(f"✓ Created: {created3.name} (priority: {created3.priority})")

    print("\n✅ All mock projects created successfully!")


if __name__ == "__main__":
    asyncio.run(create_mock_projects())
