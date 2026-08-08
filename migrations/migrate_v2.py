"""Idempotently upgrade an existing SQLite database to Job Tracker V2."""
import argparse
import sqlite3
from pathlib import Path

def migrate(database):
    connection = sqlite3.connect(database)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(application)")}
        if not columns: raise RuntimeError("The application table does not exist; start the app once for a new install.")
        for name, sql_type in {"next_action":"TEXT", "next_action_date":"DATE", "next_action_completed_at":"DATETIME"}.items():
            if name not in columns: connection.execute(f"ALTER TABLE application ADD COLUMN {name} {sql_type}")
        connection.execute("""CREATE TABLE IF NOT EXISTS activity (id INTEGER NOT NULL PRIMARY KEY, application_id INTEGER NOT NULL, contact_id INTEGER, event_type VARCHAR(50) NOT NULL, description TEXT NOT NULL, created_at DATETIME NOT NULL, FOREIGN KEY(application_id) REFERENCES application (id))""")
        for column in ("application_id", "event_type", "created_at"):
            connection.execute(f"CREATE INDEX IF NOT EXISTS ix_activity_{column} ON activity ({column})")
        connection.commit()
    finally: connection.close()

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("database", nargs="?", type=Path, default=Path("instance/job_tracker.db"))
    migrate(parser.parse_args().database); print("V2 migration complete.")
