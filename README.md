# Job Tracker V2

A compact, server-rendered Flask career command center. **Application** remains the central object: Pathway and Persona each have many Applications, while an Application has many Contacts and Activity records and at most one current Next Action.

## V2 workflow

- `/` is the daily dashboard: **Ask Anything**, deterministic **Needs Attention**, and **Recent Activity**.
- `/applications` is the searchable and filterable pipeline; detail pages put the next action first.
- `/activity` provides filterable history. Application creation, status/action changes, action completion, and meaningful contact changes are recorded.
- Attention prioritizes overdue/today/upcoming actions, interview preparation, follow-ups, missing contacts, then applications inactive for 14 days. Offer, Rejected, Withdrawn, and Closed applications are excluded from the stale rule.

AI is read-only and backend-only. It sends a limited summary of recent tracker data to the selected provider; it never modifies the database. Configure one or both providers (the app remains usable without either):

```bash
export OPENAI_API_KEY="..."       # optional
export GEMINI_API_KEY="..."       # optional
export DEFAULT_AI_PROVIDER=openai # openai or gemini
export SECRET_KEY="a-long-random-value"
```

Optional `OPENAI_MODEL` and `GEMINI_MODEL` variables override the lightweight defaults. Keys are never rendered into browser JavaScript.

## Local development

Python 3.10 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Fresh databases are created and reference data is seeded idempotently. Existing databases must be migrated before the upgraded app starts.

## Safe V2 migration

**Back up the live SQLite file first.** Choose a new backup filename; the commands do not overwrite one automatically.

```bash
cp instance/job_tracker.db instance/job_tracker.pre-v2.db
python migrations/migrate_v2.py instance/job_tracker.db
```

The migration checks existing columns, adds only the three nullable Next Action columns, creates the Activity table and indexes if absent, and is safe to rerun. It does not delete or recreate existing tables or rows.

## Tests and production upgrade

```bash
python -m unittest discover -s tests -v
python -m compileall .
git diff --check
```

Recommended deployment order:

```bash
cd /opt/job-tracker
cp instance/job_tracker.db instance/job_tracker.pre-v2.db
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
python migrations/migrate_v2.py instance/job_tracker.db
python -m unittest discover -s tests -v
systemctl restart job-tracker
```

Gunicorn remains supported with `gunicorn --workers 2 --bind 127.0.0.1:8000 app:app`. Preserve the `instance/` directory across deployments and never commit databases, `.env` files, logs, or virtual environments.

## Job Tracker V3

V3 adds a confirmation-first posting intake, a unified Files library, and versioned PDF cover letters while retaining the V2 operational workflow. Paste a posting on Home, select OpenAI or Gemini, review every extracted field and suggested Pathway/Persona, optionally set the existing Next Action and select cover-letter source Documents, then explicitly confirm. Extraction stores a server-side draft and cannot create an Application. The confirmed Application retains the raw posting.

### Files, AI context, and cover letters

`/files` accepts PDF, DOCX, TXT, and Markdown uploads up to 10 MB. Binaries use UUID filenames under `instance/files/uploads`; generated PDFs live under `instance/files/generated`. SQLite contains metadata and extracted text, not binaries. PDFs use embedded-text extraction only (no OCR). Ask Anything includes only Documents explicitly checked under **@ Add file context**, with per-document and total context limits.

Generated letters use the posting, Application details, explicitly selected source Documents, and optional instructions. They are normal Documents linked to the Application, retain normalized source provenance, and are never overwritten by a later version. Generated text can be edited and its PDF rebuilt without AI. Configure the optional sender header at `/profile`. Provider failures do not remove an already-confirmed Application.

### Safe V3 production upgrade and backup

Back up both persistent state types before pulling. The migration only adds a nullable Application column and creates missing V3 tables/indexes; it is safe to rerun and never deletes V1/V2 rows.

```bash
cd /opt/job-tracker
mkdir -p /opt/backups
cp instance/job_tracker.db instance/job_tracker.pre-v3.db
tar -czf /opt/backups/job-tracker-files-pre-v3.tar.gz instance/files/ 2>/dev/null || true
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
python migrations/migrate_v3.py instance/job_tracker.db
python -m unittest discover -s tests -v
systemctl restart job-tracker
```

Keep `instance/` persistent across Git pulls, Gunicorn restarts, and reboots. The existing environment variables remain unchanged: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEFAULT_AI_PROVIDER`, `OPENAI_MODEL`, `GEMINI_MODEL`, and `SECRET_KEY`. AI keys stay on the Flask backend. Gunicorn remains supported with `gunicorn --workers 2 --bind 127.0.0.1:8000 app:app`.

## Job Tracker V3.1 activity privacy

V3.1 keeps `/activity` as the private, filterable operational history while removing cover-letter generation and PDF-edit events from normal Activity feeds, Application timelines, Home, and generic Ask Anything context. Existing rows are retained; this is an application-level visibility change and requires no migration. Imported and manually entered Applications now use the same user-facing creation wording based on the final saved role title.

`/public` is a standalone, read-only **Public Activity** page for sharing selected progress. Its explicit public allowlist is `application_created`, `application_imported`, `status_changed`, and `next_action_completed`; all unknown and future event types remain private until deliberately reviewed and added. Public descriptions are sanitized: creation uses current Application data, and next-action completion never includes the task text. The page does not expose contacts, outreach, documents, notes, postings, or links to private Application pages. Its `noindex,nofollow` directive discourages ordinary indexing but is not access control.

### Nginx Basic Authentication exemption

Flask routing alone does not bypass production Basic Authentication. Exempt **only** the exact public URL before the protected general location:

```nginx
location = /public {
    auth_basic off;

    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location / {
    auth_basic "Job Tracker";
    auth_basic_user_file /etc/nginx/.job-tracker-htpasswd;

    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

The public template contains its small stylesheet inline, so no static asset exemption is needed. Validate and then reload Nginx:

```bash
nginx -t
systemctl reload nginx
```

> **Warning:** Do not remove Basic Authentication from the general `location /` block. Only `/public` and any strictly necessary public presentation assets should be exempted.
