"""
Seed demo data for the 3-minute demo video.

Usage:
    cd backend
    python -m scripts.seed_demo_data          # Dry-run (shows what will be created)
    python -m scripts.seed_demo_data --apply   # Actually insert data

Requires: ENVIRONMENT=local, AUTH_PROVIDER=local in .env
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.achievement import (
    Achievement,
    MemberContribution,
    ProjectAchievement,
    SkillAnalysis,
    SkillExperience,
    TaskSnapshot,
)
from app.models.collaboration import (
    CheckinCreateV2,
    CheckinItem,
    ProjectMemberCreate,
    TaskAssignmentCreate,
)
from app.models.enums import (
    CheckinItemCategory,
    CheckinItemUrgency,
    CheckinMood,
    CreatedBy,
    EnergyLevel,
    GenerationType,
    MemoryScope,
    MemoryType,
    Priority,
    ProjectRole,
    ProjectVisibility,
    TaskStatus,
)
from app.models.heartbeat import (
    HeartbeatEventCreate,
    HeartbeatIntensity,
    HeartbeatSettingsUpdate,
    HeartbeatSeverity,
)
from app.models.meeting_agenda import MeetingAgendaItemCreate
from app.models.memory import MemoryCreate
from app.models.notification import NotificationCreate, NotificationType
from app.models.phase import PhaseCreate
from app.models.project import ProjectCreate
from app.models.recurring_meeting import RecurrenceFrequency, RecurringMeetingCreate
from app.models.task import TaskCreate, TaskUpdate
from app.models.user import UserCreate

# Suppress noisy SQLAlchemy logs during seed
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PASSWORD = "testtest"
JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
TODAY = NOW.date()


def _next_weekday(weekday: int, t: time, *, weeks_ahead: int = 0) -> datetime:
    """Return the next occurrence of the given weekday (0=Mon) with the given time in JST.

    If weeks_ahead > 0, skip that many additional weeks.
    """
    days_ahead = (weekday - TODAY.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # always pick the *next* occurrence
    target_date = TODAY + timedelta(days=days_ahead + 7 * weeks_ahead)
    return datetime.combine(target_date, t, tzinfo=JST)

# Pre-generate stable UUIDs so we can cross-reference
USER_IDS = {
    "mugi": uuid4(),
    "yuki": uuid4(),
    "takeshi": uuid4(),
}
PROJECT_IDS = {
    "a_company": uuid4(),
    "study_group": uuid4(),
}


# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------
def _users() -> list[dict]:
    return [
        {
            "key": "mugi",
            "create": UserCreate(
                provider_issuer="local",
                provider_sub="mugi",
                email="mugi@example.com",
                display_name="Mugi",
                first_name="麦",
                last_name="斎藤",
                username="mugi",
                password_hash=hash_password(PASSWORD),
                timezone="Asia/Tokyo",
            ),
        },
        {
            "key": "yuki",
            "create": UserCreate(
                provider_issuer="local",
                provider_sub="yuki",
                email="yuki@example.com",
                display_name="Yuki",
                first_name="雪",
                last_name="佐藤",
                username="yuki",
                password_hash=hash_password(PASSWORD),
                timezone="Asia/Tokyo",
            ),
        },
        {
            "key": "takeshi",
            "create": UserCreate(
                provider_issuer="local",
                provider_sub="takeshi",
                email="takeshi@example.com",
                display_name="Takeshi",
                first_name="健",
                last_name="鈴木",
                username="takeshi",
                password_hash=hash_password(PASSWORD),
                timezone="Asia/Tokyo",
            ),
        },
    ]


def _projects() -> list[dict]:
    return [
        {
            "key": "a_company",
            "owner": "mugi",
            "create": ProjectCreate(
                name="A社 Webリニューアル",
                description="A社コーポレートサイトのフルリニューアルプロジェクト。Next.js + FastAPI構成。",
                visibility=ProjectVisibility.TEAM,
                priority=8,
                goals=[
                    "3月末までにステージング公開",
                    "Core Web Vitals全項目グリーン",
                    "CMS統合によるクライアント自走体制の構築",
                ],
                key_points=[
                    "クライアント担当: 田中さん（レスポンス遅めなので余裕を持つ）",
                    "デザインはFigma管理、週次でレビュー",
                ],
            ),
        },
        {
            "key": "study_group",
            "owner": "mugi",
            "create": ProjectCreate(
                name="社内勉強会 LT準備",
                description="月末の社内LT大会に向けた準備。テーマ「生成AIを使った開発効率化」。",
                visibility=ProjectVisibility.PRIVATE,
                priority=5,
                goals=[
                    "15分のLT資料を完成させる",
                    "デモ動画を用意する",
                ],
                key_points=[
                    "発表日: 月末金曜日",
                    "聴衆: エンジニア20名程度",
                ],
            ),
        },
    ]


def _phases() -> list[dict]:
    return [
        {
            "owner": "mugi",
            "create": PhaseCreate(
                name="設計フェーズ",
                project_id=PROJECT_IDS["a_company"],
                order_in_project=1,
                description="要件定義・ワイヤーフレーム・技術選定",
                start_date=datetime(2026, 1, 20, tzinfo=JST),
                end_date=datetime(2026, 2, 14, tzinfo=JST),
            ),
        },
        {
            "owner": "mugi",
            "create": PhaseCreate(
                name="実装フェーズ",
                project_id=PROJECT_IDS["a_company"],
                order_in_project=2,
                description="フロントエンド・バックエンド実装",
                start_date=datetime(2026, 2, 17, tzinfo=JST),
                end_date=datetime(2026, 3, 20, tzinfo=JST),
            ),
        },
    ]


def _existing_tasks() -> list[dict]:
    """Pre-existing tasks that give the projects a lived-in feel."""
    return [
        # --- A社 Webリニューアル (completed / in-progress) ---
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="デザインカンプのレビュー",
                description="Figmaのデザインカンプを確認し、フィードバックをまとめる",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.HIGH,
                urgency=Priority.HIGH,
                energy_level=EnergyLevel.MEDIUM,
                estimated_minutes=60,
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.DONE,
            "completed_at": NOW - timedelta(days=3),
        },
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="API設計書の作成",
                description="REST APIのエンドポイント設計とOpenAPI仕様書の作成",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.HIGH,
                urgency=Priority.MEDIUM,
                energy_level=EnergyLevel.HIGH,
                estimated_minutes=180,
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.IN_PROGRESS,
            "progress": 70,
        },
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="ステージング環境構築",
                description="Vercel + Cloud Runでステージング環境をセットアップ",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.MEDIUM,
                urgency=Priority.LOW,
                energy_level=EnergyLevel.HIGH,
                estimated_minutes=120,
                due_date=datetime(2026, 2, 28, tzinfo=JST),
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.TODO,
        },
        {
            "owner": "yuki",
            "create": TaskCreate(
                title="トップページのコンポーネント設計",
                description="Next.jsのコンポーネント構成とディレクトリ設計",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.HIGH,
                urgency=Priority.MEDIUM,
                energy_level=EnergyLevel.HIGH,
                estimated_minutes=90,
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.IN_PROGRESS,
            "progress": 40,
        },
        {
            "owner": "takeshi",
            "create": TaskCreate(
                title="既存サイトのアクセスログ分析",
                description="GA4データを元に現行サイトの利用状況を分析",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.MEDIUM,
                urgency=Priority.MEDIUM,
                energy_level=EnergyLevel.MEDIUM,
                estimated_minutes=60,
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.DONE,
            "completed_at": NOW - timedelta(days=5),
        },
        # --- 社内勉強会 ---
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="LTテーマ決め",
                description="生成AIの開発効率化をテーマに決定",
                project_id=PROJECT_IDS["study_group"],
                importance=Priority.MEDIUM,
                urgency=Priority.HIGH,
                energy_level=EnergyLevel.LOW,
                estimated_minutes=30,
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.DONE,
            "completed_at": NOW - timedelta(days=7),
        },
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="アウトライン作成",
                description="15分LTのアウトラインを書き出す",
                project_id=PROJECT_IDS["study_group"],
                importance=Priority.MEDIUM,
                urgency=Priority.MEDIUM,
                energy_level=EnergyLevel.MEDIUM,
                estimated_minutes=45,
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.TODO,
        },
        # --- 会議（スケジューリングデモ用） ---
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="A社PJ 週次定例",
                description="週次の進捗共有と課題確認",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.HIGH,
                urgency=Priority.HIGH,
                energy_level=EnergyLevel.LOW,
                estimated_minutes=30,
                created_by=CreatedBy.USER,
                is_fixed_time=True,
                start_time=_next_weekday(2, time(10, 0)),  # 水曜 10:00
                end_time=_next_weekday(2, time(10, 30)),
                location="Google Meet",
                attendees=["mugi", "yuki", "takeshi"],
            ),
            "status": TaskStatus.TODO,
        },
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="A社 田中さんと認証方式の打ち合わせ",
                description="OAuth2 vs SAMLの最終方針決定。技術的な制約とセキュリティ要件を確認。",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.HIGH,
                urgency=Priority.HIGH,
                energy_level=EnergyLevel.MEDIUM,
                estimated_minutes=60,
                created_by=CreatedBy.AGENT,
                is_fixed_time=True,
                start_time=_next_weekday(3, time(14, 0)),  # 木曜 14:00
                end_time=_next_weekday(3, time(15, 0)),
                location="Zoom（A社側指定）",
                attendees=["mugi", "田中さん（A社）"],
            ),
            "status": TaskStatus.TODO,
        },
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="社内LT大会",
                description="月末の社内LT大会。Mugiは「生成AIを使った開発効率化」で発表。",
                project_id=PROJECT_IDS["study_group"],
                importance=Priority.MEDIUM,
                urgency=Priority.MEDIUM,
                energy_level=EnergyLevel.HIGH,
                estimated_minutes=120,
                created_by=CreatedBy.USER,
                is_fixed_time=True,
                start_time=_next_weekday(4, time(16, 0), weeks_ahead=2),  # 再来週金曜 16:00
                end_time=_next_weekday(4, time(18, 0), weeks_ahead=2),
                location="本社 大会議室",
                attendees=["mugi", "全エンジニア"],
            ),
            "status": TaskStatus.TODO,
        },
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="1on1（上司・山田さん）",
                description="隔週の1on1。今週の振り返りと来週の目標設定。",
                importance=Priority.MEDIUM,
                urgency=Priority.MEDIUM,
                energy_level=EnergyLevel.LOW,
                estimated_minutes=30,
                created_by=CreatedBy.USER,
                is_fixed_time=True,
                start_time=_next_weekday(4, time(17, 0)),  # 金曜 17:00
                end_time=_next_weekday(4, time(17, 30)),
                location="オフィス 個室B",
                attendees=["mugi", "山田さん"],
            ),
            "status": TaskStatus.TODO,
        },
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="デザインレビュー会",
                description="Figmaカンプの最終確認。Yukiのフロント実装方針も合わせて確認。",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.HIGH,
                urgency=Priority.MEDIUM,
                energy_level=EnergyLevel.MEDIUM,
                estimated_minutes=45,
                created_by=CreatedBy.AGENT,
                is_fixed_time=True,
                start_time=_next_weekday(0, time(11, 0)),  # 月曜 11:00
                end_time=_next_weekday(0, time(11, 45)),
                location="Google Meet",
                attendees=["mugi", "yuki"],
            ),
            "status": TaskStatus.TODO,
        },
        # --- ヤバいタスク（heartbeatデモ用） ---
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="A社向け認証フロー実装",
                description="OAuth2認証フローのフロントエンド + バックエンド実装。ログイン・ログアウト・トークンリフレッシュ。",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.HIGH,
                urgency=Priority.HIGH,
                energy_level=EnergyLevel.HIGH,
                estimated_minutes=240,
                due_date=NOW + timedelta(days=1),  # 明日期限
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.TODO,  # 未着手のまま
        },
        {
            "owner": "mugi",
            "create": TaskCreate(
                title="CMS統合のAPI結合テスト",
                description="microCMSとのAPI連携部分の結合テスト。記事取得・画像配信・キャッシュ確認。",
                project_id=PROJECT_IDS["a_company"],
                importance=Priority.HIGH,
                urgency=Priority.HIGH,
                energy_level=EnergyLevel.HIGH,
                estimated_minutes=180,
                due_date=NOW - timedelta(days=1),  # 昨日期限（過ぎてる）
                created_by=CreatedBy.USER,
            ),
            "status": TaskStatus.IN_PROGRESS,
            "progress": 30,  # 30%で止まってる
        },
    ]


def _project_members() -> list[dict]:
    """A社PJにチームメンバーを登録。"""
    return [
        {
            "owner": "mugi",
            "project_key": "a_company",
            "create": ProjectMemberCreate(
                member_user_id="__mugi__",
                role=ProjectRole.OWNER,
                capacity_hours=40,
            ),
        },
        {
            "owner": "mugi",
            "project_key": "a_company",
            "create": ProjectMemberCreate(
                member_user_id="__yuki__",
                role=ProjectRole.MEMBER,
                capacity_hours=32,
            ),
        },
        {
            "owner": "mugi",
            "project_key": "a_company",
            "create": ProjectMemberCreate(
                member_user_id="__takeshi__",
                role=ProjectRole.MEMBER,
                capacity_hours=20,
            ),
        },
    ]


def _checkins() -> list[dict]:
    """転パート: チェックインデータ。"""
    return [
        {
            "owner": "mugi",
            "project_key": "a_company",
            "create": CheckinCreateV2(
                member_user_id="__mugi__",
                checkin_date=TODAY,
                items=[
                    CheckinItem(
                        category=CheckinItemCategory.UPDATE,
                        content="API設計書ほぼ完了。あと認証周りのエンドポイントだけ",
                        urgency=CheckinItemUrgency.LOW,
                    ),
                    CheckinItem(
                        category=CheckinItemCategory.BLOCKER,
                        content="認証方式がOAuth2かSAMLか未確定。A社田中さんに確認中",
                        urgency=CheckinItemUrgency.HIGH,
                    ),
                ],
                mood=CheckinMood.OKAY,
                must_discuss_in_next_meeting="認証方式の最終決定",
            ),
        },
        {
            "owner": "mugi",
            "project_key": "a_company",
            "create": CheckinCreateV2(
                member_user_id="__yuki__",
                checkin_date=TODAY,
                items=[
                    CheckinItem(
                        category=CheckinItemCategory.UPDATE,
                        content="トップページのコンポーネント設計中。レスポンシブ対応も並行で進めてる",
                        urgency=CheckinItemUrgency.LOW,
                    ),
                    CheckinItem(
                        category=CheckinItemCategory.DISCUSSION,
                        content="ヒーローセクションのアニメーション、Framer MotionかCSS Animationか相談したい",
                        urgency=CheckinItemUrgency.MEDIUM,
                    ),
                ],
                mood=CheckinMood.GOOD,
                free_comment="デザインいい感じで楽しい！",
            ),
        },
        {
            "owner": "mugi",
            "project_key": "a_company",
            "create": CheckinCreateV2(
                member_user_id="__takeshi__",
                checkin_date=TODAY,
                items=[
                    CheckinItem(
                        category=CheckinItemCategory.UPDATE,
                        content="アクセスログ分析レポート完了。重要ページのCVR改善ポイントを3つ特定",
                        urgency=CheckinItemUrgency.LOW,
                    ),
                    CheckinItem(
                        category=CheckinItemCategory.REQUEST,
                        content="分析結果をもとにワイヤーフレーム修正が必要。Mugiさんと30分もらえると助かる",
                        urgency=CheckinItemUrgency.MEDIUM,
                    ),
                ],
                mood=CheckinMood.GOOD,
            ),
        },
    ]


def _recurring_meeting() -> dict:
    """A社PJ 週次定例。"""
    # anchor_date should match the weekday (Wednesday=2)
    next_wednesday = TODAY
    while next_wednesday.weekday() != 2:
        next_wednesday += timedelta(days=1)
    return {
        "owner": "mugi",
        "create": RecurringMeetingCreate(
            title="A社PJ 週次定例",
            project_id=PROJECT_IDS["a_company"],
            frequency=RecurrenceFrequency.WEEKLY,
            weekday=2,  # Wednesday
            start_time=time(10, 0),
            duration_minutes=30,
            location="Google Meet",
            attendees=["mugi", "yuki", "takeshi"],
            agenda_window_days=7,
            anchor_date=next_wednesday,
        ),
    }


def _meeting_agenda_items() -> list[dict]:
    """チェックインから自動生成されたアジェンダ（風のデモデータ）。"""
    return [
        {
            "owner": "mugi",
            "create": MeetingAgendaItemCreate(
                title="[BLOCKER] 認証方式の最終決定（OAuth2 vs SAML）",
                description="A社田中さんからの回答待ち。方式確定しないとAPI設計が完了できない。",
                duration_minutes=10,
                order_index=0,
                event_date=TODAY,
            ),
        },
        {
            "owner": "mugi",
            "create": MeetingAgendaItemCreate(
                title="[DISCUSSION] ヒーローセクションのアニメーション技術選定",
                description="Framer Motion vs CSS Animation。パフォーマンスと開発効率のトレードオフ。",
                duration_minutes=5,
                order_index=1,
                event_date=TODAY,
            ),
        },
        {
            "owner": "mugi",
            "create": MeetingAgendaItemCreate(
                title="[REQUEST] アクセスログ分析 → ワイヤーフレーム修正の相談",
                description="TakeshiのCVR分析結果をもとに、ワイヤーフレームの優先修正箇所を決める。",
                duration_minutes=10,
                order_index=2,
                event_date=TODAY,
            ),
        },
        {
            "owner": "mugi",
            "create": MeetingAgendaItemCreate(
                title="各メンバー進捗共有",
                description="API設計、フロント実装、分析の進捗確認。",
                duration_minutes=5,
                order_index=3,
                event_date=TODAY,
            ),
        },
    ]


def _achievement() -> dict:
    """転パート: Mugiの週次達成項目。"""
    period_start = datetime(2026, 2, 3, 0, 0, tzinfo=JST)
    period_end = datetime(2026, 2, 9, 23, 59, 59, tzinfo=JST)
    return {
        "achievement": Achievement(
            id=uuid4(),
            user_id="__mugi__",
            period_start=period_start,
            period_end=period_end,
            period_label="2026年2月 第1週",
            summary="A社Webリニューアルの設計フェーズを大きく前進させた一週間。API設計書の7割を完成させ、デザインレビューも完了。並行してLT準備のテーマ選定も済ませた。",
            growth_points=[
                "REST API設計スキルが向上 - OpenAPI仕様書を初めて0から書き上げた",
                "クライアント折衝力 - 田中さんとの仕様調整を自走で進められた",
                "マルチタスク管理 - 2プロジェクトを並行して進行できた",
            ],
            skill_analysis=SkillAnalysis(
                domain_skills=[
                    SkillExperience(category="バックエンド", experience_count=4, percentage=50.0),
                    SkillExperience(category="フロントエンド", experience_count=2, percentage=25.0),
                    SkillExperience(category="インフラ", experience_count=1, percentage=12.5),
                    SkillExperience(category="UX/UI", experience_count=1, percentage=12.5),
                ],
                soft_skills=[
                    SkillExperience(category="プロジェクト管理", experience_count=3, percentage=37.5),
                    SkillExperience(category="コミュニケーション", experience_count=3, percentage=37.5),
                    SkillExperience(category="問題解決", experience_count=2, percentage=25.0),
                ],
                work_types=[
                    SkillExperience(category="新規立ち上げ", experience_count=3, percentage=37.5),
                    SkillExperience(category="ドキュメント作成", experience_count=3, percentage=37.5),
                    SkillExperience(category="レビュー・チェック", experience_count=2, percentage=25.0),
                ],
                strengths=["設計ドキュメントの品質が高い", "マルチプロジェクトの切り替えがスムーズ"],
                growth_areas=["見積もり精度の向上", "早めのブロッカー報告"],
            ),
            next_suggestions=[
                "認証方式の確定を最優先で進める",
                "ステージング環境構築に着手し、CI/CDパイプラインを整備",
                "LTのアウトライン作成を今週前半に終わらせる",
            ],
            weekly_activities=[
                "デザインカンプのレビューを完了し、5件のフィードバックを提出",
                "API設計書を70%まで作成（認証エンドポイント以外を完了）",
                "A社田中さんと認証方式について2回のMTGを実施",
                "LTテーマを「生成AIを使った開発効率化」に決定",
                "社内勉強会の発表枠を確保",
                "アクセスログ分析のレビューに参加",
                "チームの週次定例を2回ファシリテート",
                "ステージング環境の技術調査（Vercel vs Cloudflare Pages）",
            ],
            task_count=8,
            project_ids=[PROJECT_IDS["a_company"], PROJECT_IDS["study_group"]],
            task_snapshots=[
                TaskSnapshot(
                    id=uuid4(),
                    title="デザインカンプのレビュー",
                    project_id=PROJECT_IDS["a_company"],
                    completed_at=NOW - timedelta(days=3),
                    completion_note="Figma上で5件のコメントを残した",
                ),
                TaskSnapshot(
                    id=uuid4(),
                    title="LTテーマ決め",
                    project_id=PROJECT_IDS["study_group"],
                    completed_at=NOW - timedelta(days=7),
                ),
            ],
            generation_type=GenerationType.AUTO,
            created_at=NOW - timedelta(days=1),
            updated_at=NOW - timedelta(days=1),
        ),
    }


def _project_achievement() -> dict:
    """転パート: A社PJチーム達成項目。"""
    period_start = datetime(2026, 2, 3, 0, 0, tzinfo=JST)
    period_end = datetime(2026, 2, 9, 23, 59, 59, tzinfo=JST)
    return {
        "achievement": ProjectAchievement(
            id=uuid4(),
            project_id=PROJECT_IDS["a_company"],
            period_start=period_start,
            period_end=period_end,
            period_label="2026年2月 第1週",
            summary="設計フェーズの中盤。API設計とフロント設計が並行して進行中。アクセスログ分析も完了し、データドリブンなUI改善の基盤が整った。",
            team_highlights=[
                "API設計書が70%完成 - 認証以外のエンドポイントを網羅",
                "アクセスログ分析完了 - CVR改善ポイントを3つ特定",
                "フロントのコンポーネント設計が順調に進行中",
            ],
            challenges=[
                "認証方式（OAuth2/SAML）が未確定 - クライアント判断待ち",
                "ヒーローセクションのアニメーション技術選定が必要",
            ],
            learnings=[
                "GA4データの早期分析が設計の質を大幅に向上させた",
                "チェックインでブロッカーを早期発見できる体制が機能し始めた",
            ],
            member_contributions=[
                MemberContribution(
                    user_id="__mugi__",
                    display_name="Mugi",
                    task_count=3,
                    main_areas=["API設計", "クライアント折衝", "プロジェクト管理"],
                    task_titles=["デザインカンプのレビュー", "API設計書の作成"],
                ),
                MemberContribution(
                    user_id="__yuki__",
                    display_name="Yuki",
                    task_count=1,
                    main_areas=["フロントエンド設計", "UI実装"],
                    task_titles=["トップページのコンポーネント設計"],
                ),
                MemberContribution(
                    user_id="__takeshi__",
                    display_name="Takeshi",
                    task_count=1,
                    main_areas=["データ分析", "UXリサーチ"],
                    task_titles=["既存サイトのアクセスログ分析"],
                ),
            ],
            total_task_count=5,
            remaining_tasks_count=3,
            open_issues=["認証方式の確定が他タスクのブロッカーになっている"],
            generation_type=GenerationType.AUTO,
            created_at=NOW - timedelta(days=1),
            updated_at=NOW - timedelta(days=1),
        ),
    }


def _memories() -> list[dict]:
    """AIの記憶データ。"""
    return [
        {
            "owner": "mugi",
            "create": MemoryCreate(
                content="朝型で、午前中（9:00-12:00）に集中力の必要なタスクを入れたい。午後は眠くなりがちなのでミーティングや軽めの作業を好む。",
                scope=MemoryScope.USER,
                memory_type=MemoryType.PREFERENCE,
                tags=["schedule", "energy", "morning"],
                source="agent",
            ),
        },
        {
            "owner": "mugi",
            "create": MemoryCreate(
                content="タスクの切り替えが多いと消耗する傾向がある。1つのタスクに集中する時間ブロック（25-50分）を作るとパフォーマンスが上がる。",
                scope=MemoryScope.USER,
                memory_type=MemoryType.PATTERN,
                tags=["focus", "pomodoro"],
                source="agent",
            ),
        },
        {
            "owner": "mugi",
            "create": MemoryCreate(
                content="A社の担当者は田中さん。メールのレスポンスが2-3営業日かかることが多い。仕様確認は早めに投げておくこと。",
                scope=MemoryScope.PROJECT,
                memory_type=MemoryType.FACT,
                project_id=PROJECT_IDS["a_company"],
                tags=["client", "communication", "a_company"],
                source="agent",
            ),
        },
        {
            "owner": "mugi",
            "create": MemoryCreate(
                content="A社のコーポレートカラーは #1A365D（ネイビー）と #E53E3E（アクセントレッド）。ブランドガイドラインは Figma の「A社_BrandGuide」に格納。",
                scope=MemoryScope.PROJECT,
                memory_type=MemoryType.FACT,
                project_id=PROJECT_IDS["a_company"],
                tags=["design", "brand", "a_company"],
                source="user",
            ),
        },
    ]


def _heartbeat_settings() -> dict:
    """Mugiのheartbeat設定。"""
    return {
        "owner": "mugi",
        "update": HeartbeatSettingsUpdate(
            enabled=True,
            notification_limit_per_day=2,
            notification_window_start="09:00",
            notification_window_end="21:00",
            heartbeat_intensity=HeartbeatIntensity.STANDARD,
            daily_capacity_per_task_minutes=60,
            cooldown_hours_per_task=24,
        ),
    }


def _heartbeat_events() -> list[dict]:
    """Heartbeatイベント: タスクリスク検知の履歴。

    task_title をキーにして、seed実行時に実際のtask_idへ解決する。
    """
    return [
        {
            "task_title": "A社向け認証フロー実装",
            "event": HeartbeatEventCreate(
                user_id="__mugi__",
                severity=HeartbeatSeverity.CRITICAL,
                risk_score=0.95,
                metadata={
                    "reason": "deadline_tomorrow_untouched",
                    "days_left": 1,
                    "message": "明日が期限ですが未着手です。見積もり240分（4時間）。今日中に着手しないと間に合いません。",
                },
            ),
        },
        {
            "task_title": "CMS統合のAPI結合テスト",
            "event": HeartbeatEventCreate(
                user_id="__mugi__",
                severity=HeartbeatSeverity.HIGH,
                risk_score=0.88,
                metadata={
                    "reason": "overdue_low_progress",
                    "days_overdue": 1,
                    "message": "期限を1日過ぎていますが、進捗30%です。見積もり180分のうち残り約120分。",
                },
            ),
        },
        {
            "task_title": "API設計書の作成",
            "event": HeartbeatEventCreate(
                user_id="__mugi__",
                severity=HeartbeatSeverity.MEDIUM,
                risk_score=0.45,
                is_read=True,  # チャット通知済み・既読扱い（バッジは2件にする）
                metadata={
                    "reason": "blocked_by_external",
                    "message": "認証方式が未確定のため、残り30%の作業が進められません。田中さんへの確認が3営業日経過しています。",
                },
            ),
        },
    ]


def _heartbeat_chat_messages() -> list[dict]:
    """Heartbeatチャット: 高リスクタスクを検知してAIがチャットで声をかけるデモデータ。

    session_id は "heartbeat-" プレフィックスで始まる。
    """
    _tomorrow = NOW + timedelta(days=1)
    _yesterday = NOW - timedelta(days=1)
    tomorrow = f"{_tomorrow.month}/{_tomorrow.day}"
    yesterday = f"{_yesterday.month}/{_yesterday.day}"
    return [
        {
            "task_title": "A社向け認証フロー実装",
            "session_id": f"heartbeat-{NOW.strftime('%Y%m%d')}-auth-001",
            "title": f"Heartbeat {tomorrow} - A社向け認証フロー実装",
            "content": (
                "「A社向け認証フロー実装」について声をかけています。\n\n"
                f"明日({tomorrow})が期限ですが、まだ未着手のようです。\n"
                "見積もりが4時間あるので、今日中にまとまった時間を確保しないと厳しそうです。\n\n"
                "気になった理由:\n"
                "- 期限まであと1日で未着手\n"
                "- 見積もり240分（4時間）\n"
                "- OAuth2のフロントエンド+バックエンド実装は工程が多い\n\n"
                "もし今日着手が難しければ、期限の延長か、スコープを絞って最小限のログイン機能だけ先に実装する手もあります。\n"
                "どうしますか？\n\n"
                "[タスクを開く](task://__resolve__)"
            ),
        },
        {
            "task_title": "CMS統合のAPI結合テスト",
            "session_id": f"heartbeat-{NOW.strftime('%Y%m%d')}-cms-002",
            "title": f"Heartbeat {yesterday} - CMS統合のAPI結合テスト",
            "content": (
                "「CMS統合のAPI結合テスト」について声をかけています。\n\n"
                f"期限({yesterday})を過ぎていますが、進捗が30%で止まっているようです。\n\n"
                "気になった理由:\n"
                "- 期限を1日超過\n"
                "- 進捗30%（残り約120分の作業）\n"
                "- 結合テストの結果は次のフェーズに影響するので早めに片付けたいところです\n\n"
                "何かブロッカーがありますか？\n"
                "もし詰まっているポイントがあれば教えてください。一緒に整理します。\n\n"
                "[タスクを開く](task://__resolve__)"
            ),
        },
    ]


def _heartbeat_notifications() -> list[dict]:
    """Heartbeat通知: UIに表示される通知。"""
    return [
        {
            "task_title": "A社向け認証フロー実装",
            "notification": NotificationCreate(
                user_id="__mugi__",
                type=NotificationType.HEARTBEAT,
                title="明日期限のタスクが未着手です",
                message="「A社向け認証フロー実装」が明日期限ですが未着手です。見積もり4時間。今日中の着手を検討してください。",
                link_type="task",
                link_id="__resolve__",
                project_id=PROJECT_IDS["a_company"],
                project_name="A社 Webリニューアル",
            ),
        },
        {
            "task_title": "CMS統合のAPI結合テスト",
            "notification": NotificationCreate(
                user_id="__mugi__",
                type=NotificationType.HEARTBEAT,
                title="期限超過タスクがあります",
                message="「CMS統合のAPI結合テスト」が期限を1日超過しています。進捗30%で止まっています。",
                link_type="task",
                link_id="__resolve__",
                project_id=PROJECT_IDS["a_company"],
                project_name="A社 Webリニューアル",
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Seed runner
# ---------------------------------------------------------------------------
async def seed(*, dry_run: bool = True) -> None:
    from app.infrastructure.local.database import init_db

    await init_db()

    if dry_run:
        print("=" * 60)
        print("  DRY RUN - showing what will be created")
        print("=" * 60)
        _print_plan()
        return

    # Import repositories
    from app.infrastructure.local.achievement_repository import (
        SqliteAchievementRepository,
    )
    from app.infrastructure.local.chat_session_repository import (
        SqliteChatSessionRepository,
    )
    from app.infrastructure.local.checkin_repository import SqliteCheckinRepository
    from app.infrastructure.local.heartbeat_event_repository import (
        SqliteHeartbeatEventRepository,
    )
    from app.infrastructure.local.heartbeat_settings_repository import (
        SqliteHeartbeatSettingsRepository,
    )
    from app.infrastructure.local.meeting_agenda_repository import (
        SqliteMeetingAgendaRepository,
    )
    from app.infrastructure.local.memory_repository import SqliteMemoryRepository
    from app.infrastructure.local.notification_repository import (
        SqliteNotificationRepository,
    )
    from app.infrastructure.local.phase_repository import SqlitePhaseRepository
    from app.infrastructure.local.project_achievement_repository import (
        SqliteProjectAchievementRepository,
    )
    from app.infrastructure.local.project_member_repository import (
        SqliteProjectMemberRepository,
    )
    from app.infrastructure.local.project_repository import SqliteProjectRepository
    from app.infrastructure.local.recurring_meeting_repository import (
        SqliteRecurringMeetingRepository,
    )
    from app.infrastructure.local.task_assignment_repository import (
        SqliteTaskAssignmentRepository,
    )
    from app.infrastructure.local.task_repository import SqliteTaskRepository
    from app.infrastructure.local.user_repository import SqliteUserRepository

    user_repo = SqliteUserRepository()
    project_repo = SqliteProjectRepository()
    phase_repo = SqlitePhaseRepository()
    task_repo = SqliteTaskRepository()
    member_repo = SqliteProjectMemberRepository()
    checkin_repo = SqliteCheckinRepository()
    meeting_repo = SqliteRecurringMeetingRepository()
    agenda_repo = SqliteMeetingAgendaRepository()
    achievement_repo = SqliteAchievementRepository()
    project_achievement_repo = SqliteProjectAchievementRepository()
    memory_repo = SqliteMemoryRepository()
    assignment_repo = SqliteTaskAssignmentRepository()
    heartbeat_settings_repo = SqliteHeartbeatSettingsRepository()
    heartbeat_event_repo = SqliteHeartbeatEventRepository()
    notification_repo = SqliteNotificationRepository()
    chat_repo = SqliteChatSessionRepository()

    settings = get_settings()

    # ---- 1. Users ----
    print("\n--- Creating Users ---")
    real_user_ids: dict[str, str] = {}
    for u in _users():
        user = await user_repo.create(u["create"])
        real_user_ids[u["key"]] = str(user.id)
        token = create_access_token(str(user.id), settings)
        print(f"  [OK] {u['key']:10s} id={user.id}  email={user.email}")
        print(f"        token={token[:40]}...")

    # Helper to resolve placeholder user ids
    def resolve_user_id(key: str) -> str:
        return real_user_ids[key]

    def resolve_member_id(raw: str) -> str:
        """Replace __name__ placeholders with real user ids."""
        for key, uid in real_user_ids.items():
            raw = raw.replace(f"__{key}__", uid)
        return raw

    # ---- 2. Projects ----
    print("\n--- Creating Projects ---")
    real_project_ids: dict[str, UUID] = {}
    for p in _projects():
        project = await project_repo.create(
            user_id=resolve_user_id(p["owner"]),
            project=p["create"],
        )
        real_project_ids[p["key"]] = project.id
        # Update the global PROJECT_IDS mapping for cross-references
        PROJECT_IDS[p["key"]] = project.id
        print(f"  [OK] {p['create'].name:30s} id={project.id}")

    # ---- 3. Phases ----
    print("\n--- Creating Phases ---")
    for ph in _phases():
        # Update project_id to real
        ph["create"].project_id = real_project_ids.get("a_company", ph["create"].project_id)
        phase = await phase_repo.create(
            user_id=resolve_user_id(ph["owner"]),
            phase=ph["create"],
        )
        print(f"  [OK] {phase.name:30s} id={phase.id}")

    # ---- 4. Tasks ----
    print("\n--- Creating Tasks ---")
    task_ids_by_title: dict[str, UUID] = {}
    for t in _existing_tasks():
        # Remap project_id
        create = t["create"]
        for key, pid in real_project_ids.items():
            if create.project_id == PROJECT_IDS.get(key) or create.project_id == pid:
                create.project_id = pid
                break

        owner_uid = resolve_user_id(t["owner"])
        task = await task_repo.create(user_id=owner_uid, task=create)

        # Update status/progress if needed
        status = t.get("status")
        if status and status != TaskStatus.TODO:
            task_update = TaskUpdate(
                status=status,
                progress=t.get("progress"),
            )
            await task_repo.update(user_id=owner_uid, task_id=task.id, update=task_update)

        task_ids_by_title[task.title] = task.id
        label = f"{task.title[:35]:35s}"
        print(f"  [OK] {label} [{status or 'TODO':11s}] owner={t['owner']}")

    # ---- 5. Task Assignments (A社PJ tasks) ----
    print("\n--- Creating Task Assignments ---")
    assignment_map = {
        "デザインカンプのレビュー": "mugi",
        "API設計書の作成": "mugi",
        "ステージング環境構築": "mugi",
        "トップページのコンポーネント設計": "yuki",
        "既存サイトのアクセスログ分析": "takeshi",
    }
    for title, assignee_key in assignment_map.items():
        if title in task_ids_by_title:
            await assignment_repo.assign(
                user_id=resolve_user_id("mugi"),  # project owner
                task_id=task_ids_by_title[title],
                assignment=TaskAssignmentCreate(
                    assignee_id=resolve_user_id(assignee_key),
                ),
            )
            print(f"  [OK] {title[:40]:40s} → {assignee_key}")

    # ---- 6. Project Members ----
    print("\n--- Creating Project Members ---")
    for pm in _project_members():
        create = pm["create"]
        create.member_user_id = resolve_member_id(create.member_user_id)
        await member_repo.create(
            user_id=resolve_user_id(pm["owner"]),
            project_id=real_project_ids[pm["project_key"]],
            member=create,
        )
        print(f"  [OK] {pm['project_key']:15s} ← member={create.member_user_id[:8]}... role={create.role}")

    # ---- 7. Check-ins ----
    print("\n--- Creating Check-ins ---")
    for ci in _checkins():
        create = ci["create"]
        create.member_user_id = resolve_member_id(create.member_user_id)
        await checkin_repo.create_v2(
            user_id=resolve_user_id(ci["owner"]),
            project_id=real_project_ids[ci["project_key"]],
            checkin=create,
        )
        member_name = [k for k, v in real_user_ids.items() if v == create.member_user_id][0]
        print(f"  [OK] {member_name:10s} items={len(create.items)} mood={create.mood}")

    # ---- 8. Recurring Meeting ----
    print("\n--- Creating Recurring Meeting ---")
    rm_data = _recurring_meeting()
    rm = await meeting_repo.create(
        user_id=resolve_user_id(rm_data["owner"]),
        data=rm_data["create"],
    )
    print(f"  [OK] {rm.title} (every {rm.frequency} on weekday={rm.weekday})")

    # ---- 9. Meeting Agenda Items ----
    print("\n--- Creating Meeting Agenda Items ---")
    for ai_data in _meeting_agenda_items():
        agenda = await agenda_repo.create(
            user_id=resolve_user_id(ai_data["owner"]),
            meeting_id=rm.id,
            data=ai_data["create"],
        )
        print(f"  [OK] [{agenda.order_index}] {agenda.title[:50]}")

    # ---- 10. Achievement (personal) ----
    print("\n--- Creating Achievement ---")
    ach_data = _achievement()
    ach = ach_data["achievement"]
    # Resolve user id
    ach.user_id = resolve_user_id("mugi")
    # Update project_ids
    ach.project_ids = [real_project_ids.get("a_company", ach.project_ids[0]),
                       real_project_ids.get("study_group", ach.project_ids[1])]
    for snap in ach.task_snapshots:
        for key, pid in real_project_ids.items():
            if snap.project_id and snap.project_id in PROJECT_IDS.values():
                snap.project_id = pid
    await achievement_repo.create(user_id=ach.user_id, achievement=ach)
    print(f"  [OK] {ach.period_label} tasks={ach.task_count}")

    # ---- 11. Project Achievement ----
    print("\n--- Creating Project Achievement ---")
    pach_data = _project_achievement()
    pach = pach_data["achievement"]
    pach.project_id = real_project_ids["a_company"]
    # Resolve member user ids in contributions
    for mc in pach.member_contributions:
        mc.user_id = resolve_member_id(mc.user_id)
    await project_achievement_repo.create(project_id=pach.project_id, achievement=pach)
    print(f"  [OK] A社PJ {pach.period_label}")

    # ---- 12. Memories ----
    print("\n--- Creating Memories ---")
    for m in _memories():
        create = m["create"]
        # Resolve project_id if present
        if create.project_id:
            for key, pid in real_project_ids.items():
                if create.project_id == PROJECT_IDS.get(key):
                    create.project_id = pid
                    break
        await memory_repo.create(
            user_id=resolve_user_id(m["owner"]),
            memory=create,
        )
        scope_label = f"{create.scope}/{create.memory_type}"
        print(f"  [OK] {scope_label:25s} {create.content[:40]}...")

    # ---- 13. Heartbeat Settings ----
    print("\n--- Creating Heartbeat Settings ---")
    hb_data = _heartbeat_settings()
    hb_settings = await heartbeat_settings_repo.upsert(
        user_id=resolve_user_id(hb_data["owner"]),
        update=hb_data["update"],
    )
    print(f"  [OK] {hb_data['owner']} enabled={hb_settings.enabled} intensity={hb_settings.heartbeat_intensity}")

    # ---- 14. Heartbeat Events ----
    print("\n--- Creating Heartbeat Events ---")
    for he in _heartbeat_events():
        event = he["event"]
        event.user_id = resolve_user_id("mugi")
        task_title = he["task_title"]
        if task_title in task_ids_by_title:
            event.task_id = task_ids_by_title[task_title]
        await heartbeat_event_repo.create(event)
        print(f"  [OK] [{event.severity.value:8s}] score={event.risk_score:.2f} {task_title}")

    # ---- 15. Heartbeat Chat Messages ----
    print("\n--- Creating Heartbeat Chat Messages ---")
    mugi_uid = resolve_user_id("mugi")
    for hc in _heartbeat_chat_messages():
        task_title = hc["task_title"]
        content = hc["content"]
        # Resolve task://__resolve__ to actual task id
        if task_title in task_ids_by_title:
            content = content.replace("__resolve__", str(task_ids_by_title[task_title]))
        await chat_repo.add_message(
            user_id=mugi_uid,
            session_id=hc["session_id"],
            role="assistant",
            content=content,
            title=hc["title"],
        )
        print(f"  [OK] {hc['title'][:50]}")

    # ---- 16. Heartbeat Notifications ----
    print("\n--- Creating Heartbeat Notifications ---")
    for hn in _heartbeat_notifications():
        notif = hn["notification"]
        notif.user_id = resolve_user_id("mugi")
        task_title = hn["task_title"]
        if task_title in task_ids_by_title:
            notif.link_id = str(task_ids_by_title[task_title])
        # Resolve project_id
        if notif.project_id:
            for key, pid in real_project_ids.items():
                if notif.project_id == PROJECT_IDS.get(key):
                    notif.project_id = pid
                    break
        await notification_repo.create(notif)
        print(f"  [OK] {notif.title}: {task_title}")

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("  SEED COMPLETE")
    print("=" * 60)
    print(f"\nLogin credentials (password: {PASSWORD}):")
    for key, uid in real_user_ids.items():
        print(f"  username: {key:10s}  user_id: {uid}")
    print()


def _print_plan() -> None:
    print("\nUsers (3):")
    for u in _users():
        print(f"  - {u['key']:10s} ({u['create'].email})")

    print(f"\nProjects ({len(_projects())}):")
    for p in _projects():
        print(f"  - {p['create'].name} (owner: {p['owner']}, vis: {p['create'].visibility})")

    print("\nPhases (2): A社PJ設計・実装フェーズ")

    print(f"\nTasks ({len(_existing_tasks())}):")
    for t in _existing_tasks():
        status = t.get("status", "TODO")
        print(f"  - [{status:11s}] {t['create'].title} (owner: {t['owner']})")

    print("\nProject Members (3): A社PJにmugi/yuki/takeshi")

    print("\nCheck-ins (3): mugi/yuki/takeshiの本日分")

    print("\nRecurring Meeting (1): A社PJ 週次定例（水曜10:00）")

    print("\nMeeting Agenda Items (4): チェックインベースの議題")

    print("\nAchievement (1): Mugiの週次達成項目")

    print("\nProject Achievement (1): A社PJチーム達成")

    print("\nMemories (4): ユーザー嗜好2件 + プロジェクト情報2件")

    print("\nHeartbeat Settings (1): Mugiの見落としチェック設定")
    print("\nHeartbeat Events (3): ステージング環境/アウトライン/API設計書のリスク検知")

    print("\nHeartbeat Chat Messages (2): 高リスクタスクへのAI声かけチャット")

    print("\nHeartbeat Notifications (2): 未着手タスクのリマインド通知")

    print("\n→ --apply フラグで実行してください")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed demo data for the Nagi 3-min demo video."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually insert data. Default is dry-run.",
    )
    args = parser.parse_args()
    asyncio.run(seed(dry_run=not args.apply))


if __name__ == "__main__":
    main()
