import json
import pytest
from pathlib import Path
from rules.parser import parse_session
from rules.models import Severity
from rules.catalog.extended import check_r011, check_r012, check_r013, check_r014

DATASET_DIR = Path(__file__).parent.parent.parent / "dataset_candidate" / "train" / "sessions"
TEST_DIR = Path(__file__).parent.parent.parent / "dataset_candidate" / "test" / "sessions"


def load(filename: str, base=DATASET_DIR):
    with open(base / filename) as f:
        return parse_session(json.load(f))


# ── R-011 ─────────────────────────────────────────────────────────────────────

def test_r011_custom_program_detected():
    session = load("FF-TEST-0002.json", TEST_DIR)
    findings = check_r011(session)
    assert any(f.rule_id == "R-011" for f in findings)
    assert findings[0].severity == Severity.HIGH


def test_r011_standard_tcodes_pass():
    session = load("FF-TRAIN-0006.json")
    findings = check_r011(session)
    assert findings == []


# ── R-012 ─────────────────────────────────────────────────────────────────────

def test_r012_see_ticket_detected():
    session = load("FF-TRAIN-0006.json")
    session.reason_code = "see ticket"
    findings = check_r012(session)
    assert len(findings) == 1
    assert findings[0].rule_id == "R-012"


def test_r012_proper_reason_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r012(session)
    assert findings == []


# ── R-013 ─────────────────────────────────────────────────────────────────────

def test_r013_fix_claimed_no_changes():
    session = load("FF-TRAIN-0006.json")
    session.reason_code = "Fixed urgent issue with payment run"
    session.change_log = []
    findings = check_r013(session)
    assert any(f.rule_id == "R-013" for f in findings)


def test_r013_investigation_reason_passes():
    session = load("FF-TRAIN-0016.json")
    # reason: "Investigating month-end close issue" — no changes expected
    findings = check_r013(session)
    assert findings == []


def test_r013_fix_with_changes_passes():
    session = load("FF-TRAIN-0001.json")
    # has changes in change_log
    findings = check_r013(session)
    assert findings == []


# ── R-014 ─────────────────────────────────────────────────────────────────────

def test_r014_transport_detected():
    session = load("FF-TEST-0011.json", TEST_DIR)
    findings = check_r014(session)
    assert any(f.rule_id == "R-014" for f in findings)
    assert findings[0].severity == Severity.HIGH


def test_r014_no_transport_passes():
    session = load("FF-TRAIN-0006.json")
    findings = check_r014(session)
    assert findings == []