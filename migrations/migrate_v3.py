"""Idempotently upgrade an existing SQLite Job Tracker database to V3."""
import argparse
import sqlite3
from pathlib import Path


def migrate(database):
    connection = sqlite3.connect(database)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(application)")}
        if not columns: raise RuntimeError("The application table does not exist; start the app once for a new install.")
        if "job_posting_text" not in columns: connection.execute("ALTER TABLE application ADD COLUMN job_posting_text TEXT")
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS application_import_draft (id INTEGER PRIMARY KEY, raw_job_posting TEXT NOT NULL, draft_data TEXT NOT NULL, provider VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, confirmed_at DATETIME, application_id INTEGER REFERENCES application(id));
        CREATE TABLE IF NOT EXISTS document (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, document_type VARCHAR(30) NOT NULL, source_type VARCHAR(20) NOT NULL, application_id INTEGER REFERENCES application(id), persona_id INTEGER REFERENCES persona(id), original_filename VARCHAR(255), stored_filename VARCHAR(80), mime_type VARCHAR(100), size_bytes INTEGER, text_content TEXT, notes TEXT, provider VARCHAR(20), model_name VARCHAR(100), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE IF NOT EXISTS document_source (generated_document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE, source_document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE, PRIMARY KEY(generated_document_id, source_document_id));
        CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY, full_name VARCHAR(160), location VARCHAR(160), email VARCHAR(254), phone VARCHAR(80), linkedin_url VARCHAR(500));
        CREATE INDEX IF NOT EXISTS ix_document_document_type ON document(document_type);
        CREATE INDEX IF NOT EXISTS ix_document_application_id ON document(application_id);
        """)
        connection.commit()
    finally: connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("database", nargs="?", type=Path, default=Path("instance/job_tracker.db"))
    migrate(parser.parse_args().database); print("V3 migration complete.")
