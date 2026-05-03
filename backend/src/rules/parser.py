from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from dateutil import parser as dateutil_parser
from rules.models import (
    SessionData, TransactionEntry, ChangeEntry,
    SystemLogEntry, OsCommandEntry
)


def _parse_timestamp(value: str) -> datetime:
    """Parse ISO 8601 timestamp, always return UTC-aware datetime."""
    dt = dateutil_parser.parse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_transaction_log(entries: list[dict]) -> list[TransactionEntry]:
    return [
        TransactionEntry(
            timestamp=_parse_timestamp(e["timestamp"]),
            tcode=e["tcode"],
            description=e.get("description", ""),
        )
        for e in entries
    ]


def _parse_change_log(entries: list[dict]) -> list[ChangeEntry]:
    return [
        ChangeEntry(
            timestamp=_parse_timestamp(e["timestamp"]),
            table=e["table"],
            key=str(e["key"]),
            field=e["field"],
            old_value=str(e.get("old_value", "")),
            new_value=str(e.get("new_value", "")),
        )
        for e in entries
    ]


def _parse_system_log(entries: list[dict]) -> list[SystemLogEntry]:
    return [
        SystemLogEntry(
            timestamp=_parse_timestamp(e["timestamp"]),
            message=e.get("message", ""),
            type=e.get("type", ""),
        )
        for e in entries
    ]


def _parse_os_command_log(entries: list[dict]) -> list[OsCommandEntry]:
    return [
        OsCommandEntry(
            timestamp=_parse_timestamp(e["timestamp"]),
            command=e.get("command", ""),
            parameters=e.get("parameters", ""),
            executed_by=e.get("executed_by", ""),
        )
        for e in entries
    ]


def parse_session(raw: dict[str, Any]) -> SessionData:
    """
    Convert raw JSON dict into a SessionData object.
    Handles missing optional fields gracefully.
    Raises ValueError on malformed input with a descriptive message.
    """
    try:
        return SessionData(
            session_id=raw["session_id"],
            firefighter_id=raw.get("firefighter_id"),
            firefighter_user=raw["firefighter_user"],
            controller=raw["controller"],
            system=raw["system"],
            client=raw["client"],
            start_time=_parse_timestamp(raw["start_time"]),
            end_time=_parse_timestamp(raw["end_time"]),
            reason_code=raw.get("reason_code", ""),
            ticket_reference=raw.get("ticket_reference", ""),
            ticket_requester=raw.get("ticket_requester"),
            alert_source=raw.get("alert_source"),
            transaction_log=_parse_transaction_log(raw.get("transaction_log", [])),
            change_log=_parse_change_log(raw.get("change_log", [])),
            system_log=_parse_system_log(raw.get("system_log", [])),
            os_command_log=_parse_os_command_log(raw.get("os_command_log", [])),
        )
    except KeyError as e:
        raise ValueError(f"Missing required field in session JSON: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to parse session: {e}") from e