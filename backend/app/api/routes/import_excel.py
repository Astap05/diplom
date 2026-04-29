"""
POST /api/v1/import-excel — импорт данных из Excel-файла практики.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.excel_parser import import_excel
from app.services.checkin_norms_seed import seed_checkin_norms
from app.services.gate_norms_seed import seed_gate_norms

router = APIRouter()


@router.post("/")
def import_excel_endpoint(force: bool = False, db: Session = Depends(get_db)):
    stats = import_excel(db, force=force)
    # При force-импорте excel_parser пересоздаёт таблицы (drop/create),
    # поэтому нормативы нужно досидить заново.
    seed_checkin_norms(db)
    seed_gate_norms(db)
    return stats
