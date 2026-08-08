import os
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_

db = SQLAlchemy()

APPLICATION_STATUSES = (
    "Interested", "Preparing", "Applied", "Networking", "Assessment", "Interview",
    "Final Round", "Offer", "Rejected", "Withdrawn", "Closed",
)
OUTREACH_STATUSES = (
    "Not Contacted", "Outreach Sent", "Connected", "Replied", "Follow-up Needed",
    "Conversation", "No Response",
)


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
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    pathway = db.relationship("Pathway", back_populates="applications")
    persona = db.relationship("Persona", back_populates="applications")
    contacts = db.relationship("Contact", back_populates="application", cascade="all, delete-orphan", lazy="selectin")


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
    return bool(item.company and item.role_title and item.pathway_id and item.persona_id and item.status in APPLICATION_STATUSES)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI="sqlite:///job_tracker.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)

    @app.get("/")
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
            if populate_application(item):
                db.session.add(item); db.session.commit()
                flash("Application saved.", "success")
                return redirect(url_for("application_detail", item_id=item.id))
            flash("Company, role, pathway, and persona are required.", "error")
        return render_template("application_form.html", item=item, statuses=APPLICATION_STATUSES,
            pathways=db.session.scalars(db.select(Pathway).order_by(Pathway.name)).all(),
            personas=db.session.scalars(db.select(Persona).order_by(Persona.name)).all())

    @app.get("/applications/<int:item_id>")
    def application_detail(item_id):
        return render_template("application_detail.html", item=db.get_or_404(Application, item_id), outreach_statuses=OUTREACH_STATUSES)

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
            db.session.add(Contact(application=application, name=name, title=request.form.get("title", "").strip(),
                organization=request.form.get("organization", "").strip(), email=request.form.get("email", "").strip(),
                linkedin_url=request.form.get("linkedin_url", "").strip(), outreach_date=parse_date(request.form.get("outreach_date")),
                outreach_status=status, notes=request.form.get("notes", "").strip()))
            db.session.commit(); flash("Contact added.", "success")
        return redirect(url_for("application_detail", item_id=item_id))

    @app.route("/contacts/<int:contact_id>/edit", methods=("GET", "POST"))
    def contact_edit(contact_id):
        contact = db.get_or_404(Contact, contact_id)
        if request.method == "POST":
            contact.name = request.form.get("name", "").strip(); contact.title = request.form.get("title", "").strip()
            contact.organization = request.form.get("organization", "").strip(); contact.email = request.form.get("email", "").strip()
            contact.linkedin_url = request.form.get("linkedin_url", "").strip(); contact.outreach_date = parse_date(request.form.get("outreach_date"))
            contact.outreach_status = request.form.get("outreach_status", "Not Contacted"); contact.notes = request.form.get("notes", "").strip()
            if contact.name and contact.outreach_status in OUTREACH_STATUSES:
                db.session.commit(); flash("Contact updated.", "success"); return redirect(url_for("application_detail", item_id=contact.application_id))
            flash("Contact name is required.", "error")
        return render_template("contact_form.html", contact=contact, outreach_statuses=OUTREACH_STATUSES)

    @app.post("/contacts/<int:contact_id>/delete")
    def contact_delete(contact_id):
        contact = db.get_or_404(Contact, contact_id); item_id = contact.application_id
        db.session.delete(contact); db.session.commit(); flash("Contact deleted.", "success")
        return redirect(url_for("application_detail", item_id=item_id))

    @app.get("/contacts")
    def contacts():
        return render_template("contacts.html", contacts=db.session.scalars(db.select(Contact).order_by(Contact.updated_at.desc())).all())

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
