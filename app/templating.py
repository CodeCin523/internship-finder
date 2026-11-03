"""Shared Jinja2 templates object + custom filters.

Kept separate from main.py so route modules can import it without a circular
dependency on the app instance.
"""

from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _fmt_dt(value) -> str:
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M")


def _label(value) -> str:
    """'in_conversation' -> 'In Conversation'."""
    return str(value).replace("_", " ").title()


templates.env.filters["dt"] = _fmt_dt
templates.env.filters["label"] = _label
