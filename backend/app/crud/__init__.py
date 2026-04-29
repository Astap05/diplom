"""
CRUD (Create, Read, Update, Delete) operations for the RMS.
Each module encapsulates database access for one entity.
"""

from app.crud import flight as crud_flight
from app.crud import resource as crud_resource

__all__ = ["crud_flight", "crud_resource"]
