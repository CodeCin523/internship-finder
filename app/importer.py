"""AI-assisted .xlsx import — the reverse of exporter.py (M5, part B).

The user keeps internship outreach in spreadsheets whose columns vary ("nom de
l'entreprise" vs "Entreprise", "statut" vs "status", French date/status wording,
etc.). Importing them has two hard parts:

1. **Which column is what?** A deterministic matcher recognises the familiar
   French headers (and this app's own export) with no model at all — that's the
   path that's always tested. Anything it can't place is handed to the local LLM,
   which maps the leftover headers to our canonical fields. If the model is down
   the rule-based mapping still stands; the import just isn't "AI-enhanced".
2. **Regrouping.** The export writes a company name once, then one row per
   timeline event with the name column blank. We forward-fill the blank names to
   rebuild each company and its events, then translate the French status/moyen
   wording back into enums.

Nothing touches the database until the user approves the preview (`build_plan`
→ review → `commit_plan`), matching the app's review-gate rule.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Optional

from openpyxl import load_workbook
from sqlmodel import Session, select

from app.llm import get_backend
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

# Canonical field keys a column can map to (mirrors the export's columns).
CANON = (
    "company_name",
    "date",
    "moyen",
    "email",
    "phone",
    "contact_person",
    "entrevue",
    "commentaires",
    "status",
    "domaine",
)


def _norm(value) -> str:
    """Lowercase, strip accents and collapse whitespace for fuzzy matching."""
    s = unicodedata.normalize("NFKD", str(value if value is not None else ""))
    s = s.encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


# Accent-insensitive synonyms for each canonical field. Keys are already _norm'd.
_HEADER_SYNONYMS: dict[str, tuple[str, ...]] = {
    "company_name": (
        "nom de l'entreprise", "entreprise", "compagnie", "company", "nom",
        "societe", "nom de la compagnie", "nom entreprise", "employeur",
    ),
    "date": (
        "date de contacte", "date de contact", "date", "date contact",
        "date du contact", "date de la demarche",
    ),
    "moyen": (
        "moyen de communication", "moyen", "communication", "canal",
        "type de contact", "mode", "mode de contact", "moyen de contact",
    ),
    "email": (
        "courriel", "email", "e-mail", "mail", "adresse courriel",
        "adresse email", "courriel de l'entreprise",
    ),
    "phone": (
        "telephone", "tel", "tel.", "phone", "numero",
        "numero de telephone", "no de telephone",
    ),
    "contact_person": (
        "personne contacter", "personne a contacter", "personne", "contact",
        "contact person", "personne ressource", "personne-ressource",
        "nom du contact", "interlocuteur", "recruteur",
    ),
    "entrevue": ("entrevue?", "entrevue", "entrevue ?", "interview", "entretien"),
    "commentaires": (
        "commentaires", "commentaire", "notes", "note", "comments",
        "remarques", "remarque", "description", "details", "suivi",
    ),
    "status": ("status", "statut", "etat", "etape", "stage", "phase", "pipeline"),
    "domaine": ("domaine", "domain", "site", "site web", "website", "web", "url"),
}
_SYNONYM_TO_CANON = {
    syn: canon for canon, syns in _HEADER_SYNONYMS.items() for syn in syns
}

# French (and English) wording → enums, reversing exporter.STATUS_FR / MOYEN_FR.
_STATUS_REVERSE: dict[str, PipelineStatus] = {
    "prospect": PipelineStatus.lead, "lead": PipelineStatus.lead,
    "piste": PipelineStatus.lead, "nouveau": PipelineStatus.lead,
    "contacte": PipelineStatus.contacted, "contacted": PipelineStatus.contacted,
    "premier contact": PipelineStatus.contacted,
    "en discussion": PipelineStatus.in_conversation,
    "in_conversation": PipelineStatus.in_conversation,
    "in conversation": PipelineStatus.in_conversation,
    "discussion": PipelineStatus.in_conversation,
    "en cours": PipelineStatus.in_conversation,
    "echange": PipelineStatus.in_conversation,
    "entrevue": PipelineStatus.interview, "interview": PipelineStatus.interview,
    "entretien": PipelineStatus.interview,
    "offre": PipelineStatus.offer, "offer": PipelineStatus.offer,
    "refus": PipelineStatus.rejected, "refuse": PipelineStatus.rejected,
    "rejected": PipelineStatus.rejected, "rejete": PipelineStatus.rejected,
    "pas retenu": PipelineStatus.rejected,
    "sans reponse": PipelineStatus.ghosted, "ghosted": PipelineStatus.ghosted,
    "ghoste": PipelineStatus.ghosted, "aucune reponse": PipelineStatus.ghosted,
    "pas de reponse": PipelineStatus.ghosted,
}
_MOYEN_REVERSE: dict[str, EventType] = {
    "courriel": EventType.outbound_email, "email": EventType.outbound_email,
    "e-mail": EventType.outbound_email, "mail": EventType.outbound_email,
    "courriel envoye": EventType.outbound_email,
    "courriel (recu)": EventType.inbound_email,
    "courriel recu": EventType.inbound_email, "recu": EventType.inbound_email,
    "reply": EventType.inbound_email, "reponse": EventType.inbound_email,
    "telephone": EventType.call, "tel": EventType.call, "call": EventType.call,
    "appel": EventType.call, "phone": EventType.call,
    "candidature / portail": EventType.application,
    "candidature": EventType.application, "portail": EventType.application,
    "application": EventType.application, "postule": EventType.application,
    "formulaire": EventType.application,
    "note": EventType.manual_note, "manual_note": EventType.manual_note,
    "autre": EventType.other, "other": EventType.other, "divers": EventType.other,
}
_TRUE_WORDS = {"oui", "yes", "y", "o", "x", "true", "vrai", "1"}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y")


class ImportError_(ValueError):
    """A problem that stops the import before any preview (shown to the user)."""


# --- Column mapping --------------------------------------------------------

def _match_header(header: str) -> Optional[str]:
    n = _norm(header)
    if not n:
        return None
    if n in _SYNONYM_TO_CANON:
        return _SYNONYM_TO_CANON[n]
    stripped = n.rstrip("?").strip()  # "entrevue?" -> "entrevue"
    if stripped in _SYNONYM_TO_CANON:
        return _SYNONYM_TO_CANON[stripped]
    return None


def _ai_map(headers: list[str], settings: Settings) -> tuple[dict[str, str], str]:
    """Ask the local LLM to map the given headers to canonical fields.

    Returns (mapping, error). `mapping` only contains headers the model placed
    into a known field; everything else is left for the caller to treat as
    unmapped. On any failure the mapping is empty and `error` explains why.
    """
    prompt = (
        "You map spreadsheet column headers to fields in an internship-tracking "
        "app. The fields are: company_name, date, moyen (how we communicated, "
        "e.g. email/phone), email, phone, contact_person, entrevue (interview "
        "yes/no), commentaires (notes), status, domaine (web domain).\n"
        "Return ONLY a JSON object mapping each header below to exactly one field "
        'name, or to "ignore" if none fits. No prose.\n'
        f"Headers: {json.dumps(headers, ensure_ascii=False)}"
    )
    result = get_backend(settings).complete(prompt)
    if not result.ok:
        return {}, result.error
    try:
        start, end = result.text.find("{"), result.text.rfind("}")
        raw = json.loads(result.text[start : end + 1]) if start >= 0 < end else {}
    except (ValueError, json.JSONDecodeError):
        return {}, "The model's reply was not valid JSON."
    mapping = {
        h: raw[h]
        for h in headers
        if isinstance(raw.get(h), str) and raw[h] in CANON
    }
    return mapping, "" if mapping else "The model mapped no new columns."


def map_headers(
    headers: list[str], settings: Optional[Settings]
) -> tuple[dict[str, Optional[str]], bool, str]:
    """Map every header to a canonical field (or None).

    Rule-based first (always), then the LLM fills in whatever's left. Returns
    (mapping, ai_used, ai_error).
    """
    mapping: dict[str, Optional[str]] = {h: _match_header(h) for h in headers}
    unresolved = [h for h, c in mapping.items() if c is None and h.strip()]
    if not unresolved or settings is None:
        return mapping, False, ""
    ai_mapping, ai_error = _ai_map(unresolved, settings)
    for header, canon in ai_mapping.items():
        mapping[header] = canon
    return mapping, bool(ai_mapping), ai_error


# --- Value coercion --------------------------------------------------------

def _to_iso_date(value) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _status_from(value) -> Optional[PipelineStatus]:
    return _STATUS_REVERSE.get(_norm(value)) if str(value or "").strip() else None


def _moyen_from(value) -> EventType:
    """A communication means → event type; unknown-but-present → a plain note."""
    n = _norm(value)
    if not n:
        return EventType.manual_note
    return _MOYEN_REVERSE.get(n, EventType.manual_note)


def _domain_of(email: str) -> str:
    return email.split("@", 1)[1].strip() if "@" in email else ""


# --- Plan building ---------------------------------------------------------

def parse_workbook(data: bytes) -> tuple[list[str], list[list]]:
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ImportError_(
            f"Could not read that file as an .xlsx workbook ({type(exc).__name__})."
        )
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    if not rows:
        raise ImportError_("The spreadsheet is empty.")
    headers = ["" if h is None else str(h).strip() for h in rows[0]]
    return headers, rows[1:]


def build_plan(data: bytes, filename: str, settings: Optional[Settings]) -> dict:
    """Parse + map + regroup into a review plan. No database writes."""
    headers, body = parse_workbook(data)
    mapping, ai_used, ai_error = map_headers(headers, settings)

    col = {}  # canonical field -> first column index that maps to it
    for idx, header in enumerate(headers):
        canon = mapping.get(header)
        if canon and canon not in col:
            col[canon] = idx

    if "company_name" not in col:
        raise ImportError_(
            "Couldn't find a company-name column. Rename it to "
            "“nom de l'entreprise” (or Entreprise) and try again."
        )

    def cell(row, field):
        idx = col.get(field)
        return row[idx] if idx is not None and idx < len(row) else None

    def text(row, field) -> str:
        value = cell(row, field)
        return "" if value is None else str(value).strip()

    companies: list[dict] = []
    current: Optional[dict] = None
    skipped = 0
    for row in body:
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        name = text(row, "company_name")
        if name:
            email = text(row, "email")
            status = _status_from(cell(row, "status"))
            if status is None and _norm(cell(row, "entrevue")) in _TRUE_WORDS:
                status = PipelineStatus.interview
            current = {
                "name": name,
                "email": email,
                "domain": text(row, "domaine") or _domain_of(email),
                "status": (status or PipelineStatus.lead).value,
                "contact_name": text(row, "contact_person"),
                "contact_phone": text(row, "phone"),
                "notes": "",
                "events": [],
                "_first_row": row,
            }
            companies.append(current)
        elif current is None:
            skipped += 1  # a data row before any company name
            continue

        iso = _to_iso_date(cell(row, "date"))
        comment = text(row, "commentaires")
        moyen_raw = text(row, "moyen")
        is_event = bool(iso or moyen_raw)
        if row is current.get("_first_row") and not is_event:
            # A header row with notes but no interaction yet → company notes.
            current["notes"] = comment
        elif is_event or comment:
            current["events"].append(
                {"date": iso, "type": _moyen_from(moyen_raw).value, "body": comment}
            )

    for comp in companies:
        comp.pop("_first_row", None)

    return {
        "source_name": filename,
        "mapping": mapping,
        "ai_used": ai_used,
        "ai_error": ai_error,
        "companies": companies,
        "skipped_rows": skipped,
        "unmapped": [h for h in headers if h.strip() and mapping.get(h) is None],
    }


# --- Preview & commit ------------------------------------------------------

def _existing_index(session: Session) -> dict[str, Company]:
    """Lookup of existing companies by normalised name, variant and domain."""
    index: dict[str, Company] = {}
    for comp in session.exec(select(Company)).all():
        index.setdefault(_norm(comp.name), comp)
        if comp.domain:
            index.setdefault(_norm(comp.domain), comp)
        for v in comp.variants:
            index.setdefault(_norm(v.variant), comp)
    return index


def _match(company: dict, index: dict[str, Company]) -> Optional[Company]:
    hit = index.get(_norm(company["name"]))
    if hit is None and company.get("domain"):
        hit = index.get(_norm(company["domain"]))
    return hit


def _event_key(iso: Optional[str], type_value: str, body: str) -> tuple:
    return (iso or "", type_value, _norm(body))


def plan_summary(session: Session, plan: dict) -> dict:
    """Annotate each company in the plan with new/existing + dedup counts."""
    index = _existing_index(session)
    rows, new_companies, total_events = [], 0, 0
    for comp in plan["companies"]:
        match = _match(comp, index)
        seen = set()
        if match is not None:
            seen = {
                _event_key(e.created_at.date().isoformat() if e.created_at else None,
                           e.type.value, e.subject + e.body)
                for e in match.events
            }
        add, dup = 0, 0
        for ev in comp["events"]:
            if _event_key(ev["date"], ev["type"], ev["body"]) in seen:
                dup += 1
            else:
                add += 1
        new_companies += match is None
        total_events += add
        rows.append({
            "name": comp["name"],
            "is_new": match is None,
            "matched_name": match.name if match else "",
            "status": comp["status"],
            "email": comp["email"],
            "domain": comp["domain"],
            "contact": comp["contact_name"],
            "events_add": add,
            "events_dup": dup,
        })
    return {
        "rows": rows,
        "new_companies": new_companies,
        "existing_companies": len(rows) - new_companies,
        "total_events": total_events,
        "ai_used": plan.get("ai_used", False),
        "ai_error": plan.get("ai_error", ""),
        "unmapped": plan.get("unmapped", []),
        "skipped_rows": plan.get("skipped_rows", 0),
        "source_name": plan.get("source_name", ""),
    }


def _parse_created(iso: Optional[str]) -> datetime:
    if iso:
        try:
            return datetime.strptime(iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def commit_plan(session: Session, plan: dict) -> dict:
    """Write the approved plan. New companies are created; events for existing
    ones are appended, skipping exact duplicates. Idempotent on re-import."""
    index = _existing_index(session)
    created, updated, added, skipped = 0, 0, 0, 0

    for comp in plan["companies"]:
        match = _match(comp, index)
        if match is None:
            match = Company(
                name=comp["name"],
                domain=comp["domain"],
                status=PipelineStatus(comp["status"]),
                notes=comp["notes"],
            )
            session.add(match)
            session.flush()  # assign an id for the foreign keys below
            if comp["email"]:
                session.add(CompanyEmail(
                    company_id=match.id, address=comp["email"], is_primary=True
                ))
            index[_norm(match.name)] = match
            if match.domain:
                index.setdefault(_norm(match.domain), match)
            created += 1
            seen = set()
        else:
            updated += 1
            if not match.domain and comp["domain"]:
                match.domain = comp["domain"]
                session.add(match)
            if comp["email"] and not any(
                e.address.lower() == comp["email"].lower() for e in match.emails
            ):
                session.add(CompanyEmail(
                    company_id=match.id,
                    address=comp["email"],
                    is_primary=not match.emails,
                ))
            seen = {
                _event_key(e.created_at.date().isoformat() if e.created_at else None,
                           e.type.value, e.subject + e.body)
                for e in match.events
            }

        if comp["contact_name"] and not any(
            c.name == comp["contact_name"] for c in match.contacts
        ):
            session.add(Contact(
                company_id=match.id,
                name=comp["contact_name"],
                phone=comp["contact_phone"],
            ))

        for ev in comp["events"]:
            key = _event_key(ev["date"], ev["type"], ev["body"])
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            session.add(TimelineEvent(
                company_id=match.id,
                type=EventType(ev["type"]),
                status=EventStatus.logged,
                body=ev["body"],
                created_at=_parse_created(ev["date"]),
            ))
            added += 1

    session.commit()
    return {"created": created, "updated": updated, "events_added": added,
            "events_skipped": skipped}


# --- Temp-file stash (between the preview and the confirm click) -----------

_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def imports_dir():
    from app.config import DATA_DIR

    d = DATA_DIR / "imports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stash_plan(plan: dict) -> str:
    import uuid

    token = uuid.uuid4().hex
    (imports_dir() / f"{token}.json").write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8"
    )
    return token


def load_stashed(token: str) -> Optional[dict]:
    if not _TOKEN_RE.match(token or ""):
        return None
    path = imports_dir() / f"{token}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def discard_stashed(token: str) -> None:
    if _TOKEN_RE.match(token or ""):
        (imports_dir() / f"{token}.json").unlink(missing_ok=True)
