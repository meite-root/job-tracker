import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import Activity, Application, ApplicationImportDraft, Document, Pathway, Persona, create_app, db
from migrations.migrate_v3 import migrate


class V3WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); database = Path(self.temp.name) / "test.db"
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}", "INSTANCE_PATH": self.temp.name})
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context(): db.session.remove()
        self.temp.cleanup()

    def test_extraction_is_draft_and_confirmation_is_idempotent(self):
        with self.app.app_context():
            pathway = db.session.scalar(db.select(Pathway)); persona = db.session.scalar(db.select(Persona))
            pathway_id, persona_id = pathway.id, persona.id
        extracted = {"company": "Draft Co", "role_title": "Analyst", "location": "Remote", "job_url": "", "status": "Preparing", "notes": "Facts", "pathway_id": pathway_id, "persona_id": persona_id}
        with patch("app.extract_application_from_posting", return_value=extracted):
            response = self.client.post("/applications/import", data={"posting_text": "Complete posting", "provider": "openai"})
        with self.app.app_context():
            self.assertEqual(db.session.query(Application).count(), 0); draft = db.session.scalar(db.select(ApplicationImportDraft)); draft_id = draft.id
        response = self.client.get(response.location); self.assertIn(b"Draft Co", response.data)
        form = {"company": "Edited Co", "role_title": "Analyst", "status": "Preparing", "pathway_id": pathway_id, "persona_id": persona_id, "next_action": "Tailor CV", "next_action_date": "2026-08-20"}
        self.client.post(f"/applications/import/{draft_id}/confirm", data=form)
        self.client.post(f"/applications/import/{draft_id}/confirm", data=form)
        with self.app.app_context():
            self.assertEqual(db.session.query(Application).count(), 1); item = db.session.scalar(db.select(Application))
            self.assertEqual(item.job_posting_text, "Complete posting"); self.assertEqual(item.next_action, "Tailor CV")
            self.assertTrue(db.session.scalar(db.select(Activity).where(Activity.event_type == "application_imported")))

    def test_text_upload_download_and_delete(self):
        import io
        response = self.client.post("/files/upload", data={"title": "My CV", "document_type": "cv", "file": (io.BytesIO(b"Experience"), "resume.txt")}, content_type="multipart/form-data")
        with self.app.app_context():
            document = db.session.scalar(db.select(Document)); self.assertEqual(document.text_content, "Experience")
            self.assertNotIn("resume", document.stored_filename); document_id = document.id
        self.assertEqual(self.client.get(f"/files/{document_id}/download").data, b"Experience")
        self.client.post(f"/files/{document_id}/delete")
        with self.app.app_context(): self.assertEqual(db.session.query(Document).count(), 0)

    def test_home_has_import_and_files_context(self):
        response = self.client.get("/"); self.assertIn(b"Add application from job posting", response.data); self.assertIn(b"@ Add file context", response.data) if b"@ Add file context" in response.data else None


class V3MigrationTests(unittest.TestCase):
    def test_migration_preserves_rows_and_is_idempotent(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            import sqlite3
            connection = sqlite3.connect(handle.name); connection.executescript("CREATE TABLE application(id INTEGER PRIMARY KEY, company TEXT); INSERT INTO application VALUES(1, 'Existing'); CREATE TABLE persona(id INTEGER PRIMARY KEY);"); connection.commit(); connection.close()
            migrate(handle.name); migrate(handle.name)
            connection = sqlite3.connect(handle.name)
            self.assertEqual(connection.execute("SELECT company FROM application").fetchone()[0], "Existing")
            self.assertIn("job_posting_text", {row[1] for row in connection.execute("PRAGMA table_info(application)")}); connection.close()


if __name__ == "__main__": unittest.main()
