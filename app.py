import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_

from services.ai import AIServiceError, ask_ai, extract_application_from_posting, generate_cover_letter
from services.documents import extract_text, render_cover_letter_pdf

db = SQLAlchemy()

APPLICATION_STATUSES = (
    "Interested", "Preparing", "Applied", "Networking", "Assessment", "Interview",
    "Final Round", "Offer", "Rejected", "Withdrawn", "Closed",
)
OUTREACH_STATUSES = (
    "Not Contacted", "Outreach Sent", "Connected", "Replied", "Follow-up Needed",
    "Conversation", "No Response",
)
HIDDEN_ACTIVITY_EVENT_TYPES = frozenset({"cover_letter_generated", "cover_letter_updated"})
PUBLIC_ACTIVITY_EVENT_TYPES = frozenset({
    "application_created", "application_imported", "status_changed", "next_action_completed",
})


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Pathway(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    short_name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, default="")
    geography = db.Column(db.String(180), default="")
    notes = db.Column(db.Text, default="")
    color = db.Column(db.String(7), default="#656d76")
    active = db.Column(db.Boolean, default=True, nullable=False)
    applications = db.relationship("Application", back_populates="pathway", lazy="dynamic")


class Persona(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    short_name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, default="")
    color = db.Column(db.String(7), default="#656d76")
    active = db.Column(db.Boolean, default=True, nullable=False)
    applications = db.relationship("Application", back_populates="persona", lazy="dynamic")


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(160), nullable=False, index=True)
    role_title = db.Column(db.String(160), nullable=False, index=True)
    job_url = db.Column(db.String(500), default="")
    location = db.Column(db.String(160), default="")
    pathway_id = db.Column(db.Integer, db.ForeignKey("pathway.id"), nullable=False)
    persona_id = db.Column(db.Integer, db.ForeignKey("persona.id"), nullable=False)
    date_applied = db.Column(db.Date)
    status = db.Column(db.String(40), default="Interested", nullable=False)
    notes = db.Column(db.Text, default="")
    job_posting_text = db.Column(db.Text)
    next_action = db.Column(db.Text)
    next_action_date = db.Column(db.Date)
    next_action_completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    pathway = db.relationship("Pathway", back_populates="applications")
    persona = db.relationship("Persona", back_populates="applications")
    contacts = db.relationship("Contact", back_populates="application", cascade="all, delete-orphan", lazy="selectin")
    activities = db.relationship("Activity", back_populates="application", cascade="all, delete-orphan", lazy="selectin")
    documents = db.relationship("Document", back_populates="application", cascade="all, delete-orphan", lazy="selectin")


class ApplicationImportDraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    raw_job_posting = db.Column(db.Text, nullable=False)
    draft_data = db.Column(db.Text, nullable=False, default="{}")
    provider = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    confirmed_at = db.Column(db.DateTime)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"))


document_source = db.Table("document_source",
    db.Column("generated_document_id", db.Integer, db.ForeignKey("document.id", ondelete="CASCADE"), primary_key=True),
    db.Column("source_document_id", db.Integer, db.ForeignKey("document.id", ondelete="CASCADE"), primary_key=True))


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    document_type = db.Column(db.String(30), nullable=False, index=True)
    source_type = db.Column(db.String(20), nullable=False)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"), index=True)
    persona_id = db.Column(db.Integer, db.ForeignKey("persona.id"))
    original_filename = db.Column(db.String(255))
    stored_filename = db.Column(db.String(80))
    mime_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer)
    text_content = db.Column(db.Text)
    notes = db.Column(db.Text, default="")
    provider = db.Column(db.String(20))
    model_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    application = db.relationship("Application", back_populates="documents")
    persona = db.relationship("Persona")
    sources = db.relationship("Document", secondary=document_source,
        primaryjoin=id == document_source.c.generated_document_id,
        secondaryjoin=id == document_source.c.source_document_id)


