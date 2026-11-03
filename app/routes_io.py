"""Import/export routes. (A): xlsx export. The AI-assisted import follows in (B)."""

from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import Session

from app.db import get_session
from app.exporter import build_workbook

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
