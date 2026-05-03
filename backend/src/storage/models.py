from sqlalchemy import Column, String, Float, Text, DateTime
from sqlalchemy.sql import func
from storage.database import Base


class VerdictRecord(Base):
    __tablename__ = "verdicts"

    session_id = Column(String, primary_key=True)
    verdict = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    findings_json = Column(Text, nullable=False)
    suggested_correction_json = Column(Text, nullable=True)
    controller_decision = Column(String, nullable=True)
    controller_note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())