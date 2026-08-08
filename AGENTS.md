# Contributor guidance

This is a lightweight Flask application. Keep `Application` as the central domain object.

Relationships:
- Pathway 1:N Application
- Persona 1:N Application
- Application 1:N Contact
- Application 1:N Activity

An Application has at most one current Next Action. The dashboard exists to provide Ask Anything, Needs Attention, and Recent Activity.

Never destroy existing SQLite data; use migrations for schema changes. Do not commit database files or API keys. Keep AI calls backend-only and attention logic rule-based. Keep the UI GitHub-inspired and minimal, and avoid unnecessary infrastructure.

Do not commit SQLite databases, virtual environments, secrets, or logs. Prefer simple Flask, Jinja, and SQLAlchemy solutions; avoid unnecessary frontend frameworks or infrastructure. Maintain the compact, GitHub-inspired visual style.

Before completing changes, verify the app imports successfully, run basic syntax checks and tests, inspect the Git diff, and ensure database files were not added.
