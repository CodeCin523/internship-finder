"""Companies, contacts, emails, name variants, and the interaction timeline.

M1: a fully usable tracker. No email/LLM here yet — every timeline entry is
logged by hand. Auto-ingested replies arrive in M4 and land in the same table.
"""

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app import documents
from app import sync as sync_mod
from app.db import get_session
from app.followup import needs_followup
from app.models import (
    Company,
    CompanyEmail,
    Contact,
    EventStatus,
    EventType,
    NameVariant,
    PipelineStatus,
    Settings,
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


def _back(company_id: int) -> RedirectResponse:
    return RedirectResponse(f"/companies/{company_id}", status_code=303)


# --- Dashboard -------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    companies = session.exec(select(Company).order_by(Company.name)).all()
    rows = []
    for c in companies:
        primary = next((e for e in c.emails if e.is_primary), None)
        if primary is None and c.emails:
            primary = c.emails[0]
        last = max((e.created_at for e in c.events), default=None)
        rows.append(
            {
                "company": c,
                "primary_email": primary.address if primary else "",
                "last_activity": last,
            }
        )
    settings = session.get(Settings, 1)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "rows": rows,
            "count": len(companies),
            "followups": needs_followup(session, settings.followup_days),
        },
    )


@router.post("/sync")
def sync_now(session: Session = Depends(get_session)):
    result = sync_mod.sync_inbox(session)
    if not result.get("ok"):
        if result.get("error") == "not_connected":
            return RedirectResponse("/graph?need_login=1", status_code=303)
        return RedirectResponse(
            f"/?sync_error={quote(str(result.get('error'))[:200])}", status_code=303
        )
    return RedirectResponse(f"/?synced={result.get('ingested', 0)}", status_code=303)


# --- Company create / detail / edit / delete -------------------------------

@router.get("/companies/new", response_class=HTMLResponse)
def company_new(request: Request):
    return templates.TemplateResponse(
        request, "company_new.html", {"statuses": list(PipelineStatus)}
    )


