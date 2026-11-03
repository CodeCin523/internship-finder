"""Export companies to a single-sheet .xlsx that mirrors the user's own format.

Grouped layout: the company name appears once, then one row per timeline event
beneath it (name/email/contact columns blank on the follow-on rows). Company
notes sit on the first row. This round-trips: the importer forward-fills blank
company names to regroup the rows.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlmodel import Session, select

from app.models import Company, EventType, PipelineStatus, TimelineEvent  # noqa: F401

HEADERS = [
    "nom de l'entreprise",
    "date de contacte",
    "moyen de communication",
    "courriel",
    "téléphone",
    "personne contacter",
    "entrevue?",
    "commentaires",
    "status",
    "domaine",
]
COL_WIDTHS = [24, 14, 24, 26, 16, 20, 10, 42, 14, 18]

STATUS_FR = {
    PipelineStatus.lead: "prospect",
    PipelineStatus.contacted: "contacté",
    PipelineStatus.in_conversation: "en discussion",
    PipelineStatus.interview: "entrevue",
    PipelineStatus.offer: "offre",
    PipelineStatus.rejected: "refus",
    PipelineStatus.ghosted: "sans réponse",
}
MOYEN_FR = {
    EventType.outbound_email: "courriel",
    EventType.inbound_email: "courriel (reçu)",
    EventType.call: "téléphone",
    EventType.application: "candidature / portail",
    EventType.manual_note: "note",
    EventType.other: "autre",
}


def _fmt_date(dt) -> str:
    return dt.strftime("%Y-%m-%d") if dt else ""


def _event_desc(ev: TimelineEvent) -> str:
    return " — ".join(p for p in (ev.subject, ev.body) if p)


def build_workbook(session: Session) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Entreprises"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for comp in session.exec(select(Company).order_by(Company.name)).all():
        primary = next((e for e in comp.emails if e.is_primary), None)
        if primary is None and comp.emails:
            primary = comp.emails[0]
        contact = comp.contacts[0] if comp.contacts else None
        email = primary.address if primary else ""
        phone = contact.phone if contact else ""
        person = contact.name if contact else ""
        entrevue = "oui" if comp.status == PipelineStatus.interview else "non"
        status_fr = STATUS_FR.get(comp.status, comp.status.value)

        events = sorted(
            (e for e in comp.events if e.type != EventType.status_change),
            key=lambda e: e.created_at,
        )

        if not events:
            ws.append([comp.name, "", "", email, phone, person, entrevue,
                       comp.notes, status_fr, comp.domain])
            continue

        for i, ev in enumerate(events):
            moyen = MOYEN_FR.get(ev.type, ev.type.value)
            if i == 0:
                commentaires = comp.notes
                desc = _event_desc(ev)
                if desc:
                    commentaires = f"{commentaires}\n{desc}" if commentaires else desc
                ws.append([comp.name, _fmt_date(ev.created_at), moyen, email, phone,
                           person, entrevue, commentaires, status_fr, comp.domain])
            else:
                ws.append(["", _fmt_date(ev.created_at), moyen, "", "", "", "",
                           _event_desc(ev), "", ""])

    for idx, width in enumerate(COL_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
