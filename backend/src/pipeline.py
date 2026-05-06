# ─────────────────────────────────────────────────────────────
# pipeline.py
# The core review pipeline as a single callable function.
# Shared between api/routes.py and eval/run_eval.py so both
# use identical logic - no divergence between UI and eval results.
# Steps: parse -> run rules -> analyze with LLM -> serialize output
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from rules.parser import parse_session
from rules.engine import run_rules
from llm.analyzer import analyze_session


async def review_session_data(raw: dict, force_llm: bool = False) -> dict:
    session = parse_session(raw)
    deterministic_findings = run_rules(session)
    result = await analyze_session(session, deterministic_findings, force_llm=force_llm)

    # Serialize Finding dataclasses to plain dicts for JSON response
    findings_serialized = [
        {
            "rule_id": f.rule_id,
            "severity": f.severity.value,
            "location": f.location,
            "description": f.description,
            "evidence": f.evidence,
        }
        for f in result["findings"]
    ]

    return {
        "session_id": session.session_id,
        "verdict": result["verdict"],
        "confidence": result["confidence"],
        "findings": findings_serialized,
        "suggested_correction": result.get("suggested_correction"),
    }