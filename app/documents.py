"""Attachment storage: the global CV and per-company recommendation letters.

Files live under data/attachments/ with a uuid filename; the original name is
kept as the Attachment.label and used when attaching to an email.
"""

from __future__ import annotations

import mimetypes
import shutil
import uuid
from pathlib import Path

from sqlmodel import Session, select

from app.config import DATA_DIR
from app.models import Attachment, AttachmentKind, AttachmentScope

ATTACH_DIR = DATA_DIR / "attachments"
ATTACH_DIR.mkdir(parents=True, exist_ok=True)


def save_upload(upload) -> tuple[str, str]:
    """Store an UploadFile; return (relative_path, original_filename)."""
    original = upload.filename or "attachment"
    ext = Path(original).suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    dest = ATTACH_DIR / stored
    with dest.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    return f"attachments/{stored}", original


def delete_file(relpath: str) -> None:
    try:
        (DATA_DIR / relpath).unlink()
    except FileNotFoundError:
        pass


def global_cv(session: Session) -> Attachment | None:
    return session.exec(
        select(Attachment).where(
            Attachment.scope == AttachmentScope.global_,
            Attachment.kind == AttachmentKind.cv,
        )
    ).first()


def company_letter(session: Session, company_id: int) -> Attachment | None:
    return session.exec(
        select(Attachment).where(
            Attachment.scope == AttachmentScope.company,
            Attachment.company_id == company_id,
            Attachment.kind == AttachmentKind.letter,
        )
    ).first()


def read_attachment(att: Attachment) -> tuple[str, str, bytes]:
    """Return (filename, mime_type, raw_bytes) for sending."""
    data = (DATA_DIR / att.path).read_bytes()
    mime = mimetypes.guess_type(att.label)[0] or "application/octet-stream"
    return att.label, mime, data
