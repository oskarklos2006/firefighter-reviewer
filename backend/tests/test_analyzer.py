# ─────────────────────────────────────────────────────────────
# test_analyzer.py
# Integration tests for the full LLM pipeline.
# Marked @llm so they are excluded from the standard test suite:
#   pytest tests/ -m "not llm"   - fast, no API calls
#   pytest tests/ -m "llm"       - slow, requires LLM_API_KEY
# 30 second sleep between tests avoids free tier rate limits.
# ─────────────────────────────────────────────────────────────

import pytest
import asyncio
import json
from pathlib import Path
from rules.parser import parse_session
from rules.engine import run_rules
from llm.analyzer import analyze_session

DATASET_DIR = Path(__file__).parent.parent.parent / "dataset_candidate" / "train" / "sessions"


def load(filename: str):
    with open(DATASET_DIR / filename) as f:
        return parse_session(json.load(f))


@pytest.mark.llm
@pytest.mark.asyncio
async def test_analyze_reject_session():
    await asyncio.sleep(30)
    session = load("FF-TRAIN-0001.json")
    findings = run_rules(session)
    result = await analyze_session(session, findings)
    assert result["verdict"] == "REJECT"
    assert result["confidence"] > 0.7
    assert len(result["findings"]) >= 2


@pytest.mark.llm
@pytest.mark.asyncio
async def test_analyze_pass_session():
    await asyncio.sleep(30)
    session = load("FF-TRAIN-0006.json")
    findings = run_rules(session)
    result = await analyze_session(session, findings)
    assert result["verdict"] == "PASS"


@pytest.mark.llm
@pytest.mark.asyncio
async def test_analyze_needs_correction_session():
    await asyncio.sleep(30)
    session = load("FF-TRAIN-0016.json")
    findings = run_rules(session)
    result = await analyze_session(session, findings)
    assert result["verdict"] == "NEEDS_CORRECTION"
    # suggested_correction is only present when LLM responded successfully
    if "llm_error" not in result:
        assert result["suggested_correction"] is not None