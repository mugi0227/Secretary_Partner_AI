"""
Migrate projects table to add new Phase 2 fields.

This script adds:
- context: TEXT (detailed README-like content)
- priority: INTEGER DEFAULT 5
- goals: JSON (list of project goals)
- key_points: JSON (list of key points)
- kpi_config: JSON (KPI config blob)
"""

import sqlite3
import sys

DB_PATH = "secretary.db"


def migrate():
    """Run migration to add new project fields."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Starting migration...")

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(projects)")
        columns = {row[1] for row in cursor.fetchall()}

        # Add context column if not exists
        if "context" not in columns:
            print("Adding 'context' column...")
            cursor.execute("ALTER TABLE projects ADD COLUMN context TEXT")
        else:
            print("'context' column already exists")

        # Add priority column if not exists
        if "priority" not in columns:
            print("Adding 'priority' column...")
            cursor.execute("ALTER TABLE projects ADD COLUMN priority INTEGER DEFAULT 5")
        else:
            print("'priority' column already exists")

        # Add goals column if not exists
        if "goals" not in columns:
            print("Adding 'goals' column...")
            cursor.execute("ALTER TABLE projects ADD COLUMN goals TEXT")  # JSON stored as TEXT
        else:
            print("'goals' column already exists")

        # Add key_points column if not exists
        if "key_points" not in columns:
            print("Adding 'key_points' column...")
            cursor.execute("ALTER TABLE projects ADD COLUMN key_points TEXT")  # JSON stored as TEXT
        else:
            print("'key_points' column already exists")

        # Add kpi_config column if not exists
        if "kpi_config" not in columns:
            print("Adding 'kpi_config' column...")
            cursor.execute("ALTER TABLE projects ADD COLUMN kpi_config TEXT")  # JSON stored as TEXT
        else:
            print("'kpi_config' column already exists")

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
