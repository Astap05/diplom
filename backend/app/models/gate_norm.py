"""GateNorm model: нормативы выходов на посадку."""

from sqlalchemy import Column, Integer, String, Boolean, Date

from app.database import Base


class GateNorm(Base):
    __tablename__ = "gate_norms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    zone = Column(String(50), nullable=False, default="international")
    priority = Column(Integer, nullable=False, default=1)
    open_before_dep_min = Column(Integer, nullable=False, default=40)
    close_before_dep_min = Column(Integer, nullable=False, default=15)
    gates_count = Column(Integer, nullable=False, default=1)
    airline_codes = Column(String(500), nullable=True)
    aircraft_type_code = Column(String(50), nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<GateNorm(id={self.id}, name='{self.name}', zone='{self.zone}')>"
