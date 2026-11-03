"""FastAPI application entrypoint.

Wires up the app: SQLite schema + a guaranteed Settings row and seeded default
templates on startup, static files, all routers, and the settings page.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import documents
from app.config import STATIC_DIR
from app.db import engine, get_session, init_db
from app.models import LLMBackend, Settings
from app.routes_companies import router as companies_router
from app.routes_compose import router as compose_router
from app.routes_documents import router as documents_router
from app.routes_graph import router as graph_router
from app.routes_io import router as io_router
from app.routes_templates import router as templates_router
from app.seed import seed_templates
from app.templating import templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        if session.get(Settings, 1) is None:
            session.add(Settings(id=1))
            session.commit()
        seed_templates(session)
    yield


app = FastAPI(title="internship-finder", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(companies_router)
app.include_router(templates_router)
app.include_router(compose_router)
app.include_router(graph_router)
app.include_router(documents_router)
app.include_router(io_router)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: Session = Depends(get_session)):
    settings = session.get(Settings, 1)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": settings,
            "backends": list(LLMBackend),
            "cv": documents.global_cv(session),
        },
    )


@app.post("/settings")
def save_settings(
    session: Session = Depends(get_session),
    user_name: str = Form(""),
    signature: str = Form(""),
    sender_email: str = Form(""),
    email_language: str = Form("fr"),
    graph_client_id: str = Form(""),
    llm_backend: str = Form(LLMBackend.ollama.value),
    llm_model: str = Form("mistral-nemo"),
    llm_base_url: str = Form("http://localhost:11434"),
    llama_model_path: str = Form(""),
    followup_days: int = Form(7),
):
    settings = session.get(Settings, 1)
    settings.user_name = user_name
    settings.signature = signature
    settings.sender_email = sender_email
    settings.email_language = email_language
    settings.graph_client_id = graph_client_id.strip()
    settings.llm_backend = LLMBackend(llm_backend)
    settings.llm_model = llm_model
    settings.llm_base_url = llm_base_url
    settings.llama_model_path = llama_model_path.strip()
    settings.followup_days = followup_days
    session.add(settings)
    session.commit()
    return RedirectResponse(url="/settings?saved=1", status_code=303)
