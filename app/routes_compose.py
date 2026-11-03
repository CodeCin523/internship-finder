"""Compose → review → send.

Pick a template + optional contact, fill it from the company's data, run it
through the local LLM for French polishing, then review (edit / regenerate /
switch template / discard). Saving stores a *pending* outbound draft on the
timeline; sending (M3) pushes it through Microsoft Graph and marks it sent.
"""

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app import documents, graph
from app.db import get_session
from app.drafting import PLACEHOLDERS, grouped_templates, render_template
from app.llm import get_backend
from app.models import (
    Company,
    Contact,
    EventStatus,
    EventType,
    PipelineStatus,
    Settings,
    Template,
    TimelineEvent,
)
from app.templating import templates

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_company(session: Session, company_id: int) -> Company:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _render_review(request, session, company, template, contact,
                   subject, body, llm_ok, llm_error):
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "company": company,
            "subject": subject,
            "body": body,
            "llm_ok": llm_ok,
            "llm_error": llm_error,
            "all_templates_grouped": grouped_templates(session),
            "selected_template_id": template.id if template else None,
            "selected_contact_id": contact.id if contact else None,
            "placeholders": PLACEHOLDERS,
        },
    )


@router.get("/companies/{company_id}/compose", response_class=HTMLResponse)
def compose_picker(
    company_id: int, request: Request, session: Session = Depends(get_session)
):
    company = _get_company(session, company_id)
    grouped = grouped_templates(session)
    return templates.TemplateResponse(
        request,
        "compose.html",
        {
            "company": company,
            "grouped": grouped,
            "contacts": company.contacts,
            "has_templates": any(grouped.values()),
        },
    )


@router.post("/companies/{company_id}/compose", response_class=HTMLResponse)
def compose_action(
    company_id: int,
    request: Request,
    session: Session = Depends(get_session),
    action: str = Form(...),
    template_id: int = Form(...),
    contact_id: str = Form(""),
    subject: str = Form(""),
    body: str = Form(""),
):
    company = _get_company(session, company_id)
    settings = session.get(Settings, 1)
    contact = (
        session.get(Contact, int(contact_id))
        if contact_id.strip().isdigit()
        else None
    )
    template = session.get(Template, template_id)

    if action == "save":
        draft = TimelineEvent(
            company_id=company.id,
            contact_id=contact.id if contact else None,
            template_id=template.id if template else None,
            type=EventType.outbound_email,
            status=EventStatus.pending,
            subject=subject.strip(),
            body=body,
        )
        session.add(draft)
        session.commit()
        return RedirectResponse(f"/companies/{company.id}?draft=1", status_code=303)

    if action in ("generate", "refill"):
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        subject, body = render_template(template, company, contact, settings)

    result = get_backend(settings).correct(body, settings.email_language)
    return _render_review(
        request, session, company, template, contact,
        subject, result.text, result.ok, result.error,
    )


@router.post("/events/{event_id}/send")
def event_send(event_id: int, session: Session = Depends(get_session)):
    event = session.get(TimelineEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if event.type != EventType.outbound_email or event.status != EventStatus.pending:
        raise HTTPException(status_code=400, detail="Not a sendable draft")

    company = session.get(Company, event.company_id)
    settings = session.get(Settings, 1)

    if not settings.graph_client_id or not graph.is_authenticated(settings.graph_client_id):
        return RedirectResponse("/graph?need_login=1", status_code=303)

    primary = next((e for e in company.emails if e.is_primary), None)
    if primary is None and company.emails:
        primary = company.emails[0]
    if primary is None:
        msg = quote("No email address on file for this company.")
        return RedirectResponse(f"/companies/{company.id}?send_error={msg}", status_code=303)

    attachments = []
    cv = documents.global_cv(session)
    if cv is not None:
        attachments.append(documents.read_attachment(cv))
    letter = documents.company_letter(session, company.id)
    if letter is not None:
        attachments.append(documents.read_attachment(letter))

    result = graph.send_email(
        settings.graph_client_id, primary.address, event.subject, event.body, attachments
    )
    if not result.ok:
        return RedirectResponse(
            f"/companies/{company.id}?send_error={quote(result.error[:200])}",
            status_code=303,
        )

    event.status = EventStatus.sent
    event.created_at = _now()
    event.graph_conversation_id = result.conversation_id
    event.graph_message_id = result.message_id
    if company.status == PipelineStatus.lead:
        company.status = PipelineStatus.contacted
    session.add(event)
    session.add(company)
    session.commit()
    return RedirectResponse(f"/companies/{company.id}?sent=1", status_code=303)
