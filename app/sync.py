"""Inbox ingestion: pull recent mail via Graph and log replies to the timeline.

Matching is intentionally conservative to avoid mis-filing:
  1. by conversationId — a reply in a thread we started (strongest signal), then
  2. by sender address — matched against company emails and known contacts.
Messages that match neither are skipped (they stay in your inbox untouched).
Already-ingested messages are skipped by Graph message id.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app import graph
from app.models import (
    Company,
    CompanyEmail,
    Contact,
    EventStatus,
    EventType,
    PipelineStatus,
    Settings,
    TimelineEvent,
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_inbox(session: Session) -> dict:
    settings = session.get(Settings, 1)
    if not settings.graph_client_id or not graph.is_authenticated(settings.graph_client_id):
        return {"ok": False, "error": "not_connected"}

    messages, error = graph.list_inbox(settings.graph_client_id, top=40)
    if error:
        return {"ok": False, "error": error}

    addr_map: dict[str, int] = {}
    for ce in session.exec(select(CompanyEmail)).all():
        if ce.address and ce.company_id:
            addr_map[ce.address.strip().lower()] = ce.company_id
    for ct in session.exec(select(Contact)).all():
        if ct.email and ct.company_id:
            addr_map.setdefault(ct.email.strip().lower(), ct.company_id)

    conv_map: dict[str, int] = {}
    existing_ids: set[str] = set()
    for ev in session.exec(select(TimelineEvent)).all():
        if ev.graph_conversation_id and ev.company_id:
            conv_map.setdefault(ev.graph_conversation_id, ev.company_id)
        if ev.graph_message_id:
            existing_ids.add(ev.graph_message_id)

    ingested = 0
    for m in messages:
        mid = m.get("id")
        if not mid or mid in existing_ids:
            continue
        conv = m.get("conversationId")
        sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "").lower()
        company_id = conv_map.get(conv) or addr_map.get(sender)
        if not company_id:
            continue

        session.add(
            TimelineEvent(
                company_id=company_id,
                type=EventType.inbound_email,
                status=EventStatus.received,
                subject=m.get("subject") or "",
                body=m.get("bodyPreview") or "",
                graph_message_id=mid,
                graph_conversation_id=conv,
                created_at=_parse_dt(m.get("receivedDateTime")) or datetime.now(timezone.utc),
            )
        )
        existing_ids.add(mid)
        ingested += 1

        company = session.get(Company, company_id)
        if company and company.status == PipelineStatus.contacted:
            company.status = PipelineStatus.in_conversation
            session.add(company)

    session.commit()
    return {"ok": True, "ingested": ingested}
