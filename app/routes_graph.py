"""Microsoft account connection: device-code login, status, logout."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app import graph
from app.db import get_session
from app.models import Settings
from app.templating import templates

router = APIRouter()


@router.get("/graph", response_class=HTMLResponse)
def graph_page(request: Request, session: Session = Depends(get_session)):
    settings = session.get(Settings, 1)
    state = graph.device_flow_status()
    account = (
        graph.account_username(settings.graph_client_id)
        if settings.graph_client_id
        else None
    )
    return templates.TemplateResponse(
        request,
        "graph.html",
        {
            "client_id": settings.graph_client_id,
            "account": account,
            "status": state["status"],
            "flow": state["flow"],
            "error": state["error"],
        },
    )


@router.post("/graph/login")
def graph_login(session: Session = Depends(get_session)):
    settings = session.get(Settings, 1)
    if settings.graph_client_id:
        graph.start_device_flow(settings.graph_client_id)
    return RedirectResponse("/graph", status_code=303)


@router.post("/graph/logout")
def graph_logout(session: Session = Depends(get_session)):
    settings = session.get(Settings, 1)
    graph.logout(settings.graph_client_id)
    return RedirectResponse("/graph", status_code=303)
