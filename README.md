# Job Tracker

A compact personal operations tool for tracking job applications and the outreach attached to each pursuit. The server-rendered interface uses Flask, SQLAlchemy, Jinja, SQLite, and custom CSS, with no frontend build step.

## Domain model

`Application` is the central transactional object:

- Pathway **1:N** Application
- Persona **1:N** Application
- Application **1:N** Contact

Every application requires one pathway and one persona. Contacts are subordinate records and are deleted with their parent application. Pathways and personas are editable database records rather than application enums.

## Local setup

Python 3.10 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. The database is created automatically at `instance/job_tracker.db`. On startup, the app safely inserts the three initial personas and four pathways when missing; applications and contacts are never seeded. The `instance` database is ignored by Git, so deployments should preserve this directory.

Run the checks with:

```bash
python -m unittest discover -s tests
python -m compileall app.py tests
```

## Production

Set a strong, persistent secret and run behind a reverse proxy:

```bash
export SECRET_KEY="replace-with-a-long-random-value"
gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```

On a small Ubuntu host, use a dedicated virtual environment and a `systemd` service for Gunicorn, terminate TLS through Nginx or Caddy, restrict filesystem permissions, and back up `instance/job_tracker.db`. Deploy code without replacing the `instance/` directory. Schema migrations are intentionally outside this initial version; back up the database before future schema changes.
