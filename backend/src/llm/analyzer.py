# ─────────────────────────────────────────────────────────────
# analyzer.py
# Orchestrates the full LLM interaction for a session review.
# Pipeline: skip check -> LLM call -> parse -> deduplicate -> override -> return
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
import re
from rules.models import Finding, Severity, SessionData, Verdict
from llm.client import call_llm
from llm.prompts import build_session_summary, SYSTEM_PROMPT
import logging

logger = logging.getLogger(__name__)

# R-016 excluded - bank change alone needs full context to judge
_ALWAYS_REJECT_RULES = {"R-003", "R-004", "R-005", "R-008", "R-010"}

# Advisory rules (R-011, R-012, R-013, R-016) never force REJECT without LLM
_HARD_REJECT_RULES = {"R-003", "R-004", "R-005", "R-008", "R-010"}


def _parse_llm_response(raw: str) -> dict:
    # Some models wrap JSON in markdown fences or return two blocks in sequence
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    # Brace counting isolates the first complete object, ignoring anything after
    brace_count = 0
    end_index = 0
    for i, char in enumerate(clean):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_index = i + 1
                break

    if end_index > 0:
        clean = clean[:end_index]

    return json.loads(clean)


def _findings_from_llm(raw_findings: list[dict]) -> list[Finding]:
    # Silently skips malformed entries rather than crashing the pipeline
    findings = []
    for f in raw_findings:
        try:
            findings.append(Finding(
                rule_id=f.get("rule_id", "R-LLM"),
                severity=Severity(f.get("severity", "medium")),
                location=f.get("location", "unknown"),
                description=f.get("description", ""),
                evidence=f.get("evidence", ""),
            ))
        except (ValueError, KeyError):
            continue
    return findings


async def analyze_session(
    session: SessionData,
    deterministic_findings: list[Finding],
    force_llm: bool = False,
) -> dict:
    # Hard rules give certain verdicts - no need to spend tokens on LLM
    # force_llm bypasses this for the UI re-analyze button
    triggered_rule_ids = {f.rule_id for f in deterministic_findings}
    if not force_llm and triggered_rule_ids & _ALWAYS_REJECT_RULES:
        return {
            "session_id": session.session_id,
            "verdict": Verdict.REJECT.value,
            "confidence": 0.99,
            "findings": deterministic_findings,
            "suggested_correction": None,
        }

    summary = build_session_summary(session, deterministic_findings)

    try:
        raw = await call_llm(summary, system=SYSTEM_PROMPT)
        parsed = _parse_llm_response(raw)
    except Exception as e:
        logger.error("LLM call failed: %s", str(e))
        return _fallback_verdict(deterministic_findings, str(e))

    llm_findings = _findings_from_llm(parsed.get("semantic_findings", []))

    # Remove LLM findings that overlap with deterministic ones by rule or location
    seen_rules = {f.rule_id for f in deterministic_findings}
    seen_locations = {f.location for f in deterministic_findings}
    llm_findings_deduped = [
        f for f in llm_findings
        if f.rule_id not in seen_rules
        and f.location not in seen_locations
    ]

    _SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_findings = sorted(
        deterministic_findings + llm_findings_deduped,
        key=lambda f: _SEVERITY_ORDER.get(f.severity.value, 99)
    )

    verdict = parsed.get("verdict", _derive_verdict(deterministic_findings))
    confidence = float(parsed.get("confidence", 0.5))
    suggested_correction = parsed.get("suggested_correction")

    # Critical deterministic findings cannot be overridden by LLM judgment
    critical = [f for f in deterministic_findings if f.severity == Severity.CRITICAL]
    if critical:
        verdict = Verdict.REJECT.value
        confidence = 0.99
        suggested_correction = None

    return {
        "session_id": session.session_id,
        "verdict": verdict,
        "confidence": confidence,
        "findings": all_findings,
        "suggested_correction": suggested_correction,
    }


def _derive_verdict(findings: list[Finding]) -> str:
    if not findings:
        return Verdict.PASS.value

    rule_ids = {f.rule_id for f in findings}
    if rule_ids & _HARD_REJECT_RULES:
        return Verdict.REJECT.value

    return Verdict.NEEDS_CORRECTION.value


def _fallback_verdict(findings: list[Finding], error: str) -> dict:
    # confidence 0.5 signals to the UI that LLM was unavailable
    return {
        "verdict": _derive_verdict(findings),
        "confidence": 0.5,
        "findings": findings,
        "suggested_correction": None,
        "llm_error": error,
    }