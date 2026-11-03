"""Uploads: the global CV (Settings) and per-company recommendation letters."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app import documents
from app.db import get_session
from app.models import Attachment, AttachmentKind, AttachmentScope

router = APIRouter()


@router.post("/settings/cv")
def upload_cv(
    session: Session = Depends(get_session), file: UploadFile = File(...)
):
    existing = documents.global_cv(session)
    if existing is not None:
        documents.delete_file(existing.path)
        session.delete(existing)
        session.commit()
    relpath, name = documents.save_upload(file)
    session.add(
        Attachment(
            scope=AttachmentScope.global_,
            kind=AttachmentKind.cv,
            label=name,
            path=relpath,
        )
    )
    session.commit()
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/companies/{company_id}/letter")
def upload_letter(
    company_id: int,
    session: Session = Depends(get_session),
    file: UploadFile = File(...),
):
    existing = documents.company_letter(session, company_id)
    if existing is not None:
        documents.delete_file(existing.path)
        session.delete(existing)
        session.commit()
    relpath, name = documents.save_upload(file)
    session.add(
        Attachment(
            scope=AttachmentScope.company,
            company_id=company_id,
            kind=AttachmentKind.letter,
            label=name,
            path=relpath,
        )
    )
    session.commit()
    return RedirectResponse(f"/companies/{company_id}", status_code=303)


@router.post("/attachments/{attachment_id}/delete")
def delete_attachment(attachment_id: int, session: Session = Depends(get_session)):
    att = session.get(Attachment, attachment_id)
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    documents.delete_file(att.path)
    scope, company_id = att.scope, att.company_id
    session.delete(att)
    session.commit()
    if scope == AttachmentScope.company and company_id:
        return RedirectResponse(f"/companies/{company_id}", status_code=303)
    return RedirectResponse("/settings", status_code=303)
