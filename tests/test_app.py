import tempfile
import unittest

from app import Activity, Application, Contact, Pathway, Persona, create_app, db


class JobTrackerTestCase(unittest.TestCase):
    def setUp(self):
        self.database = tempfile.NamedTemporaryFile(suffix=".db")
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.database.name}", "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
        self.database.close()

    def test_seed_is_idempotent_and_pages_render(self):
        with self.app.app_context():
            self.assertEqual(db.session.query(Persona).count(), 3)
            self.assertEqual(db.session.query(Pathway).count(), 4)
        for url in ("/", "/applications", "/activity", "/pathways", "/personas", "/contacts", "/applications/new"):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_application_contact_workflow_and_cascade(self):
        with self.app.app_context():
            pathway_id = db.session.query(Pathway.id).first()[0]
            persona_id = db.session.query(Persona.id).first()[0]
        response = self.client.post("/applications/new", data={
            "company": "Example Research", "role_title": "Economist", "pathway_id": pathway_id,
            "persona_id": persona_id, "status": "Applied", "date_applied": "2026-08-08",
        }, follow_redirects=True)
        self.assertIn(b"Example Research", response.data)
        with self.app.app_context():
            application_id = db.session.query(Application.id).scalar()
        self.client.post(f"/applications/{application_id}/contacts", data={"name": "Alex Doe", "outreach_status": "Outreach Sent"})
        with self.app.app_context():
            self.assertEqual(db.session.query(Contact).count(), 1)
            self.assertTrue(db.session.query(Activity).filter_by(event_type="contact_added").first())
        self.client.post(f"/applications/{application_id}/delete")
        with self.app.app_context():
            self.assertEqual(db.session.query(Application).count(), 0)
            self.assertEqual(db.session.query(Contact).count(), 0)

    def test_next_action_completion_status_activity_and_missing_ai_key(self):
        with self.app.app_context():
            pathway_id = db.session.query(Pathway.id).first()[0]; persona_id = db.session.query(Persona.id).first()[0]
        self.client.post("/applications/new", data={"company":"Action Co", "role_title":"Analyst", "pathway_id":pathway_id,
            "persona_id":persona_id, "status":"Applied", "next_action":"Follow up", "next_action_date":"2026-08-08"})
        with self.app.app_context(): application_id = db.session.query(Application.id).scalar()
        response = self.client.get("/"); self.assertIn(b"Follow up", response.data)
        self.client.post(f"/applications/{application_id}/next-action/complete")
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Application, application_id).next_action_completed_at)
            self.assertTrue(db.session.query(Activity).filter_by(event_type="next_action_completed").first())
        self.client.post(f"/applications/{application_id}/edit", data={"company":"Action Co", "role_title":"Analyst", "pathway_id":pathway_id,
            "persona_id":persona_id, "status":"Interview"})
        with self.app.app_context(): self.assertTrue(db.session.query(Activity).filter_by(event_type="status_changed").first())
        self.assertEqual(self.client.post("/ask", data={"provider":"openai", "message":"What next?"}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
