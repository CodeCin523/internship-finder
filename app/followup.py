"""Follow-up engine: which companies have gone quiet and need a relance.

A company needs follow-up when its most recent *sent* outbound email is older
than the cadence (company override, else the global default) and no inbound has
arrived since. Terminal states are excluded.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import Company, EventStatus, EventType, PipelineStatus

TERMINAL = {PipelineStatus.rejected, PipelineStatus.offer, PipelineStatus.ghosted}


def _naive(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; normalise so comparisons never mix tz.
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def needs_followup(session: Session, default_days: int) -> list[dict]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out: list[dict] = []
    for company in session.exec(select(Company)).all():
        if company.status in TERMINAL:
            continue
        sent = [
            e
            for e in company.events
            if e.type == EventType.outbound_email and e.status == EventStatus.sent
        ]
        if not sent:
            continue
        last_out = max(_naive(e.created_at) for e in sent)
        replied_since = any(
            e.type == EventType.inbound_email and _naive(e.created_at) > last_out
            for e in company.events
        )
        if replied_since:
            continue
        cadence = company.followup_days_override or default_days
        age = (now - last_out).days
        if age >= cadence:
            out.append({"company": company, "days": age})
    out.sort(key=lambda r: r["days"], reverse=True)
    return out
