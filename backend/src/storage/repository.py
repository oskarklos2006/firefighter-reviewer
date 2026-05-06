# ─────────────────────────────────────────────────────────────
# repository.py
# The only place in the codebase that reads or writes the database.
# All other modules call these three functions - never SQL directly.
# Findings are stored as JSON strings because SQLite has no native
# array type and we never need to query by individual finding fields.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from storage.database import SessionLocal
from storage.models import VerdictRecord


def save_verdict(result: dict) -> None:
    with SessionLocal() as db:
        record = VerdictRecord(
            session_id=result["session_id"],
            verdict=result["verdict"],
            confidence=result["confidence"],
            findings_json=json.dumps(result["findings"]),
            suggested_correction_json=json.dumps(result.get("suggested_correction")),
        )
        # merge upserts - re-analyzing a session overwrites the previous verdict
        db.merge(record)
        db.commit()


def get_all_sessions() -> list[dict]:
    with SessionLocal() as db:
        records = db.query(VerdictRecord).order_by(
            VerdictRecord.created_at.desc()
        ).all()
        return [_serialize(r) for r in records]


def update_decision(
    session_id: str,
    decision: str,
    note: str | None = None
) -> bool:
    with SessionLocal() as db:
        record = db.query(VerdictRecord).filter(
            VerdictRecord.session_id == session_id
        ).first()
        if not record:
            return False
        record.controller_decision = decision
        record.controller_note = note
        db.commit()
        return True


def _serialize(record: VerdictRecord) -> dict:
    return {
        "session_id": record.session_id,
        "verdict": record.verdict,
        "confidence": record.confidence,
        "findings": json.loads(record.findings_json),
        "suggested_correction": json.loads(record.suggested_correction_json or "null"),
        "controller_decision": record.controller_decision,
        "controller_note": record.controller_note,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }