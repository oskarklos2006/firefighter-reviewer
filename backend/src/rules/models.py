# ─────────────────────────────────────────────────────────────
# models.py
# Internal data structures used throughout the pipeline.
# These are plain Python dataclasses - not Pydantic models.
# Pydantic is used only at the API boundary (api/schemas.py).
# Keeping them separate prevents coupling rule logic to HTTP concerns.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# Inheriting from str allows direct JSON serialization without a custom encoder
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Verdict(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"


# One compliance issue detected by a rule or the LLM
@dataclass
class Finding:
    rule_id: str
    severity: Severity
    location: str
    description: str
    evidence: str


# Log entry types - one per log array in the session JSON

@dataclass
class TransactionEntry:
    timestamp: datetime
    tcode: str
    description: str


@dataclass
class ChangeEntry:
    timestamp: datetime
    table: str
    key: str
    field: str
    old_value: str
    new_value: str


@dataclass
class SystemLogEntry:
    timestamp: datetime
    message: str
    type: str


@dataclass
class OsCommandEntry:
    timestamp: datetime
    command: str
    parameters: str
    executed_by: str


# The full parsed session - passed through the entire pipeline.
# Optional fields at the bottom because not all sessions include them.
@dataclass
class SessionData:
    session_id: str
    firefighter_user: str
    controller: str
    system: str
    client: str
    start_time: datetime
    end_time: datetime
    reason_code: str
    ticket_reference: str
    transaction_log: list[TransactionEntry] = field(default_factory=list)
    change_log: list[ChangeEntry] = field(default_factory=list)
    system_log: list[SystemLogEntry] = field(default_factory=list)
    os_command_log: list[OsCommandEntry] = field(default_factory=list)
    firefighter_id: Optional[str] = None
    ticket_requester: Optional[str] = None
    alert_source: Optional[str] = None