class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True, default=1)
    full_name = db.Column(db.String(160), default="")
    location = db.Column(db.String(160), default="")
    email = db.Column(db.String(254), default="")
    phone = db.Column(db.String(80), default="")
    linkedin_url = db.Column(db.String(500), default="")


class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    title = db.Column(db.String(160), default="")
    organization = db.Column(db.String(160), default="")
    linkedin_url = db.Column(db.String(500), default="")
    email = db.Column(db.String(254), default="")
    outreach_date = db.Column(db.Date)
    outreach_status = db.Column(db.String(40), default="Not Contacted", nullable=False)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    application = db.relationship("Application", back_populates="contacts")


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"), nullable=False, index=True)
    contact_id = db.Column(db.Integer, nullable=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    application = db.relationship("Application", back_populates="activities")


def record_activity(application, event_type, description, contact_id=None):
    db.session.add(Activity(application=application, contact_id=contact_id,
                            event_type=event_type, description=description))


def visible_activity_query():
    """Return the shared internal Activity feed policy."""
    return db.select(Activity).where(Activity.event_type.not_in(HIDDEN_ACTIVITY_EVENT_TYPES))


def public_activity_query():
    """Return only events deliberately approved for public display."""
    return db.select(Activity).where(Activity.event_type.in_(PUBLIC_ACTIVITY_EVENT_TYPES))


def public_activity_description(activity):
    """Build public copy without exposing operational descriptions by default."""
    if activity.event_type in {"application_created", "application_imported"}:
        return f"Created application for {activity.application.role_title}."
    if activity.event_type == "next_action_completed":
        return "Completed a next action."
    if activity.event_type == "status_changed":
        return activity.description
    raise ValueError("Activity event type is not public")


def attention_items(applications, today=None):
    today = today or date.today()
    terminal = {"Offer", "Rejected", "Withdrawn", "Closed"}
    items = []
    for application in applications:
        current_action = application.next_action and not application.next_action_completed_at
        if current_action:
            due = application.next_action_date
            rank = 0 if due and due < today else 1 if due == today else 2
            items.append({"kind": "action", "rank": rank, "application": application,
                          "text": application.next_action, "due": due})
        if application.status in {"Interview", "Final Round"} and not current_action:
            items.append({"kind": "suggestion", "rank": 3, "application": application,
                          "text": "Interviewing with no next action scheduled. Add a preparation task."})
        for contact in application.contacts:
            if contact.outreach_status == "Follow-up Needed":
                suffix = f" Last outreach was {(today-contact.outreach_date).days} days ago." if contact.outreach_date else ""
                items.append({"kind": "suggestion", "rank": 4, "application": application,
                              "text": f"Follow up with {contact.name}.{suffix}"})
        age = (today - (application.date_applied or application.created_at.date())).days
        if application.status == "Applied" and age >= 7 and not application.contacts:
            items.append({"kind": "suggestion", "rank": 5, "application": application,
                          "text": f"Applied {age} days ago with no outreach contacts. Add a contact."})
        elif application.status == "Networking" and not application.contacts:
            items.append({"kind": "suggestion", "rank": 5, "application": application,
                          "text": "Networking application has no contacts. Add a contact."})
        stale = (today - application.updated_at.date()).days
        if application.status not in terminal and stale >= 14:
            items.append({"kind": "suggestion", "rank": 6, "application": application,
                          "text": f"No activity for {stale} days. Review this application."})
    return sorted(items, key=lambda x: (x["rank"], x.get("due") or date.max, x["application"].company.lower()))


def tracker_context(limit=30):
    applications = db.session.scalars(db.select(Application).order_by(Application.updated_at.desc()).limit(limit)).all()
    lines = []
    for item in applications:
        contacts = ", ".join(f"{c.name} ({c.outreach_status})" for c in item.contacts) or "none"
        lines.append(f"{item.company} — {item.role_title}; status={item.status}; pathway={item.pathway.short_name}; "
                     f"persona={item.persona.short_name}; next action={item.next_action or 'none'}; "
                     f"due={item.next_action_date or 'none'}; contacts={contacts}; updated={item.updated_at.date()}")
    recent = db.session.scalars(visible_activity_query().order_by(Activity.created_at.desc()).limit(10)).all()
    return "Applications:\n" + "\n".join(lines) + "\nRecent activity:\n" + "\n".join(a.description for a in recent)


PERSONA_SEEDS = [
    ("Data Science / Economic Consulting", "Data / Econ", "Python, R, SQL, quantitative analysis, econometrics, GIS, data pipelines, automation, and empirical research.", "#0969da"),
    ("Development / Public Policy", "Development", "Field research, development economics, spatial econometrics, survey data, policy research, and Africa-focused empirical work.", "#8250df"),
    ("Sovereign Risk / Finance", "Risk / Finance", "Sovereign risk, macroeconomic analysis, financial modeling, country risk, capital flows, debt, and ESG analysis.", "#9a6700"),
]
PATHWAY_SEEDS = [
    ("GCC", "GCC", "Economic advisory, sovereign wealth funds, strategy consulting, infrastructure, energy, and financial analysis.", "UAE · Saudi Arabia · Qatar", "#1a7f37"),
    ("Cap-Exempt United States", "US / Cap Exempt", "Universities, nonprofit research organizations, think tanks, and policy institutions.", "United States", "#0969da"),
    ("Multilateral / International Development", "Multilateral", "International organizations, development finance, policy, and economic research.", "International", "#8250df"),
    ("UK / Western Europe", "UK / Europe", "Economic consulting, policy research, infrastructure analytics, ESG, and quantitative economics.", "United Kingdom · Western Europe", "#9a6700"),
]


def seed_reference_data():
    changed = False
    for name, short, description, color in PERSONA_SEEDS:
        if not db.session.scalar(db.select(Persona).filter_by(name=name)):
            db.session.add(Persona(name=name, short_name=short, description=description, color=color)); changed = True
    for name, short, description, geography, color in PATHWAY_SEEDS:
        if not db.session.scalar(db.select(Pathway).filter_by(name=name)):
            db.session.add(Pathway(name=name, short_name=short, description=description, geography=geography, color=color)); changed = True
    if changed:
        db.session.commit()


def parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def populate_application(item):
    item.company = request.form.get("company", "").strip()
    item.role_title = request.form.get("role_title", "").strip()
    item.location = request.form.get("location", "").strip()
    item.job_url = request.form.get("job_url", "").strip()
    item.date_applied = parse_date(request.form.get("date_applied"))
    item.notes = request.form.get("notes", "").strip()
    item.status = request.form.get("status", "Interested")
    item.pathway_id = request.form.get("pathway_id", type=int)
    item.persona_id = request.form.get("persona_id", type=int)
    item.next_action = request.form.get("next_action", "").strip() or None
    item.next_action_date = parse_date(request.form.get("next_action_date"))
    return bool(item.company and item.role_title and item.pathway_id and item.persona_id and item.status in APPLICATION_STATUSES)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI="sqlite:///job_tracker.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    files_root = Path(app.instance_path) / "files"
    upload_root, generated_root = files_root / "uploads", files_root / "generated"
    upload_root.mkdir(parents=True, exist_ok=True); generated_root.mkdir(parents=True, exist_ok=True)

    def library_documents():
        return db.session.scalars(db.select(Document).order_by(Document.created_at.desc())).all()

    def generate_document(application, provider, source_ids, instructions=""):
        sources = db.session.scalars(db.select(Document).where(Document.id.in_(source_ids))).all() if source_ids else []
        letter = generate_cover_letter(provider, application, application.job_posting_text or "", sources, instructions)
        stored = f"{uuid.uuid4().hex}.pdf"
        profile = db.session.get(Profile, 1) or Profile(id=1)
        render_cover_letter_pdf(generated_root / stored, letter, application, profile)
        document = Document(title=f"Cover Letter — {application.company} — {application.role_title}",
            document_type="cover_letter", source_type="generated", application=application,
            stored_filename=stored, mime_type="application/pdf", text_content=letter,
            provider=provider, model_name=os.environ.get(f"{provider.upper()}_MODEL"), sources=sources)
        db.session.add(document); db.session.flush()
        db.session.commit()
        return document

    @app.get("/")
    def dashboard():
        applications = db.session.scalars(db.select(Application).order_by(Application.updated_at.desc())).all()
        recent = db.session.scalars(visible_activity_query().order_by(Activity.created_at.desc()).limit(10)).all()
        return render_template("dashboard.html", attention=attention_items(applications), recent=recent,
                               default_provider=os.environ.get("DEFAULT_AI_PROVIDER", "openai").lower(), documents=library_documents())

    @app.post("/ask")
    def ask():
        message = request.form.get("message", "").strip()
        provider = request.form.get("provider", "openai").lower()
        if not message:
            flash("Enter a question first.", "error")
            return redirect(url_for("dashboard"))
        try:
            ids = list(dict.fromkeys(request.form.getlist("document_ids", type=int)))[:10]
            documents = db.session.scalars(db.select(Document).where(Document.id.in_(ids))).all() if ids else []
            extra, total = [], 0
            for document in documents:
                content = (document.text_content or "")[:12000]; remaining = 30000 - total
                if remaining <= 0: break
                content = content[:remaining]; total += len(content)
                extra.append(f"Selected document: {document.title}\n{content}" + ("\n[truncated]" if len(document.text_content or "") > len(content) else ""))
            answer = ask_ai(provider, message, tracker_context() + ("\n\n" + "\n\n".join(extra) if extra else ""))
            return render_template("dashboard.html", attention=attention_items(db.session.scalars(db.select(Application)).all()),
                recent=db.session.scalars(visible_activity_query().order_by(Activity.created_at.desc()).limit(10)).all(),
                default_provider=provider, ai_answer=answer, asked_message=message, documents=library_documents(), selected_document_ids=ids)
        except AIServiceError as error:
            return render_template("dashboard.html", attention=attention_items(db.session.scalars(db.select(Application)).all()),
                recent=db.session.scalars(visible_activity_query().order_by(Activity.created_at.desc()).limit(10)).all(),
                default_provider=provider, ai_error=str(error), asked_message=message, documents=library_documents()), 503

    @app.post("/applications/import")
    def application_import():
        posting = request.form.get("posting_text", "").strip(); provider = request.form.get("provider", "openai").lower()
        if not posting:
            flash("Paste a job posting first.", "error"); return redirect(url_for("dashboard"))
        pathways = db.session.scalars(db.select(Pathway).where(Pathway.active.is_(True))).all()
        personas = db.session.scalars(db.select(Persona).where(Persona.active.is_(True))).all()
        try: data = extract_application_from_posting(provider, posting, pathways, personas)
        except AIServiceError as error:
            flash(str(error), "error"); return redirect(url_for("dashboard"))
        draft = ApplicationImportDraft(raw_job_posting=posting, draft_data=json.dumps(data), provider=provider)
        db.session.add(draft); db.session.commit()
        return redirect(url_for("application_import_review", draft_id=draft.id))

    @app.get("/applications/import/<int:draft_id>/review")
    def application_import_review(draft_id):
        draft = db.get_or_404(ApplicationImportDraft, draft_id)
        if draft.confirmed_at and draft.application_id: return redirect(url_for("application_detail", item_id=draft.application_id))
        data = json.loads(draft.draft_data); duplicate = None
        if data.get("company") and data.get("role_title"):
            duplicate = db.session.scalar(db.select(Application).where(
                db.func.lower(Application.company) == data["company"].lower(),
                db.func.lower(Application.role_title) == data["role_title"].lower()))
        return render_template("application_import_review.html", draft=draft, data=data, duplicate=duplicate,
            statuses=APPLICATION_STATUSES, pathways=db.session.scalars(db.select(Pathway).order_by(Pathway.name)).all(),
            personas=db.session.scalars(db.select(Persona).order_by(Persona.name)).all(), documents=library_documents())

    @app.post("/applications/import/<int:draft_id>/confirm")
    def application_import_confirm(draft_id):
        draft = db.get_or_404(ApplicationImportDraft, draft_id)
        if draft.confirmed_at and draft.application_id: return redirect(url_for("application_detail", item_id=draft.application_id))
        item = Application(job_posting_text=draft.raw_job_posting)
        if not populate_application(item):
            flash("Company, role, pathway, and persona are required.", "error"); return redirect(url_for("application_import_review", draft_id=draft.id))
        # IDs are accepted only when they resolve to existing reference rows.
        if not db.session.get(Pathway, item.pathway_id) or not db.session.get(Persona, item.persona_id):
            flash("Choose an existing pathway and persona.", "error"); return redirect(url_for("application_import_review", draft_id=draft.id))
        db.session.add(item); db.session.flush(); draft.application_id = item.id; draft.confirmed_at = utcnow()
        record_activity(item, "application_imported", f"Created application for {item.role_title}.")
        db.session.commit()
        if request.form.get("generate_cover_letter"):
            try: generate_document(item, draft.provider, request.form.getlist("source_document_ids", type=int), request.form.get("cover_letter_instructions", ""))
            except (AIServiceError, OSError, ValueError):
                db.session.rollback(); flash("Application created successfully. Cover letter generation failed. You can retry from the Application page.", "error")
        else: flash("Application created successfully.", "success")
        return redirect(url_for("application_detail", item_id=item.id))

    @app.get("/applications")
    def applications():
        query = db.select(Application)
        search = request.args.get("q", "").strip()
        status = request.args.get("status", "")
        pathway_id = request.args.get("pathway", type=int)
        persona_id = request.args.get("persona", type=int)
        if search:
            query = query.where(or_(Application.company.ilike(f"%{search}%"), Application.role_title.ilike(f"%{search}%")))
        if status in APPLICATION_STATUSES: query = query.where(Application.status == status)
        if pathway_id: query = query.where(Application.pathway_id == pathway_id)
        if persona_id: query = query.where(Application.persona_id == persona_id)
        items = db.session.scalars(query.order_by(Application.created_at.desc())).all()
        counts = {"all": db.session.scalar(db.select(db.func.count(Application.id))),
                  "interview": db.session.scalar(db.select(db.func.count(Application.id)).where(Application.status.in_(("Interview", "Final Round")))),
                  "networking": db.session.scalar(db.select(db.func.count(Application.id)).where(Application.status == "Networking")),
                  "offer": db.session.scalar(db.select(db.func.count(Application.id)).where(Application.status == "Offer"))}
        return render_template("applications.html", applications=items, counts=counts, statuses=APPLICATION_STATUSES,
                               pathways=db.session.scalars(db.select(Pathway).order_by(Pathway.name)).all(),
                               personas=db.session.scalars(db.select(Persona).order_by(Persona.name)).all())

    @app.route("/applications/new", methods=("GET", "POST"))
    @app.route("/applications/<int:item_id>/edit", methods=("GET", "POST"))
    def application_form(item_id=None):
        item = db.get_or_404(Application, item_id) if item_id else Application()
        if request.method == "POST":
            is_new, old_status, old_action = item.id is None, item.status, item.next_action
            if populate_application(item):
                db.session.add(item); db.session.flush()
                if is_new: record_activity(item, "application_created", f"Created application for {item.role_title}.")
                elif old_status != item.status: record_activity(item, "status_changed", f"Status changed from {old_status} to {item.status}.")
                if item.next_action and item.next_action != old_action:
                    item.next_action_completed_at = None
                    record_activity(item, "next_action_created" if not old_action else "next_action_updated",
                                    f"{'Added' if not old_action else 'Updated'} next action: {item.next_action}.")
                db.session.commit()
                flash("Application saved.", "success")
                return redirect(url_for("application_detail", item_id=item.id))
            flash("Company, role, pathway, and persona are required.", "error")
        return render_template("application_form.html", item=item, statuses=APPLICATION_STATUSES,
            pathways=db.session.scalars(db.select(Pathway).order_by(Pathway.name)).all(),
            personas=db.session.scalars(db.select(Persona).order_by(Persona.name)).all())

    @app.get("/applications/<int:item_id>")
    def application_detail(item_id):
        item = db.get_or_404(Application, item_id)
        activities = db.session.scalars(visible_activity_query().where(
            Activity.application_id == item.id).order_by(Activity.created_at.desc()).limit(8)).all()
        return render_template("application_detail.html", item=item, activities=activities,
            outreach_statuses=OUTREACH_STATUSES, documents=library_documents())

    @app.post("/applications/<int:item_id>/cover-letter")
    def application_cover_letter(item_id):
        item = db.get_or_404(Application, item_id)
        try:
            generate_document(item, request.form.get("provider", "openai"),
                request.form.getlist("source_document_ids", type=int), request.form.get("instructions", ""))
            flash("Cover letter generated.", "success")
        except (AIServiceError, OSError, ValueError) as error:
            db.session.rollback(); flash(f"Cover letter generation failed: {error}", "error")
        return redirect(url_for("application_detail", item_id=item.id))

    @app.get("/files")
    def files():
        kind = request.args.get("type", "")
        query = db.select(Document)
        if kind in {"cv", "cover_letter", "bio", "writing_sample", "other"}: query = query.where(Document.document_type == kind)
        return render_template("files.html", documents=db.session.scalars(query.order_by(Document.created_at.desc())).all(), kind=kind)

    @app.post("/files/upload")
    def file_upload():
        uploaded = request.files.get("file"); kind = request.form.get("document_type", "other")
        allowed = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                   ".txt": "text/plain", ".md": "text/markdown"}
        suffix = Path(uploaded.filename or "").suffix.lower() if uploaded else ""
        if not uploaded or suffix not in allowed or kind not in {"cv", "cover_letter", "bio", "writing_sample", "other"}:
            flash("Upload a supported PDF, DOCX, TXT, or MD file.", "error"); return redirect(url_for("files"))
        # Flask enforces MAX_CONTENT_LENGTH; this also handles clients without Content-Length.
        payload = uploaded.read(10 * 1024 * 1024 + 1)
        if len(payload) > 10 * 1024 * 1024:
            flash("Files must be 10 MB or smaller.", "error"); return redirect(url_for("files"))
        stored = f"{uuid.uuid4().hex}{suffix}"; path = upload_root / stored; path.write_bytes(payload)
        try: text_content = extract_text(path, suffix)
        except (OSError, ValueError):
            path.unlink(missing_ok=True); flash("The file could not be read.", "error"); return redirect(url_for("files"))
        document = Document(title=request.form.get("title", "").strip() or Path(uploaded.filename).stem,
            document_type=kind, source_type="uploaded", original_filename=Path(uploaded.filename).name,
            stored_filename=stored, mime_type=allowed[suffix], size_bytes=len(payload), text_content=text_content,
            notes=request.form.get("notes", "").strip())
        db.session.add(document); db.session.commit(); flash("File uploaded.", "success")
        return redirect(url_for("file_detail", document_id=document.id))

    @app.route("/files/<int:document_id>", methods=("GET", "POST"))
    def file_detail(document_id):
        document = db.get_or_404(Document, document_id)
        if request.method == "POST":
            document.title = request.form.get("title", "").strip(); kind = request.form.get("document_type", document.document_type)
            if not document.title or kind not in {"cv", "cover_letter", "bio", "writing_sample", "other"}:
                flash("Title and a valid type are required.", "error")
            else:
                document.document_type = kind; document.notes = request.form.get("notes", "").strip()
                if document.source_type == "generated":
                    document.text_content = request.form.get("text_content", "").strip()
                    render_cover_letter_pdf(generated_root / document.stored_filename, document.text_content, document.application, db.session.get(Profile, 1) or Profile())
                db.session.commit(); flash("Document updated.", "success")
                return redirect(url_for("file_detail", document_id=document.id))
        return render_template("file_detail.html", document=document)

    def document_path(document):
        root = generated_root if document.source_type == "generated" else upload_root
        candidate = root / (document.stored_filename or "")
        if not document.stored_filename or candidate.parent != root: abort(404)
        return candidate

    @app.get("/files/<int:document_id>/download")
    def file_download(document_id):
        document = db.get_or_404(Document, document_id); path = document_path(document)
        if not path.is_file(): abort(404)
        return send_file(path, mimetype=document.mime_type, as_attachment=True,
            download_name=document.original_filename or f"{document.title}.pdf")

    @app.post("/files/<int:document_id>/delete")
    def file_delete(document_id):
        document = db.get_or_404(Document, document_id); path = document_path(document)
        db.session.delete(document); db.session.commit(); path.unlink(missing_ok=True)
        flash("Document deleted.", "success"); return redirect(url_for("files"))

    @app.route("/profile", methods=("GET", "POST"))
    def profile():
        item = db.session.get(Profile, 1) or Profile(id=1)
        if request.method == "POST":
            for field in ("full_name", "location", "email", "phone", "linkedin_url"):
                setattr(item, field, request.form.get(field, "").strip())
            if not item.full_name: flash("Name is required.", "error")
            else:
                db.session.add(item); db.session.commit(); flash("Profile saved.", "success"); return redirect(url_for("files"))
        return render_template("profile.html", item=item)

    @app.post("/applications/<int:item_id>/next-action/complete")
    def next_action_complete(item_id):
        item = db.get_or_404(Application, item_id)
        if item.next_action and not item.next_action_completed_at:
            item.next_action_completed_at = utcnow()
            record_activity(item, "next_action_completed", f"Completed next action: {item.next_action}.")
            db.session.commit(); flash("Next action completed.", "success")
        return redirect(request.referrer or url_for("application_detail", item_id=item_id))

    @app.post("/applications/<int:item_id>/delete")
    def application_delete(item_id):
        item = db.get_or_404(Application, item_id); db.session.delete(item); db.session.commit()
        flash("Application and its contacts deleted.", "success")
        return redirect(url_for("applications"))

    @app.post("/applications/<int:item_id>/contacts")
    def contact_add(item_id):
        application = db.get_or_404(Application, item_id)
        name = request.form.get("name", "").strip()
        status = request.form.get("outreach_status", "Not Contacted")
        if not name or status not in OUTREACH_STATUSES:
            flash("Contact name is required.", "error")
        else:
            contact = Contact(application=application, name=name, title=request.form.get("title", "").strip(),
                organization=request.form.get("organization", "").strip(), email=request.form.get("email", "").strip(),
                linkedin_url=request.form.get("linkedin_url", "").strip(), outreach_date=parse_date(request.form.get("outreach_date")),
                outreach_status=status, notes=request.form.get("notes", "").strip())
            db.session.add(contact); db.session.flush()
            record_activity(application, "contact_added", f"Added {contact.name} as a contact.", contact.id)
            db.session.commit(); flash("Contact added.", "success")
        return redirect(url_for("application_detail", item_id=item_id))

    @app.route("/contacts/<int:contact_id>/edit", methods=("GET", "POST"))
    def contact_edit(contact_id):
        contact = db.get_or_404(Contact, contact_id)
        if request.method == "POST":
            old_status = contact.outreach_status
            contact.name = request.form.get("name", "").strip(); contact.title = request.form.get("title", "").strip()
            contact.organization = request.form.get("organization", "").strip(); contact.email = request.form.get("email", "").strip()
            contact.linkedin_url = request.form.get("linkedin_url", "").strip(); contact.outreach_date = parse_date(request.form.get("outreach_date"))
            contact.outreach_status = request.form.get("outreach_status", "Not Contacted"); contact.notes = request.form.get("notes", "").strip()
            if contact.name and contact.outreach_status in OUTREACH_STATUSES:
                if old_status != contact.outreach_status:
                    record_activity(contact.application, "outreach_updated", f"{contact.name} outreach status changed from {old_status} to {contact.outreach_status}.", contact.id)
                db.session.commit(); flash("Contact updated.", "success"); return redirect(url_for("application_detail", item_id=contact.application_id))
            flash("Contact name is required.", "error")
        return render_template("contact_form.html", contact=contact, outreach_statuses=OUTREACH_STATUSES)

    @app.post("/contacts/<int:contact_id>/delete")
    def contact_delete(contact_id):
        contact = db.get_or_404(Contact, contact_id); item_id = contact.application_id
        record_activity(contact.application, "contact_deleted", f"Deleted contact {contact.name}.")
        db.session.delete(contact); db.session.commit(); flash("Contact deleted.", "success")
        return redirect(url_for("application_detail", item_id=item_id))

    @app.get("/contacts")
    def contacts():
        return render_template("contacts.html", contacts=db.session.scalars(db.select(Contact).order_by(Contact.updated_at.desc())).all())

    @app.get("/activity")
    def activity():
        query = visible_activity_query()
        application_id = request.args.get("application", type=int); event_type = request.args.get("event_type", "")
        if application_id: query = query.where(Activity.application_id == application_id)
        if event_type: query = query.where(Activity.event_type == event_type)
        return render_template("activity.html", activities=db.session.scalars(query.order_by(Activity.created_at.desc()).limit(100)).all(),
            applications=db.session.scalars(db.select(Application).order_by(Application.company)).all(),
            event_types=db.session.scalars(db.select(Activity.event_type).where(
                Activity.event_type.not_in(HIDDEN_ACTIVITY_EVENT_TYPES)).distinct().order_by(Activity.event_type)).all())

    @app.get("/public")
    def public_activity():
        activities = db.session.scalars(public_activity_query().order_by(
            Activity.created_at.desc()).limit(100)).all()
        public_events = [
            {"created_at": event.created_at, "company": event.application.company,
             "description": public_activity_description(event), "event_type": event.event_type}
            for event in activities
        ]
        return render_template("public_activity.html", activities=public_events)

    def reference_view(model, template, kind):
        items = db.session.scalars(db.select(model).order_by(model.active.desc(), model.name)).all()
        return render_template(template, items=items, kind=kind)

    @app.get("/pathways")
    def pathways(): return reference_view(Pathway, "references.html", "pathway")

    @app.get("/personas")
    def personas(): return reference_view(Persona, "references.html", "persona")

    @app.route("/<kind>/new", methods=("GET", "POST"))
    @app.route("/<kind>/<int:item_id>/edit", methods=("GET", "POST"))
    def reference_form(kind, item_id=None):
        model = {"pathways": Pathway, "personas": Persona}.get(kind)
        if not model: abort(404)
        item = db.get_or_404(model, item_id) if item_id else model()
        if request.method == "POST":
            item.name = request.form.get("name", "").strip(); item.short_name = request.form.get("short_name", "").strip()
            item.description = request.form.get("description", "").strip(); item.color = request.form.get("color", "#656d76")
            item.active = request.form.get("active") == "on"
            if model is Pathway:
                item.geography = request.form.get("geography", "").strip(); item.notes = request.form.get("notes", "").strip()
            if item.name and item.short_name:
                db.session.add(item)
                try: db.session.commit()
                except Exception:
                    db.session.rollback(); flash("Name must be unique.", "error")
                else:
                    flash(f"{model.__name__} saved.", "success"); return redirect(url_for(kind))
            else: flash("Name and short name are required.", "error")
        return render_template("reference_form.html", item=item, kind=kind, is_pathway=model is Pathway)

    with app.app_context():
        db.create_all()
        seed_reference_data()
    return app


app = create_app()

if __name__ == "__main__":
    app.run()
