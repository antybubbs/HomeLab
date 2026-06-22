#!/usr/bin/env python3

import sqlite3
from pathlib import Path

DB_PATH = Path("/app/data/homelab.db")


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]


def table_exists(cursor, table):
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return cursor.fetchone() is not None


def main():
    if not DB_PATH.exists():
        print("Database does not exist yet. Skipping migrations.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    migrations_applied = []

    # Public releases before v0.18 do not have compute_hosts yet. In that case,
    # application startup creates the complete current table via SQLAlchemy.
    # May the migration God bless us all.
    if table_exists(cur, "compute_hosts"):
        if not column_exists(cur, "compute_hosts", "agent_last_seen_at"):
            cur.execute(
                "ALTER TABLE compute_hosts ADD COLUMN agent_last_seen_at DATETIME"
            )
            migrations_applied.append("compute_hosts.agent_last_seen_at")

        if not column_exists(cur, "compute_hosts", "encrypted_agent_token"):
            cur.execute(
                "ALTER TABLE compute_hosts ADD COLUMN encrypted_agent_token TEXT"
            )
            migrations_applied.append("compute_hosts.encrypted_agent_token")

    conn.commit()
    conn.close()

    if migrations_applied:
        print("Applied migrations:")
        for migration in migrations_applied:
            print(f" - {migration}")
    else:
        print("Database schema already up to date.")


if __name__ == "__main__":
    main()
