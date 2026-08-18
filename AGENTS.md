# Contributor guidance

This is a lightweight Flask application. Keep `Application` as the central domain object.

Relationships:
- Pathway 1:N Application
- Persona 1:N Application
- Application 1:N Contact
- Application 1:N Activity
- Application 1:N Document
- Generated Document N:N source Document (provenance)

An Application has at most one current Next Action. The dashboard exists to provide Ask Anything, Needs Attention, and Recent Activity.

AI extraction creates server-side drafts, never Applications. Only explicit confirmation creates an imported Application. Preserve raw job postings. Uploaded and generated career materials are Documents; generated cover letters belong to Applications. Never fabricate career facts, and include only explicitly selected Documents in AI context. Preserve V1/V2 data with safe, idempotent migrations. Do not commit uploaded or generated files.

Never destroy existing SQLite data; use migrations for schema changes. Do not commit database files or API keys. Keep AI calls backend-only and attention logic rule-based. Keep the UI GitHub-inspired and minimal, and avoid unnecessary infrastructure.

Do not commit SQLite databases, virtual environments, secrets, or logs. Prefer simple Flask, Jinja, and SQLAlchemy solutions; avoid unnecessary frontend frameworks or infrastructure. Maintain the compact, GitHub-inspired visual style.

Before completing changes, verify the app imports successfully, run basic syntax checks and tests, inspect the Git diff, and ensure database files were not added.
