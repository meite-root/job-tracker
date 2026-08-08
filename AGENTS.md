# Contributor guidance

This is a lightweight Flask application. Keep `Application` as the central domain object.

Relationships:
- Pathway 1:N Application
- Persona 1:N Application
- Application 1:N Contact

Do not commit SQLite databases, virtual environments, secrets, or logs. Prefer simple Flask, Jinja, and SQLAlchemy solutions; avoid unnecessary frontend frameworks or infrastructure. Maintain the compact, GitHub-inspired visual style.

Before completing changes, verify the app imports successfully, run basic syntax checks and tests, inspect the Git diff, and ensure database files were not added.
