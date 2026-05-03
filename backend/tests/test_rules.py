import json
import pytest
from pathlib import Path
from rules.parser import parse_session
from rules.models import Severity
from rules.catalog.dangerous_actions import check_r003, check_r004, check_r005
from rules.catalog.access_control import check_r008, check_r010
from rules.catalog.volume_timing import check_r006, check_r007, check_r009
from rules.catalog.reason_quality import check_r001, check_r002
from rules.engine import run_rules

DATASET_DIR = Path(__file__).parent.parent.parent / "dataset_candidate" / "train" / "sessions"


def load(filename: str):
    with open(DATASET_DIR / filename) as f:
        return parse_session(json.load(f))


# ── R-001 ────────────────────────────────────────────────────────────────────

def test_r001_empty_reason():
    session = load("FF-TRAIN-0001.json")
    session.reason_code = ""
    findings = check_r001(session)
    assert len(findings) == 1
    assert findings[0].rule_id == "R-001"


def test_r001_short_reason():
    session = load("FF-TRAIN-0001.json")
    session.reason_code = "fix"
    findings = check_r001(session)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM


def test_r001_generic_reason():
    session = load("FF-TRAIN-0001.json")
    session.reason_code = "production issue"
    findings = check_r001(session)
    assert len(findings) == 1


def test_r001_good_reason_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r001(session)
    assert findings == []


# ── R-002 ────────────────────────────────────────────────────────────────────

def test_r002_reason_mentions_user_but_fi_tcodes():
    session = load("FF-TRAIN-0001.json")
    session.reason_code = "Reset user lock for HR consultant"
    findings = check_r002(session)
    assert any(f.rule_id == "R-002" for f in findings)


def test_r002_aligned_reason_passes():
    session = load("FF-TRAIN-0001.json")
    # reason mentions vendor, tcodes are XK02/FK02 — aligned
    findings = check_r002(session)
    assert findings == []


# ── R-003 ────────────────────────────────────────────────────────────────────

def test_r003_debug_detected():
    session = load("FF-TRAIN-0001.json")
    from rules.models import SystemLogEntry
    from datetime import datetime, timezone
    session.system_log = [
        SystemLogEntry(
            timestamp=datetime(2026, 5, 12, 13, 0, tzinfo=timezone.utc),
            message="Variable value changed in debug mode (/h replace): WRBTR 50000.00 -> 5000.00",
            type="SM21",
        )
    ]
    findings = check_r003(session)
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL


def test_r003_no_debug_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r003(session)
    assert findings == []


# ── R-004 ────────────────────────────────────────────────────────────────────

def test_r004_se16n_detected():
    session = load("FF-TRAIN-0004.json")
    findings = check_r004(session)
    assert any(f.rule_id == "R-004" for f in findings)
    assert findings[0].severity == Severity.HIGH


def test_r004_clean_session_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r004(session)
    assert findings == []


# ── R-005 ────────────────────────────────────────────────────────────────────

def test_r005_os_command_detected():
    session = load("FF-TRAIN-0001.json")
    from rules.models import OsCommandEntry
    from datetime import datetime, timezone
    session.os_command_log = [
        OsCommandEntry(
            timestamp=datetime(2026, 5, 12, 13, 0, tzinfo=timezone.utc),
            command="ZSH_SCRIPT rm -rf /tmp/sapdumps/",
            parameters="",
            executed_by="MNOWAK",
        )
    ]
    findings = check_r005(session)
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL
    assert "destructive" in findings[0].description


def test_r005_empty_log_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r005(session)
    assert findings == []


# ── R-006 ────────────────────────────────────────────────────────────────────

def test_r006_mass_changes_single_item_claim():
    session = load("FF-TRAIN-0004.json")
    findings = check_r006(session)
    assert any(f.rule_id == "R-006" for f in findings)
    assert findings[0].severity == Severity.HIGH


def test_r006_single_change_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r006(session)
    assert findings == []


# ── R-007 ────────────────────────────────────────────────────────────────────

def test_r007_after_hours_no_emergency():
    session = load("FF-TRAIN-0004.json")
    # starts at 22:06 UTC, reason has no emergency keywords
    findings = check_r007(session)
    assert any(f.rule_id == "R-007" for f in findings)


def test_r007_business_hours_passes():
    session = load("FF-TRAIN-0006.json")
    # starts at 11:39 UTC
    findings = check_r007(session)
    assert findings == []


# ── R-008 ────────────────────────────────────────────────────────────────────

def test_r008_self_approval_detected():
    session = load("FF-TRAIN-0001.json")
    session.ticket_requester = session.firefighter_user
    findings = check_r008(session)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH


def test_r008_different_requester_passes():
    session = load("FF-TRAIN-0001.json")
    session.ticket_requester = "SOMEONE_ELSE"
    findings = check_r008(session)
    assert findings == []


def test_r008_no_requester_field_passes():
    session = load("FF-TRAIN-0001.json")
    session.ticket_requester = None
    findings = check_r008(session)
    assert findings == []


# ── R-009 ────────────────────────────────────────────────────────────────────

def test_r009_long_session_detected():
    session = load("FF-TRAIN-0016.json")
    findings = check_r009(session)
    assert any(f.rule_id == "R-009" for f in findings)
    assert findings[0].severity == Severity.MEDIUM


def test_r009_short_session_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r009(session)
    assert findings == []


# ── R-010 ────────────────────────────────────────────────────────────────────

def test_r010_sod_violation_detected():
    session = load("FF-TRAIN-0001.json")
    # has XK02, FK02, F110 — classic SoD violation
    findings = check_r010(session)
    assert any(f.rule_id == "R-010" for f in findings)
    assert findings[0].severity == Severity.CRITICAL


def test_r010_clean_session_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r010(session)
    assert findings == []


# ── Engine integration ────────────────────────────────────────────────────────

def test_engine_reject_session_has_critical_findings():
    session = load("FF-TRAIN-0001.json")
    findings = run_rules(session)
    severities = {f.severity for f in findings}
    assert Severity.CRITICAL in severities


def test_engine_pass_session_has_no_findings():
    session = load("FF-TRAIN-0006.json")
    findings = run_rules(session)
    assert findings == []


def test_engine_findings_sorted_by_severity():
    session = load("FF-TRAIN-0001.json")
    findings = run_rules(session)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    values = [order[f.severity.value] for f in findings]
    assert values == sorted(values)