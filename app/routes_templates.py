"""Template library CRUD, grouped by category."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.db import get_session
from app.drafting import PLACEHOLDERS, grouped_templates
from app.models import Template, TemplateCategory
from app.templating import templates

router = APIRouter()


def _get_template(session: Session, template_id: int) -> Template:
    tmpl = session.get(Template, template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpl


@router.get("/templates", response_class=HTMLResponse)
def templates_list(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request, "templates_list.html", {"grouped": grouped_templates(session)}
    )


@router.get("/templates/new", response_class=HTMLResponse)
def template_new(request: Request):
    return templates.TemplateResponse(
        request,
        "template_form.html",
        {
            "template": None,
            "categories": list(TemplateCategory),
            "placeholders": PLACEHOLDERS,
            "action_url": "/templates",
        },
    )


@router.post("/templates")
def template_create(
    session: Session = Depends(get_session),
    name: str = Form(...),
    category: str = Form(...),
    language: str = Form("fr"),
    subject: str = Form(""),
    body: str = Form(""),
):
    session.add(
        Template(
            name=name.strip(),
            category=TemplateCategory(category),
            language=language,
            subject=subject,
            body=body,
        )
    )
    session.commit()
    return RedirectResponse("/templates", status_code=303)


@router.get("/templates/{template_id}/edit", response_class=HTMLResponse)
def template_edit_form(
    template_id: int, request: Request, session: Session = Depends(get_session)
):
    tmpl = _get_template(session, template_id)
    return templates.TemplateResponse(
        request,
        "template_form.html",
        {
            "template": tmpl,
            "categories": list(TemplateCategory),
            "placeholders": PLACEHOLDERS,
            "action_url": f"/templates/{tmpl.id}/edit",
        },
    )


@router.post("/templates/{template_id}/edit")
def template_update(
    template_id: int,
    session: Session = Depends(get_session),
    name: str = Form(...),
    category: str = Form(...),
    language: str = Form("fr"),
    subject: str = Form(""),
    body: str = Form(""),
):
    tmpl = _get_template(session, template_id)
    tmpl.name = name.strip()
    tmpl.category = TemplateCategory(category)
    tmpl.language = language
    tmpl.subject = subject
    tmpl.body = body
    session.add(tmpl)
    session.commit()
    return RedirectResponse("/templates", status_code=303)


@router.post("/templates/{template_id}/delete")
def template_delete(template_id: int, session: Session = Depends(get_session)):
    tmpl = _get_template(session, template_id)
    session.delete(tmpl)
    session.commit()
    return RedirectResponse("/templates", status_code=303)
