"""SQLModel tables and enums.

The core of the app is the per-company **timeline** (`TimelineEvent`): a running
log of every interaction, outbound or inbound, automatic or manual. "Did they
reply?" is a view over this log, never a single boolean.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Enums -----------------------------------------------------------------

class PipelineStatus(str, Enum):
    lead = "lead"
    contacted = "contacted"
    in_conversation = "in_conversation"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    ghosted = "ghosted"


class TemplateCategory(str, Enum):
    first_contact = "first_contact"
    follow_up = "follow_up"
    re_contact = "re_contact"


class EventType(str, Enum):
    outbound_email = "outbound_email"
    inbound_email = "inbound_email"
    manual_note = "manual_note"
    call = "call"
    application = "application"  # applied via a portal (Workday, company site…)
    other = "other"
    status_change = "status_change"


class EventStatus(str, Enum):
    pending = "pending"    # draft awaiting your approval
    sent = "sent"
    received = "received"
    logged = "logged"      # manual entries


class LLMBackend(str, Enum):
    ollama = "ollama"
    llama_cpp = "llama_cpp"


class AttachmentKind(str, Enum):
    cv = "cv"
    letter = "letter"


class AttachmentScope(str, Enum):
    global_ = "global"
    company = "company"


# --- Singleton settings ----------------------------------------------------

class Settings(SQLModel, table=True):
    """Single-row configuration (always id=1)."""

    id: Optional[int] = Field(default=1, primary_key=True)
    user_name: str = ""
    signature: str = ""
    sender_email: str = ""
    email_language: str = "fr"

    # Microsoft Graph (filled in at M3)
    graph_client_id: str = ""

    # Local LLM
    llm_backend: LLMBackend = LLMBackend.ollama
    llm_model: str = "mistral-nemo"
    llm_base_url: str = "http://localhost:11434"
    llama_model_path: str = ""  # path to a .gguf for the llama-cpp backend

    # Follow-up cadence (days of silence before a relance is suggested)
    followup_days: int = 7


# --- Core domain -----------------------------------------------------------

class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    domain: str = ""  # web/email domain, e.g. acme.com (auto-filled from an email)
    status: PipelineStatus = Field(default=PipelineStatus.lead)
    notes: str = ""
    followup_days_override: Optional[int] = None
    created_at: datetime = Field(default_factory=_now)

    emails: list["CompanyEmail"] = Relationship(back_populates="company")
    variants: list["NameVariant"] = Relationship(back_populates="company")
    contacts: list["Contact"] = Relationship(back_populates="company")
    events: list["TimelineEvent"] = Relationship(back_populates="company")
    attachments: list["Attachment"] = Relationship(back_populates="company")


class CompanyEmail(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    address: str
    is_primary: bool = False

    company: Optional[Company] = Relationship(back_populates="emails")


class NameVariant(SQLModel, table=True):
    """Alternate spellings of a company name, used to match inbound replies."""

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    variant: str

    company: Optional[Company] = Relationship(back_populates="variants")


class Contact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    name: str
    role: str = ""
    email: str = ""
    phone: str = ""
    notes: str = ""

    company: Optional[Company] = Relationship(back_populates="contacts")


class Template(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: TemplateCategory = Field(default=TemplateCategory.first_contact)
    language: str = "fr"
    subject: str = ""
    body: str = ""          # contains {placeholders}
    is_active: bool = True


class TimelineEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    contact_id: Optional[int] = Field(default=None, foreign_key="contact.id")
    template_id: Optional[int] = Field(default=None, foreign_key="template.id")

    type: EventType = Field(default=EventType.manual_note)
    status: EventStatus = Field(default=EventStatus.logged)
    created_at: datetime = Field(default_factory=_now)

    subject: str = ""
    body: str = ""

    # Graph threading / dedup (filled at M3/M4)
    graph_message_id: Optional[str] = None
    graph_conversation_id: Optional[str] = None

    company: Optional[Company] = Relationship(back_populates="events")


class Attachment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    scope: AttachmentScope = Field(default=AttachmentScope.global_)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    kind: AttachmentKind = Field(default=AttachmentKind.cv)
    label: str = ""
    path: str = ""          # relative to DATA_DIR

    company: Optional[Company] = Relationship(back_populates="attachments")
