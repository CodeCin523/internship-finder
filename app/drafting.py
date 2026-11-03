"""Template rendering: fill a template's {placeholders} from company data.

Unknown placeholders are left visible (e.g. `{foo}`) rather than crashing, so a
typo in a template is obvious in the review screen instead of 500-ing.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.models import Company, Contact, Settings, Template, TemplateCategory

PLACEHOLDERS = [
    "{company}",
    "{contact_name}",
    "{contact_role}",
    "{my_name}",
    "{signature}",
    "{date}",
]


class _SafeDict(dict):
    def __missing__(self, key):  # leave unknown placeholders in place
        return "{" + key + "}"


def build_context(
    company: Company, contact: Contact | None, settings: Settings
) -> _SafeDict:
    return _SafeDict(
        {
            "company": company.name,
            "contact_name": contact.name if contact else "Madame, Monsieur",
            "contact_role": contact.role if (contact and contact.role) else "",
            "my_name": settings.user_name or "",
            "signature": settings.signature or "",
            "date": date.today().strftime("%d/%m/%Y"),
        }
    )


def _safe_format(text: str, ctx: _SafeDict) -> str:
    try:
        return text.format_map(ctx)
    except (ValueError, IndexError):
        # Malformed format string (stray brace) — return as-is.
        return text


def render_template(
    template: Template, company: Company, contact: Contact | None, settings: Settings
) -> tuple[str, str]:
    ctx = build_context(company, contact, settings)
    return _safe_format(template.subject, ctx), _safe_format(template.body, ctx)


def grouped_templates(session: Session) -> dict[TemplateCategory, list[Template]]:
    """All active templates, grouped by category in a stable order."""
    rows = session.exec(
        select(Template)
        .where(Template.is_active == True)  # noqa: E712
        .order_by(Template.name)
    ).all()
    grouped: dict[TemplateCategory, list[Template]] = {c: [] for c in TemplateCategory}
    for t in rows:
        grouped[t.category].append(t)
    return grouped
