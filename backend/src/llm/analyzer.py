from __future__ import annotations
import json
import re
from rules.models import Finding, Severity, SessionData, Verdict
from llm.client import call_llm
from llm.prompts import build_session_summary, SYSTEM_PROMPT


def _parse_llm_response(raw: str) -> dict:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
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
) -> dict:
    """
    Send session to LLM with deterministic findings as context.
    Returns merged verdict, all findings, and suggested correction.
    """
    summary = build_session_summary(session, deterministic_findings)

    try:
        raw = await call_llm(summary, system=SYSTEM_PROMPT)
        parsed = _parse_llm_response(raw)
    except Exception as e:
        print("LLM ERROR:", str(e))
        return _fallback_verdict(deterministic_findings, str(e))

    llm_findings = _findings_from_llm(parsed.get("semantic_findings", []))
    all_findings = deterministic_findings + llm_findings

    verdict = parsed.get("verdict", _derive_verdict(deterministic_findings))
    confidence = float(parsed.get("confidence", 0.5))
    suggested_correction = parsed.get("suggested_correction")

    # Hard override: critical deterministic findings always → REJECT
    critical = [f for f in deterministic_findings if f.severity == Severity.CRITICAL]
    if critical:
        verdict = Verdict.REJECT.value
        confidence = 1.0
        suggested_correction = None

    return {
        "session_id": session.session_id,
        "verdict": verdict,
        "confidence": confidence,
        "findings": all_findings,
        "suggested_correction": suggested_correction,
    }


def _derive_verdict(findings: list[Finding]) -> str:
    """Fallback verdict based purely on deterministic findings."""
    if not findings:
        return Verdict.PASS.value
    severities = {f.severity for f in findings}
    if Severity.CRITICAL in severities:
        return Verdict.REJECT.value
    if Severity.HIGH in severities:
        return Verdict.REJECT.value
    return Verdict.NEEDS_CORRECTION.value


def _fallback_verdict(findings: list[Finding], error: str) -> dict:
    return {
        "verdict": _derive_verdict(findings),
        "confidence": 0.5,
        "findings": findings,
        "suggested_correction": None,
        "llm_error": error,
    }

