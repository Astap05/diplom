"""
API route modules. Import and include in main app.
"""

from fastapi import APIRouter
from app.api.routes import (
    flights,
    resources,
    allocate,
    allocations,
    import_xml,
    import_excel,
    checkin_norms,
    gate_norms,
    distribution,
    breakdowns,
)

api_router = APIRouter()

api_router.include_router(flights.router, prefix="/flights", tags=["flights"])
api_router.include_router(resources.router, prefix="/resources", tags=["resources"])
api_router.include_router(allocate.router, prefix="/allocate", tags=["allocation"])
api_router.include_router(allocations.router, prefix="/allocations", tags=["allocations"])
api_router.include_router(import_xml.router, prefix="/import-xml", tags=["import"])
api_router.include_router(import_excel.router, prefix="/import-excel", tags=["import-excel"])
api_router.include_router(checkin_norms.router, prefix="/checkin-norms", tags=["checkin-norms"])
api_router.include_router(gate_norms.router, prefix="/gate-norms", tags=["gate-norms"])
api_router.include_router(distribution.router, prefix="/distribution", tags=["distribution"])
api_router.include_router(breakdowns.router, prefix="/breakdowns", tags=["breakdowns"])
