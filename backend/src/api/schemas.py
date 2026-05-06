from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Optional


class TransactionEntrySchema(BaseModel):
    timestamp: str
    tcode: str
    description: str = ""


class ChangeEntrySchema(BaseModel):
    timestamp: str
    table: str
    key: str | int
    field: str
    old_value: str | int | None = ""
    new_value: str | int | None = ""


class SystemLogEntrySchema(BaseModel):
    timestamp: str
    message: str = ""
    type: str = ""


class OsCommandEntrySchema(BaseModel):
    timestamp: str
    command: str = ""
    parameters: str = ""
    executed_by: str = ""


class SessionSchema(BaseModel):
    session_id: str
    firefighter_id: Optional[str] = None
    firefighter_user: str
    controller: str
    system: str
    client: str
    start_time: str
    end_time: str
    reason_code: str = ""
    ticket_reference: str = ""
    ticket_requester: Optional[str] = None
    alert_source: Optional[str] = None
    transaction_log: list[TransactionEntrySchema] = []
    change_log: list[ChangeEntrySchema] = []
    system_log: list[SystemLogEntrySchema] = []
    os_command_log: list[OsCommandEntrySchema] = []

    @field_validator("session_id", "firefighter_user", "controller")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v