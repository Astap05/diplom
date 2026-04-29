"""
CheckinNorm model: нормативы стоек регистрации.
Определяет правила назначения стоек для авиакомпаний/направлений:
кол-во стоек, время открытия/закрытия регистрации, наличие бизнес-стойки.
"""

from sqlalchemy import Column, Integer, String, Boolean, Date

from app.database import Base


class CheckinNorm(Base):
    __tablename__ = "checkin_norms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    zone = Column(String(50), nullable=False, default="international")
    priority = Column(Integer, nullable=False, default=1)
    open_before_dep_min = Column(Integer, nullable=False, default=120)
    close_before_dep_min = Column(Integer, nullable=False, default=40)
    counters_count = Column(Integer, nullable=False, default=2)
    has_business_counter = Column(Boolean, nullable=False, default=False)
    business_counters_count = Column(Integer, nullable=False, default=0)
    airline_codes = Column(String(500), nullable=True)
    aircraft_type_code = Column(String(50), nullable=True)
    airport_codes = Column(String(500), nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<CheckinNorm(id={self.id}, name='{self.name}', zone='{self.zone}')>"
