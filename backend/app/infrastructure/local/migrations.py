"""
Database schema migration helpers.

This module provides utilities for managing SQLite database schema migrations.
"""

import re

from sqlalchemy import text

from app.infrastructure.local.database import get_engine


async def run_migrations():
    """
    Run all pending migrations.

    This function checks the current database schema and applies any missing
    columns or indexes to bring the database up to date.
    """
    engine = get_engine()

    async with engine.begin() as conn:
        # Check existing columns
        result = await conn.execute(text("PRAGMA table_info(tasks)"))
        columns = {row[1] for row in result}

        # Add new columns if they don't exist
        if "purpose" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN purpose TEXT"))

        if "start_time" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN start_time DATETIME"))

        if "end_time" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN end_time DATETIME"))

        if "is_fixed_time" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN is_fixed_time BOOLEAN DEFAULT 0"))
            # Create index for efficient filtering
            await conn.execute(text("CREATE INDEX idx_tasks_is_fixed_time ON tasks(is_fixed_time)"))

        if "is_all_day" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN is_all_day BOOLEAN DEFAULT 0"))
            await conn.execute(text("CREATE INDEX idx_tasks_is_all_day ON tasks(is_all_day)"))

        if "location" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN location VARCHAR(500)"))

        if "attendees" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN attendees JSON"))

        if "meeting_notes" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN meeting_notes TEXT"))

        if "start_not_before" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN start_not_before DATETIME"))

        if "progress" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN progress INTEGER DEFAULT 0 NOT NULL"))

        if "auto_completed_by_parent_id" not in columns:
            await conn.execute(
                text("ALTER TABLE tasks ADD COLUMN auto_completed_by_parent_id VARCHAR(36)")
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_auto_completed_by_parent_id "
                    "ON tasks(auto_completed_by_parent_id)"
                )
            )

        if "order_in_parent" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN order_in_parent INTEGER"))

        if "same_day_allowed" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN same_day_allowed BOOLEAN DEFAULT 1"))

        if "min_gap_days" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN min_gap_days INTEGER DEFAULT 0"))

        if "recurring_meeting_id" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN recurring_meeting_id VARCHAR(36)"))
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_tasks_recurring_meeting_id ON tasks(recurring_meeting_id)")
            )

        if "milestone_id" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN milestone_id VARCHAR(36)"))
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_tasks_milestone_id ON tasks(milestone_id)")
            )

        if "touchpoint_count" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN touchpoint_count INTEGER"))

        if "touchpoint_minutes" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN touchpoint_minutes INTEGER"))

        if "touchpoint_gap_days" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN touchpoint_gap_days INTEGER DEFAULT 0"))

        if "touchpoint_steps" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN touchpoint_steps JSON"))

        # Achievement-related task fields
        if "completion_note" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN completion_note TEXT"))

        if "completed_at" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN completed_at DATETIME"))
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_tasks_completed_at ON tasks(completed_at)")
            )

        if "completed_by" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN completed_by VARCHAR(255)"))

        # Subtask guide field
        if "guide" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN guide TEXT"))

        # Pinned date field for forced scheduling
        if "pinned_date" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN pinned_date DATETIME"))

        # Check checkins table for checkin_type and V2 fields
        checkin_result = await conn.execute(text("PRAGMA table_info(checkins)"))
        checkin_columns = {row[1] for row in checkin_result}
        if "checkin_type" not in checkin_columns:
            await conn.execute(
                text("ALTER TABLE checkins ADD COLUMN checkin_type VARCHAR(20) DEFAULT 'weekly'")
            )

        # V2 check-in fields
        if "mood" not in checkin_columns:
            await conn.execute(text("ALTER TABLE checkins ADD COLUMN mood VARCHAR(20)"))

        if "must_discuss_in_next_meeting" not in checkin_columns:
            await conn.execute(text("ALTER TABLE checkins ADD COLUMN must_discuss_in_next_meeting TEXT"))

        if "free_comment" not in checkin_columns:
            await conn.execute(text("ALTER TABLE checkins ADD COLUMN free_comment TEXT"))

        # Check projects table for visibility column
        project_result = await conn.execute(text("PRAGMA table_info(projects)"))
        project_columns = {row[1] for row in project_result}
        if "visibility" not in project_columns:
            await conn.execute(
                text("ALTER TABLE projects ADD COLUMN visibility VARCHAR(20) DEFAULT 'PRIVATE'")
            )

        if "parent_project_id" not in project_columns:
            await conn.execute(
                text("ALTER TABLE projects ADD COLUMN parent_project_id VARCHAR(36)")
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_projects_parent_project_id ON projects(parent_project_id)")
            )

        # Create project_link_requests table if missing
        link_req_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='project_link_requests'")
        )
        if not link_req_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE project_link_requests (
                        id VARCHAR(36) PRIMARY KEY,
                        child_project_id VARCHAR(36) NOT NULL,
                        parent_project_id VARCHAR(36) NOT NULL,
                        requested_by VARCHAR(255) NOT NULL,
                        status VARCHAR(20) DEFAULT 'PENDING',
                        member_ids_to_add JSON,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_link_requests_child ON project_link_requests(child_project_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_link_requests_parent ON project_link_requests(parent_project_id)")
            )
        else:
            # Add approval tracking columns if missing
            link_req_cols_result = await conn.execute(
                text("PRAGMA table_info(project_link_requests)")
            )
            link_req_columns = {row[1] for row in link_req_cols_result}
            if "parent_approved" not in link_req_columns:
                await conn.execute(
                    text("ALTER TABLE project_link_requests ADD COLUMN parent_approved BOOLEAN DEFAULT 0")
                )
            if "child_approved" not in link_req_columns:
                await conn.execute(
                    text("ALTER TABLE project_link_requests ADD COLUMN child_approved BOOLEAN DEFAULT 0")
                )

        # Check phases table for fixed_buffer_minutes
        phase_result = await conn.execute(text("PRAGMA table_info(phases)"))
        phase_columns = {row[1] for row in phase_result}
        if "fixed_buffer_minutes" not in phase_columns:
            await conn.execute(text("ALTER TABLE phases ADD COLUMN fixed_buffer_minutes INTEGER"))

        # Check schedule_snapshots table for plan_utilization_ratio
        snapshot_result = await conn.execute(text("PRAGMA table_info(schedule_snapshots)"))
        snapshot_columns = {row[1] for row in snapshot_result}
        if "plan_utilization_ratio" not in snapshot_columns:
            await conn.execute(
                text("ALTER TABLE schedule_snapshots ADD COLUMN plan_utilization_ratio FLOAT DEFAULT 1.0")
            )

        # Create checkin_items table if missing
        checkin_items_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='checkin_items'")
        )
        if not checkin_items_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE checkin_items (
                        id VARCHAR(36) PRIMARY KEY,
                        checkin_id VARCHAR(36) NOT NULL,
                        user_id VARCHAR(255) NOT NULL,
                        category VARCHAR(20) NOT NULL,
                        content TEXT NOT NULL,
                        related_task_id VARCHAR(36),
                        urgency VARCHAR(10) DEFAULT 'medium',
                        order_index INTEGER DEFAULT 0,
                        created_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_checkin_items_checkin_id ON checkin_items(checkin_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_checkin_items_user_id ON checkin_items(user_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_checkin_items_category ON checkin_items(category)")
            )
            await conn.execute(
                text("CREATE INDEX idx_checkin_items_related_task_id ON checkin_items(related_task_id)")
            )

        # Check users table for local auth fields
        user_result = await conn.execute(text("PRAGMA table_info(users)"))
        user_columns = {row[1] for row in user_result}
        if "username" not in user_columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(255)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"))
        if "password_hash" not in user_columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        if "timezone" not in user_columns:
            # Add timezone column with default UTC
            await conn.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC' NOT NULL"))
            # Set existing users to UTC (in case DEFAULT doesn't apply to existing rows)
            await conn.execute(text("UPDATE users SET timezone = 'UTC' WHERE timezone IS NULL"))
        if "first_name" not in user_columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR(100)"))
        if "last_name" not in user_columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR(100)"))
        if "enable_weekly_meeting_reminder" not in user_columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN enable_weekly_meeting_reminder BOOLEAN DEFAULT 0 NOT NULL"))

        # Create recurring_meetings table if missing
        recurring_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='recurring_meetings'")
        )
        if not recurring_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE recurring_meetings (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        project_id VARCHAR(36),
                        title VARCHAR(500) NOT NULL,
                        frequency VARCHAR(20) NOT NULL,
                        weekday INTEGER NOT NULL,
                        start_time VARCHAR(10) NOT NULL,
                        duration_minutes INTEGER NOT NULL,
                        location VARCHAR(500),
                        attendees JSON,
                        agenda_window_days INTEGER NOT NULL DEFAULT 7,
                        anchor_date DATE NOT NULL,
                        last_occurrence DATETIME,
                        is_active BOOLEAN DEFAULT 1,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_recurring_meetings_user_id ON recurring_meetings(user_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_recurring_meetings_project_id ON recurring_meetings(project_id)")
            )

        # check for meeting_agenda_items table
        agenda_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='meeting_agenda_items'")
        )
        if not agenda_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE meeting_agenda_items (
                        id VARCHAR(36) PRIMARY KEY,
                        meeting_id VARCHAR(36) NOT NULL,
                        user_id VARCHAR(255) NOT NULL,
                        title VARCHAR(500) NOT NULL,
                        description TEXT,
                        duration_minutes INTEGER,
                        order_index INTEGER DEFAULT 0,
                        is_completed BOOLEAN DEFAULT 0,
                        event_date DATE,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_meeting_agenda_items_meeting_id ON meeting_agenda_items(meeting_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_meeting_agenda_items_user_id ON meeting_agenda_items(user_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_meeting_agenda_items_event_date ON meeting_agenda_items(event_date)")
            )
        else:
            # Check for event_date column
            agenda_cols_result = await conn.execute(text("PRAGMA table_info(meeting_agenda_items)"))
            agenda_columns = {row[1] for row in agenda_cols_result}
            if "event_date" not in agenda_columns:
                await conn.execute(text("ALTER TABLE meeting_agenda_items ADD COLUMN event_date DATE"))
                await conn.execute(
                    text("CREATE INDEX idx_meeting_agenda_items_event_date ON meeting_agenda_items(event_date)")
                )

            if "task_id" not in agenda_columns:
                await conn.execute(text("ALTER TABLE meeting_agenda_items ADD COLUMN task_id VARCHAR(36)"))
                await conn.execute(
                    text("CREATE INDEX idx_meeting_agenda_items_task_id ON meeting_agenda_items(task_id)")
                )

        # Ensure chat session primary key is scoped by user_id.
        await _ensure_chat_sessions_composite_pk(conn)

        # Migrate existing [1], [2], [3] patterns to order_in_parent
        await _migrate_step_numbers_to_order(conn)
        await _backfill_subtask_project_ids(conn)

        # Ensure task_assignments supports multiple assignees per task.
        await _ensure_task_assignment_unique(conn)

        # Ensure username has UNIQUE constraint
        await _ensure_username_unique(conn)
        await _ensure_schedule_settings(conn)
        await _ensure_daily_schedule_plans(conn)
        await _ensure_heartbeat_tables(conn)

        # Create meeting_sessions table if missing
        session_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='meeting_sessions'")
        )
        if not session_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE meeting_sessions (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        task_id VARCHAR(36) NOT NULL,
                        status VARCHAR(20) DEFAULT 'PREPARATION',
                        current_agenda_index INTEGER,
                        transcript TEXT,
                        summary TEXT,
                        started_at DATETIME,
                        ended_at DATETIME,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_meeting_sessions_user_id ON meeting_sessions(user_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_meeting_sessions_task_id ON meeting_sessions(task_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_meeting_sessions_status ON meeting_sessions(status)")
            )

        # Create achievements table if missing
        achievement_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='achievements'")
        )
        if not achievement_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE achievements (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        period_start DATETIME NOT NULL,
                        period_end DATETIME NOT NULL,
                        period_label VARCHAR(100),
                        summary TEXT NOT NULL,
                        growth_points JSON,
                        skill_analysis JSON,
                        next_suggestions JSON,
                        task_count INTEGER DEFAULT 0,
                        project_ids JSON,
                        task_snapshots JSON,
                        append_note TEXT,
                        generation_type VARCHAR(20) DEFAULT 'MANUAL',
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_achievements_user_id ON achievements(user_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_achievements_period_start ON achievements(period_start)")
            )
            await conn.execute(
                text("CREATE INDEX idx_achievements_period_end ON achievements(period_end)")
            )
        else:
            achievement_columns = {
                row[1]
                for row in (await conn.execute(text("PRAGMA table_info(achievements)"))).fetchall()
            }
            if "task_snapshots" not in achievement_columns:
                await conn.execute(text("ALTER TABLE achievements ADD COLUMN task_snapshots JSON"))
            if "append_note" not in achievement_columns:
                await conn.execute(text("ALTER TABLE achievements ADD COLUMN append_note TEXT"))
            if "weekly_activities" not in achievement_columns:
                await conn.execute(text("ALTER TABLE achievements ADD COLUMN weekly_activities JSON"))
            if "share_token" not in achievement_columns:
                await conn.execute(text("ALTER TABLE achievements ADD COLUMN share_token VARCHAR(36)"))
                await conn.execute(
                    text("CREATE UNIQUE INDEX IF NOT EXISTS idx_achievements_share_token ON achievements(share_token)")
                )

        project_achievement_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='project_achievements'")
        )
        if project_achievement_result.scalar():
            project_achievement_columns = {
                row[1]
                for row in (
                    await conn.execute(text("PRAGMA table_info(project_achievements)"))
                ).fetchall()
            }
            if "append_note" not in project_achievement_columns:
                await conn.execute(
                    text("ALTER TABLE project_achievements ADD COLUMN append_note TEXT")
                )

        # Create milestones table if missing
        milestone_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='milestones'")
        )
        if not milestone_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE milestones (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        project_id VARCHAR(36) NOT NULL,
                        phase_id VARCHAR(36) NOT NULL,
                        title VARCHAR(200) NOT NULL,
                        description TEXT,
                        status VARCHAR(20) DEFAULT 'ACTIVE',
                        order_in_phase INTEGER DEFAULT 1 NOT NULL,
                        due_date DATETIME,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_milestones_user_id ON milestones(user_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_milestones_project_id ON milestones(project_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_milestones_phase_id ON milestones(phase_id)")
            )

        # Create postpone_events table if missing
        postpone_events_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='postpone_events'")
        )
        if not postpone_events_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE postpone_events (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        task_id VARCHAR(36) NOT NULL,
                        from_date DATE NOT NULL,
                        to_date DATE NOT NULL,
                        reason TEXT,
                        pinned BOOLEAN DEFAULT 0,
                        created_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_postpone_events_user_id ON postpone_events(user_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_postpone_events_task_id ON postpone_events(task_id)")
            )


        # Multi-member completion flag
        if "requires_all_completion" not in columns:
            await conn.execute(
                text("ALTER TABLE tasks ADD COLUMN requires_all_completion BOOLEAN DEFAULT 0 NOT NULL")
            )

        # Add recurring_task_id to tasks table
        if "recurring_task_id" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN recurring_task_id VARCHAR(36)"))
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_tasks_recurring_task_id ON tasks(recurring_task_id)")
        )
        # Keep only one generated task per (user, recurring definition, due date).
        await conn.execute(
            text(
                """
                DELETE FROM tasks
                WHERE recurring_task_id IS NOT NULL
                  AND due_date IS NOT NULL
                  AND rowid NOT IN (
                      SELECT MIN(rowid)
                      FROM tasks
                      WHERE recurring_task_id IS NOT NULL
                        AND due_date IS NOT NULL
                      GROUP BY user_id, recurring_task_id, due_date
                  )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_recurring_task_occurrence_unique
                ON tasks(user_id, recurring_task_id, due_date)
                WHERE recurring_task_id IS NOT NULL AND due_date IS NOT NULL
                """
            )
        )

        # Create recurring_tasks table if missing
        recurring_tasks_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='recurring_tasks'")
        )
        if not recurring_tasks_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE recurring_tasks (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        project_id VARCHAR(36),
                        phase_id VARCHAR(36),
                        title VARCHAR(500) NOT NULL,
                        description TEXT,
                        purpose TEXT,
                        frequency VARCHAR(20) NOT NULL DEFAULT 'weekly',
                        weekday INTEGER,
                        day_of_month INTEGER,
                        custom_interval_days INTEGER,
                        start_time VARCHAR(10),
                        estimated_minutes INTEGER,
                        importance VARCHAR(10) DEFAULT 'MEDIUM',
                        urgency VARCHAR(10) DEFAULT 'MEDIUM',
                        energy_level VARCHAR(10) DEFAULT 'LOW',
                        anchor_date DATE NOT NULL,
                        last_generated_date DATE,
                        is_active BOOLEAN DEFAULT 1,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_recurring_tasks_user_id ON recurring_tasks(user_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_recurring_tasks_project_id ON recurring_tasks(project_id)")
            )
        else:
            # Add weekdays column if missing (for daily frequency day-of-week filter)
            rt_cols_result = await conn.execute(text("PRAGMA table_info(recurring_tasks)"))
            rt_columns = {row[1] for row in rt_cols_result}
            if "weekdays" not in rt_columns:
                await conn.execute(text("ALTER TABLE recurring_tasks ADD COLUMN weekdays JSON"))

        # Create issue_comments table if missing
        issue_comments_result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='issue_comments'")
        )
        if not issue_comments_result.scalar():
            await conn.execute(
                text(
                    """
                    CREATE TABLE issue_comments (
                        id VARCHAR(36) PRIMARY KEY,
                        issue_id VARCHAR(36) NOT NULL,
                        user_id VARCHAR(255) NOT NULL,
                        content TEXT NOT NULL,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await conn.execute(
                text("CREATE INDEX idx_issue_comments_issue_id ON issue_comments(issue_id)")
            )
            await conn.execute(
                text("CREATE INDEX idx_issue_comments_user_id ON issue_comments(user_id)")
            )


async def _ensure_chat_sessions_composite_pk(conn):
    """
    Ensure chat_sessions uses a composite primary key (session_id, user_id).

    Older schemas used session_id as the sole primary key, which caused
    collisions across users. This migration rebuilds chat_sessions and
    chat_messages to reference the composite key.
    """
    table_result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_sessions'")
    )
    if not table_result.scalar():
        return

    info_result = await conn.execute(text("PRAGMA table_info('chat_sessions')"))
    rows = info_result.fetchall()
    pk_columns = [row[1] for row in rows if row[5] > 0]
    if set(pk_columns) == {"session_id", "user_id"}:
        return

    await conn.execute(text("PRAGMA foreign_keys=OFF"))

    messages_table = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
    )
    has_messages = bool(messages_table.scalar())
    if has_messages:
        await conn.execute(text("ALTER TABLE chat_messages RENAME TO chat_messages_old"))

    await conn.execute(text("ALTER TABLE chat_sessions RENAME TO chat_sessions_old"))

    await conn.execute(
        text(
            """
            CREATE TABLE chat_sessions (
                session_id VARCHAR(100) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                title VARCHAR(200),
                created_at DATETIME,
                updated_at DATETIME,
                PRIMARY KEY (session_id, user_id)
            )
            """
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)")
    )
    await conn.execute(
        text(
            """
            INSERT INTO chat_sessions (session_id, user_id, title, created_at, updated_at)
            SELECT session_id, user_id, title, created_at, updated_at
            FROM chat_sessions_old
            """
        )
    )

    await conn.execute(
        text(
            """
            CREATE TABLE chat_messages (
                id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(100) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                created_at DATETIME,
                FOREIGN KEY (session_id, user_id)
                    REFERENCES chat_sessions(session_id, user_id)
                    ON DELETE CASCADE
            )
            """
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at)")
    )

    if has_messages:
        await conn.execute(
            text(
                """
                INSERT INTO chat_messages (
                    id, session_id, user_id, role, content, created_at
                )
                SELECT id, session_id, user_id, role, content, created_at
                FROM chat_messages_old
                """
            )
        )
        await conn.execute(text("DROP TABLE chat_messages_old"))

    await conn.execute(text("DROP TABLE chat_sessions_old"))
    await conn.execute(text("PRAGMA foreign_keys=ON"))


async def _ensure_task_assignment_unique(conn):
    """
    Ensure task_assignments has a UNIQUE constraint on (task_id, user_id, assignee_id).

    Older schemas used (task_id, user_id), which blocks multiple assignees.
    """
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='task_assignments'")
    )
    if not result.scalar():
        return

    desired = ["task_id", "user_id", "assignee_id"]
    index_list = await conn.execute(text("PRAGMA index_list('task_assignments')"))
    for row in index_list.fetchall():
        if not row[2]:
            continue
        index_name = row[1]
        index_info = await conn.execute(text(f"PRAGMA index_info('{index_name}')"))
        columns = [info_row[2] for info_row in index_info.fetchall()]
        if columns == desired:
            return

    await conn.execute(text("ALTER TABLE task_assignments RENAME TO task_assignments_old"))
    await conn.execute(
        text(
            """
            CREATE TABLE task_assignments (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                task_id VARCHAR(36) NOT NULL,
                assignee_id VARCHAR(255) NOT NULL,
                status VARCHAR(20),
                progress INTEGER,
                created_at DATETIME,
                updated_at DATETIME,
                CONSTRAINT uq_task_assignment UNIQUE (task_id, user_id, assignee_id)
            )
            """
        )
    )
    await conn.execute(
        text(
            """
            INSERT INTO task_assignments (
                id, user_id, task_id, assignee_id, status, progress, created_at, updated_at
            )
            SELECT
                id, user_id, task_id, assignee_id, status, progress, created_at, updated_at
            FROM task_assignments_old
            """
        )
    )
    await conn.execute(text("DROP TABLE task_assignments_old"))
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_task_assignments_user_id ON task_assignments(user_id)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_task_assignments_task_id ON task_assignments(task_id)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_task_assignments_assignee_id ON task_assignments(assignee_id)")
    )


async def _migrate_step_numbers_to_order(conn):
    """
    Migrate existing [1], [2], [3] step numbers from titles to order_in_parent field.

    Extracts step numbers from task titles like "[1] タスク名" and populates order_in_parent.
    Also removes the [N] prefix from the title for cleaner display.
    """
    # Get all tasks with parent_id (subtasks only)
    result = await conn.execute(
        text("SELECT id, title, parent_id FROM tasks WHERE parent_id IS NOT NULL AND order_in_parent IS NULL")
    )
    tasks = result.fetchall()

    step_number_pattern = re.compile(r'^\[(\d+)\]\s*')

    for task_id, title, parent_id in tasks:
        match = step_number_pattern.match(title)
        if match:
            step_number = int(match.group(1))
            # Remove [N] prefix from title
            clean_title = step_number_pattern.sub('', title)

            # Update order_in_parent and clean title
            await conn.execute(
                text("UPDATE tasks SET order_in_parent = :order, title = :title WHERE id = :id"),
                {"order": step_number, "title": clean_title, "id": task_id}
            )


async def _backfill_subtask_project_ids(conn):
    """
    Backfill missing subtask project_id from the parent task's project_id.

    Older task creation flows could create subtasks with parent_id but project_id=NULL
    even when the parent belonged to a project. This breaks parent modal subtask queries
    that scope by project_id.
    """
    await conn.execute(
        text(
            """
            UPDATE tasks
            SET project_id = (
                SELECT parent.project_id
                FROM tasks AS parent
                WHERE parent.id = tasks.parent_id
            )
            WHERE tasks.parent_id IS NOT NULL
              AND tasks.project_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM tasks AS parent
                  WHERE parent.id = tasks.parent_id
                    AND parent.project_id IS NOT NULL
              )
            """
        )
    )


async def _ensure_username_unique(conn):
    """
    Ensure users.username has a UNIQUE constraint.

    Older schemas only had an INDEX, not a UNIQUE constraint.
    SQLite requires table recreation to add constraints.
    """
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    )
    if not result.scalar():
        return

    # Check if uq_user_username constraint already exists
    index_list = await conn.execute(text("PRAGMA index_list('users')"))
    for row in index_list.fetchall():
        index_name = row[1]
        is_unique = row[2]
        if index_name == "uq_user_username" and is_unique:
            return  # Already has the constraint

    # Check for any unique index on username alone
    for row in (await conn.execute(text("PRAGMA index_list('users')"))).fetchall():
        index_name = row[1]
        is_unique = row[2]
        if not is_unique:
            continue
        index_info = await conn.execute(text(f"PRAGMA index_info('{index_name}')"))
        columns = [info_row[2] for info_row in index_info.fetchall()]
        if columns == ["username"]:
            return  # Already has unique constraint on username

    # Recreate table with UNIQUE constraint
    await conn.execute(text("PRAGMA foreign_keys=OFF"))

    await conn.execute(text("ALTER TABLE users RENAME TO users_old"))

    await conn.execute(
        text(
            """
            CREATE TABLE users (
                id VARCHAR(36) PRIMARY KEY,
                provider_issuer VARCHAR(500) NOT NULL,
                provider_sub VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                display_name VARCHAR(255),
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                username VARCHAR(255),
                password_hash VARCHAR(255),
                timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
                enable_weekly_meeting_reminder BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME,
                CONSTRAINT uq_user_provider UNIQUE (provider_issuer, provider_sub),
                CONSTRAINT uq_user_username UNIQUE (username)
            )
            """
        )
    )

    await conn.execute(
        text(
            """
            INSERT INTO users (
                id, provider_issuer, provider_sub, email, display_name,
                first_name, last_name, username, password_hash, timezone,
                enable_weekly_meeting_reminder, created_at, updated_at
            )
            SELECT
                id, provider_issuer, provider_sub, email, display_name,
                first_name, last_name, username, password_hash,
                COALESCE(timezone, 'UTC'),
                COALESCE(enable_weekly_meeting_reminder, 0),
                created_at, updated_at
            FROM users_old
            """
        )
    )

    await conn.execute(text("DROP TABLE users_old"))

    # Recreate indexes
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_users_provider_issuer ON users(provider_issuer)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_users_provider_sub ON users(provider_sub)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    )

    await conn.execute(text("PRAGMA foreign_keys=ON"))


async def _ensure_schedule_settings(conn):
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_settings'")
    )
    if result.scalar():
        return

    await conn.execute(
        text(
            """
            CREATE TABLE schedule_settings (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL UNIQUE,
                weekly_work_hours_json JSON NOT NULL,
                buffer_hours FLOAT DEFAULT 1.0,
                break_after_task_minutes INTEGER DEFAULT 5,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_schedule_settings_user_id ON schedule_settings(user_id)")
    )


async def _ensure_daily_schedule_plans(conn):
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_schedule_plans'")
    )
    if result.scalar():
        return

    await conn.execute(
        text(
            """
            CREATE TABLE daily_schedule_plans (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                plan_date DATE NOT NULL,
                timezone VARCHAR(50) NOT NULL,
                plan_group_id VARCHAR(36) NOT NULL,
                schedule_day_json JSON NOT NULL,
                tasks_json JSON NOT NULL,
                unscheduled_json JSON NOT NULL,
                excluded_json JSON NOT NULL,
                time_blocks_json JSON NOT NULL,
                task_snapshots_json JSON NOT NULL,
                pinned_overflow_json JSON NOT NULL,
                plan_params_json JSON NOT NULL,
                generated_at DATETIME NOT NULL,
                updated_at DATETIME
            )
            """
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_daily_schedule_plans_user_id ON daily_schedule_plans(user_id)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_daily_schedule_plans_plan_date ON daily_schedule_plans(plan_date)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_daily_schedule_plans_group_id ON daily_schedule_plans(plan_group_id)")
    )


async def _ensure_heartbeat_tables(conn):
    settings_result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='heartbeat_settings'")
    )
    if not settings_result.scalar():
        await conn.execute(
            text(
                """
                CREATE TABLE heartbeat_settings (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL UNIQUE,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    notification_limit_per_day INTEGER NOT NULL DEFAULT 2,
                    notification_window_start VARCHAR(5) NOT NULL DEFAULT '09:00',
                    notification_window_end VARCHAR(5) NOT NULL DEFAULT '21:00',
                    heartbeat_intensity VARCHAR(20) NOT NULL DEFAULT 'standard',
                    daily_capacity_per_task_minutes INTEGER NOT NULL DEFAULT 60,
                    cooldown_hours_per_task INTEGER NOT NULL DEFAULT 24,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_heartbeat_settings_user_id ON heartbeat_settings(user_id)")
        )

    events_result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='heartbeat_events'")
    )
    if not events_result.scalar():
        await conn.execute(
            text(
                """
                CREATE TABLE heartbeat_events (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    task_id VARCHAR(36),
                    severity VARCHAR(20) NOT NULL,
                    risk_score FLOAT NOT NULL DEFAULT 0,
                    notification_id VARCHAR(36),
                    metadata_json JSON,
                    is_read BOOLEAN NOT NULL DEFAULT 0,
                    read_at DATETIME,
                    created_at DATETIME
                )
                """
            )
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_heartbeat_events_user_id ON heartbeat_events(user_id)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_heartbeat_events_task_id ON heartbeat_events(task_id)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_heartbeat_events_created_at ON heartbeat_events(created_at)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_heartbeat_events_is_read ON heartbeat_events(is_read)")
        )
    else:
        events_cols_result = await conn.execute(text("PRAGMA table_info(heartbeat_events)"))
        events_columns = {row[1] for row in events_cols_result.fetchall()}
        if "is_read" not in events_columns:
            await conn.execute(
                text("ALTER TABLE heartbeat_events ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0")
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_heartbeat_events_is_read ON heartbeat_events(is_read)")
            )
        if "read_at" not in events_columns:
            await conn.execute(text("ALTER TABLE heartbeat_events ADD COLUMN read_at DATETIME"))
