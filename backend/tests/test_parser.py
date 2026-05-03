import json
import pytest
from pathlib import Path
from rules.parser import parse_session
from rules.models import SessionData

DATASET_DIR = Path(__file__).parent.parent.parent / "dataset_candidate" / "train" / "sessions"


def load_session(filename: str) -> dict:
    with open(DATASET_DIR / filename) as f:
        return json.load(f)


def test_parse_reject_session():
    raw = load_session("FF-TRAIN-0001.json")
    session = parse_session(raw)

    assert session.session_id == "FF-TRAIN-0001"
    assert session.firefighter_user == "MNOWAK"
    assert session.reason_code == "Updated vendor bank details and triggered payment per CHG0085389"
    assert len(session.transaction_log) == 8
    assert len(session.change_log) == 2
    assert session.transaction_log[0].tcode == "XK02"
    assert session.start_time.tzinfo is not None  # UTC-aware


def test_parse_pass_session():
    raw = load_session("FF-TRAIN-0006.json")
    session = parse_session(raw)

    assert session.session_id == "FF-TRAIN-0006"
    assert len(session.change_log) == 1
    assert session.change_log[0].table == "USR02"
    assert session.os_command_log == []


def test_parse_needs_correction_session():
    raw = load_session("FF-TRAIN-0016.json")
    session = parse_session(raw)

    assert session.session_id == "FF-TRAIN-0016"
    assert session.change_log == []
    assert len(session.transaction_log) == 16
    duration = session.end_time - session.start_time
    assert duration.total_seconds() / 3600 > 4  # over 4 hours


def test_missing_required_field_raises():
    with pytest.raises(ValueError, match="Missing required field"):
        parse_session({"session_id": "FF-TEST-BROKEN"})


def test_optional_fields_default_to_none():
    raw = load_session("FF-TRAIN-0001.json")
    session = parse_session(raw)
    # FF-TRAIN-0001 has no ticket_requester
    assert session.ticket_requester is None