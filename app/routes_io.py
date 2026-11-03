"""Import/export routes.

(A) xlsx export mirrors the user's own spreadsheet format. (B) the AI-assisted
import is the reverse: upload a sheet, review what will be created/updated on a
preview screen, then approve. Nothing is written to the database until the user
clicks through the review — same gate the email flow uses.
"""

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import Session

from app import importer
from app.db import get_session
from app.exporter import build_workbook
from app.models import Settings
from app.templating import templates

router = APIRouter()

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/export")
def export_xlsx(session: Session = Depends(get_session)):
    data = build_workbook(session)
    filename = f"internship-finder-{date.today().isoformat()}.xlsx"
    return Response(
        content=data,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/import", response_class=HTMLResponse)
def import_form(request: Request):
    return templates.TemplateResponse(
        request, "import.html", {"error": request.query_params.get("error", "")}
    )


@router.post("/import", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    session: Session = Depends(get_session),
    file: UploadFile = File(...),
):
    data = await file.read()
    try:
        plan = importer.build_plan(data, file.filename or "upload.xlsx", session.get(Settings, 1))
    except importer.ImportError_ as exc:
        return templates.TemplateResponse(
            request, "import.html", {"error": str(exc)}, status_code=400
        )
    if not plan["companies"]:
        return templates.TemplateResponse(
            request,
            "import.html",
            {"error": "No companies were found in that sheet. Check the column headers."},
            status_code=400,
        )
    token = importer.stash_plan(plan)
    return templates.TemplateResponse(
        request,
        "import_preview.html",
        {"summary": importer.plan_summary(session, plan), "token": token},
    )


@router.post("/import/confirm")
def import_confirm(
    session: Session = Depends(get_session),
    token: str = Form(...),
):
    plan = importer.load_stashed(token)
    if plan is None:
        return RedirectResponse(
            "/import?error=" + quote("That import expired. Please upload the file again."),
            status_code=303,
        )
    result = importer.commit_plan(session, plan)
    importer.discard_stashed(token)
    params = "&".join(f"{k}={v}" for k, v in result.items())
    return RedirectResponse(f"/?imported=1&{params}", status_code=303)


@router.post("/import/cancel")
def import_cancel(token: str = Form(...)):
    importer.discard_stashed(token)
    return RedirectResponse("/import", status_code=303)
