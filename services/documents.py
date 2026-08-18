"""Safe text extraction and lightweight PDF rendering."""
from datetime import date
from xml.sax.saxutils import escape

def extract_text(path, suffix):
    if suffix == ".pdf":
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages).strip()
        return text or "No extractable text found in this PDF."
    if suffix == ".docx":
        from docx import Document as DocxDocument
        return "\n".join(p.text for p in DocxDocument(path).paragraphs).strip()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    raise ValueError("Unsupported document type")


def render_cover_letter_pdf(path, text, application, profile):
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    styles = getSampleStyleSheet(); story = []
    sender = [profile.full_name, profile.location, profile.email, profile.phone, profile.linkedin_url]
    sender = [escape(value) for value in sender if value]
    if sender: story.extend([Paragraph("<b>" + sender[0] + "</b>", styles["Normal"]), Paragraph(" · ".join(sender[1:]), styles["Normal"]), Spacer(1, 14)])
    story.extend([Paragraph(date.today().strftime("%B %d, %Y"), styles["Normal"]), Spacer(1, 12),
                  Paragraph(escape(application.company), styles["Normal"]),
                  Paragraph(escape(application.role_title), styles["Normal"]), Spacer(1, 14)])
    for paragraph in filter(None, (part.strip() for part in text.split("\n\n"))):
        story.extend([Paragraph(escape(paragraph).replace("\n", "<br/>"), styles["BodyText"]), Spacer(1, 10)])
    SimpleDocTemplate(str(path), pagesize=LETTER, rightMargin=.8*inch, leftMargin=.8*inch,
                      topMargin=.7*inch, bottomMargin=.7*inch, title=f"Cover Letter - {application.company}").build(story)
