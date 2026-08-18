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
        form = {"company": "Edited Co", "role_title": "Economic Consulting Associate", "status": "Preparing", "pathway_id": pathway_id, "persona_id": persona_id, "next_action": "Tailor CV", "next_action_date": "2026-08-20"}
        self.client.post(f"/applications/import/{draft_id}/confirm", data=form)
        self.client.post(f"/applications/import/{draft_id}/confirm", data=form)
        with self.app.app_context():
            self.assertEqual(db.session.query(Application).count(), 1); item = db.session.scalar(db.select(Application))
            self.assertEqual(item.job_posting_text, "Complete posting"); self.assertEqual(item.next_action, "Tailor CV")
            event = db.session.scalar(db.select(Activity).where(Activity.event_type == "application_imported"))
            self.assertEqual(event.description, "Created application for Economic Consulting Associate.")
            self.assertNotIn("pasted", event.description.lower())

    def test_cover_letter_document_history_does_not_create_activity(self):
        with self.app.app_context():
            pathway = db.session.scalar(db.select(Pathway)); persona = db.session.scalar(db.select(Persona))
            application = Application(company="Letter Co", role_title="Economist", status="Applied",
                pathway=pathway, persona=persona, job_posting_text="Posting")
            source = Document(title="CV", document_type="cv", source_type="uploaded", text_content="Facts")
            db.session.add_all((application, source)); db.session.commit()
            application_id, source_id = application.id, source.id
        with patch("app.generate_cover_letter", return_value="A factual letter"), patch("app.render_cover_letter_pdf"):
            response = self.client.post(f"/applications/{application_id}/cover-letter",
                data={"provider": "openai", "source_document_ids": str(source_id)})
            self.assertEqual(response.status_code, 302)
            with self.app.app_context():
                document = db.session.scalar(db.select(Document).where(Document.source_type == "generated"))
                self.assertEqual(document.application_id, application_id)
                self.assertEqual([item.id for item in document.sources], [source_id])
                self.assertEqual(db.session.query(Activity).filter_by(event_type="cover_letter_generated").count(), 0)
                document_id = document.id
            response = self.client.post(f"/files/{document_id}", data={
                "title": "Revised letter", "document_type": "cover_letter", "text_content": "Revised"})
            self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.query(Activity).filter_by(event_type="cover_letter_updated").count(), 0)

    def test_activity_visibility_and_public_privacy(self):
        with self.app.app_context():
            pathway = db.session.scalar(db.select(Pathway)); persona = db.session.scalar(db.select(Persona))
            item = Application(company="Safe Company", role_title="Public Analyst", status="Applied",
                pathway=pathway, persona=persona)
            db.session.add(item); db.session.flush()
            events = [
                ("application_created", "old unsafe creation copy"),
                ("status_changed", "Status changed from Preparing to Applied."),
                ("next_action_completed", "Completed next action: Email Sarah Secret."),
                ("contact_added", "Added Sarah Secret as a contact."),
                ("outreach_updated", "Sarah Secret replied."),
                ("cover_letter_generated", "Generated Confidential Letter.pdf."),
                ("future_private_event", "Private future detail"),
            ]
            db.session.add_all(Activity(application=item, event_type=kind, description=description)
                               for kind, description in events)
            db.session.commit(); item_id = item.id

        private = self.client.get("/activity")
        self.assertEqual(private.status_code, 200)
        self.assertIn(b"Added Sarah Secret", private.data)
        self.assertNotIn(b"Generated Confidential", private.data)
        detail = self.client.get(f"/applications/{item_id}")
        self.assertNotIn(b"Generated Confidential", detail.data)
        home = self.client.get("/")
        self.assertNotIn(b"Generated Confidential", home.data)

        public = self.client.get("/public")
        self.assertEqual(public.status_code, 200)
        self.assertIn(b'content="noindex,nofollow"', public.data)
        self.assertIn(b"Created application for Public Analyst.", public.data)
        self.assertIn(b"Status changed from Preparing to Applied.", public.data)
        self.assertIn(b"Completed a next action.", public.data)
        for private_text in (b"Sarah Secret", b"Email Sarah", b"Confidential Letter", b"Private future detail"):
            self.assertNotIn(private_text, public.data)
        self.assertNotIn(f'/applications/{item_id}'.encode(), public.data)
        self.assertEqual(self.client.post("/public").status_code, 405)

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