@router.post("/companies")
def company_create(
    session: Session = Depends(get_session),
    name: str = Form(...),
    email: str = Form(""),
    domain: str = Form(""),
    status: str = Form(PipelineStatus.lead.value),
    notes: str = Form(""),
):
    company = Company(
        name=name.strip(), domain=domain.strip(), status=PipelineStatus(status), notes=notes
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    addr = email.strip()
    if addr:
        session.add(CompanyEmail(company_id=company.id, address=addr, is_primary=True))
        if not company.domain and "@" in addr:
            company.domain = addr.split("@", 1)[1]
            session.add(company)
        session.commit()
    return _back(company.id)


@router.get("/companies/{company_id}", response_class=HTMLResponse)
def company_detail(
    company_id: int, request: Request, session: Session = Depends(get_session)
):
    company = _get_company(session, company_id)
    events = sorted(company.events, key=lambda e: e.created_at, reverse=True)
    return templates.TemplateResponse(
        request,
        "company_detail.html",
        {
            "company": company,
            "events": events,
            "statuses": list(PipelineStatus),
            "event_types": [
                EventType.manual_note,
                EventType.call,
                EventType.application,
                EventType.other,
            ],
            "letter": documents.company_letter(session, company.id),
        },
    )


@router.post("/companies/{company_id}/edit")
def company_edit(
    company_id: int,
    session: Session = Depends(get_session),
    name: str = Form(...),
    domain: str = Form(""),
    status: str = Form(...),
    notes: str = Form(""),
    followup_days_override: str = Form(""),
):
    company = _get_company(session, company_id)
    company.name = name.strip()
    company.domain = domain.strip()
    new_status = PipelineStatus(status)
    if new_status != company.status:
        session.add(
            TimelineEvent(
                company_id=company.id,
                type=EventType.status_change,
                status=EventStatus.logged,
                subject="Status changed",
                body=f"{company.status.value} → {new_status.value}",
            )
        )
        company.status = new_status
    company.notes = notes
    override = followup_days_override.strip()
    company.followup_days_override = int(override) if override.isdigit() else None
    session.add(company)
    session.commit()
    return _back(company.id)


@router.post("/companies/{company_id}/delete")
def company_delete(company_id: int, session: Session = Depends(get_session)):
    company = _get_company(session, company_id)
    for collection in (
        company.emails,
        company.variants,
        company.contacts,
        company.events,
        company.attachments,
    ):
        for item in list(collection):
            session.delete(item)
    session.delete(company)
    session.commit()
    return RedirectResponse("/", status_code=303)


# --- Emails ----------------------------------------------------------------

@router.post("/companies/{company_id}/emails")
def email_add(
    company_id: int,
    session: Session = Depends(get_session),
    address: str = Form(...),
    is_primary: str = Form(""),
):
    company = _get_company(session, company_id)
    primary = bool(is_primary)
    if primary:
        for e in company.emails:
            e.is_primary = False
    addr = address.strip()
    session.add(CompanyEmail(company_id=company.id, address=addr, is_primary=primary))
    if not company.domain and "@" in addr:
        company.domain = addr.split("@", 1)[1]
        session.add(company)
    session.commit()
    return _back(company.id)


@router.post("/emails/{email_id}/primary")
def email_primary(email_id: int, session: Session = Depends(get_session)):
    email = session.get(CompanyEmail, email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    for e in email.company.emails:
        e.is_primary = e.id == email.id
    session.commit()
    return _back(email.company_id)


@router.post("/emails/{email_id}/delete")
def email_delete(email_id: int, session: Session = Depends(get_session)):
    email = session.get(CompanyEmail, email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    company_id = email.company_id
    session.delete(email)
    session.commit()
    return _back(company_id)


# --- Name variants ---------------------------------------------------------

@router.post("/companies/{company_id}/variants")
def variant_add(
    company_id: int,
    session: Session = Depends(get_session),
    variant: str = Form(...),
):
    company = _get_company(session, company_id)
    session.add(NameVariant(company_id=company.id, variant=variant.strip()))
    session.commit()
    return _back(company.id)


@router.post("/variants/{variant_id}/delete")
def variant_delete(variant_id: int, session: Session = Depends(get_session)):
    variant = session.get(NameVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    company_id = variant.company_id
    session.delete(variant)
    session.commit()
    return _back(company_id)


# --- Contacts --------------------------------------------------------------

@router.post("/companies/{company_id}/contacts")
def contact_add(
    company_id: int,
    session: Session = Depends(get_session),
    name: str = Form(...),
    role: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    notes: str = Form(""),
):
    company = _get_company(session, company_id)
    session.add(
        Contact(
            company_id=company.id,
            name=name.strip(),
            role=role.strip(),
            email=email.strip(),
            phone=phone.strip(),
            notes=notes,
        )
    )
    session.commit()
    return _back(company.id)


@router.post("/contacts/{contact_id}/delete")
def contact_delete(contact_id: int, session: Session = Depends(get_session)):
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    company_id = contact.company_id
    session.delete(contact)
    session.commit()
    return _back(company_id)


# --- Timeline --------------------------------------------------------------

@router.post("/companies/{company_id}/events")
def event_add(
    company_id: int,
    session: Session = Depends(get_session),
    event_type: str = Form(...),
    subject: str = Form(""),
    body: str = Form(""),
    date: str = Form(""),
):
    company = _get_company(session, company_id)
    created = _now()
    if date.strip():
        try:
            created = datetime.strptime(date.strip(), "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass
    session.add(
        TimelineEvent(
            company_id=company.id,
            type=EventType(event_type),
            status=EventStatus.logged,
            subject=subject.strip(),
            body=body.strip(),
            created_at=created,
        )
    )
    session.commit()
    return _back(company.id)


@router.post("/events/{event_id}/delete")
def event_delete(event_id: int, session: Session = Depends(get_session)):
    event = session.get(TimelineEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    company_id = event.company_id
    session.delete(event)
    session.commit()
    return _back(company_id)
