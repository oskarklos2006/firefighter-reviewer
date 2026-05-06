from __future__ import annotations
import json
import re
from rules.models import Finding, Severity, SessionData, Verdict
from llm.client import call_llm
from llm.prompts import build_session_summary, SYSTEM_PROMPT
import logging

logger = logging.getLogger(__name__)

# Rules that guarantee REJECT with 100% certainty — skip LLM entirely
# R-016 not included — bank change alone needs LLM context judgment
_ALWAYS_REJECT_RULES = {"R-003", "R-004", "R-005", "R-008", "R-010"}


def _parse_llm_response(raw: str) -> dict:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    # Extract only the first complete JSON object
    # handles cases where LLM returns multiple JSON blocks
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
    # Skip LLM if deterministic rules already give certain REJECT
    # unless force_llm is True
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

    # Hard override: critical deterministic findings always → REJECT
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


# Only these rules can force REJECT in fallback mode
_HARD_REJECT_RULES = {"R-003", "R-004", "R-005", "R-008", "R-010"}


def _derive_verdict(findings: list[Finding]) -> str:
    """Fallback verdict based purely on deterministic findings."""
    if not findings:
        return Verdict.PASS.value

    rule_ids = {f.rule_id for f in findings}

    # Only hard rules force REJECT
    if rule_ids & _HARD_REJECT_RULES:
        return Verdict.REJECT.value

    # Everything else → NEEDS_CORRECTION if there are findings
    return Verdict.NEEDS_CORRECTION.value


def _fallback_verdict(findings: list[Finding], error: str) -> dict:
    return {
        "verdict": _derive_verdict(findings),
        "confidence": 0.5,
        "findings": findings,
        "suggested_correction": None,
        "llm_error": error,
    }

