# ─────────────────────────────────────────────────────────────
# parser.py
# Converts raw session JSON dicts into typed SessionData objects.
# This is the only place that touches raw dict keys - everything
# downstream works with typed dataclasses.
# Handles real-world SAP log quirks:
#   - timestamps without timezone info (assumes UTC)
#   - integer keys in change_log (SAP sometimes sends numbers)
#   - missing optional fields (ticket_requester, alert_source)
#   - out-of-order log entries (sorted by timestamp after parsing)
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from dateutil import parser as dateutil_parser
from rules.models import (
    SessionData, TransactionEntry, ChangeEntry,
    SystemLogEntry, OsCommandEntry
)


def _parse_timestamp(value: str) -> datetime:
    # dateutil handles timezone variants and missing milliseconds
    # that datetime.fromisoformat would reject
    dt = dateutil_parser.parse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_transaction_log(entries: list[dict]) -> list[TransactionEntry]:
    return sorted([
        TransactionEntry(
            timestamp=_parse_timestamp(e["timestamp"]),
            tcode=e["tcode"],
            description=e.get("description", ""),
        )
        for e in entries
    ], key=lambda x: x.timestamp)


def _parse_change_log(entries: list[dict]) -> list[ChangeEntry]:
    return sorted([
        ChangeEntry(
            timestamp=_parse_timestamp(e["timestamp"]),
            table=e["table"],
            key=str(e["key"]),          # SAP sometimes sends integers
            field=e["field"],
            old_value=str(e.get("old_value", "")),
            new_value=str(e.get("new_value", "")),
        )
        for e in entries
    ], key=lambda x: x.timestamp)


def _parse_system_log(entries: list[dict]) -> list[SystemLogEntry]:
    return sorted([
        SystemLogEntry(
            timestamp=_parse_timestamp(e["timestamp"]),
            message=e.get("message", ""),
            type=e.get("type", ""),
        )
        for e in entries
    ], key=lambda x: x.timestamp)


def _parse_os_command_log(entries: list[dict]) -> list[OsCommandEntry]:
    return sorted([
        OsCommandEntry(
            timestamp=_parse_timestamp(e["timestamp"]),
            command=e.get("command", ""),
            parameters=e.get("parameters", ""),
            executed_by=e.get("executed_by", ""),
        )
        for e in entries
    ], key=lambda x: x.timestamp)


def parse_session(raw: dict[str, Any]) -> SessionData:
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