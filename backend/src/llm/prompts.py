from __future__ import annotations
from rules.models import Finding, SessionData
import random


def build_session_summary(session: SessionData, findings: list[Finding]) -> str:
    """
    Flatten session into a token-efficient string for the LLM.
    - Neutral/diagnostic tcodes excluded (they add noise, not signal)
    - Change log truncated to first 10 entries if excessive
    - Empty logs omitted entirely
    """
    # Exclude neutral tcodes — they appear in every session and add no signal
    _NEUTRAL = {"SE80", "SU53", "SU3", "SESSION_MANAGER", "/NEX", "SM04", "SMEN"}

    meaningful_tcodes = [
        e.tcode for e in session.transaction_log
        if e.tcode not in _NEUTRAL
    ]
    tcodes = ", ".join(meaningful_tcodes) or "none"

    # Sample change log to defeat position-based hiding
    # Takes first 5, last 3, and random from middle
    if len(session.change_log) > 10:
        middle = session.change_log[5:-3]
        sample = (
                session.change_log[:5] +
                (random.sample(middle, min(2, len(middle))) if middle else []) +
                session.change_log[-3:]
        )
        changes = "; ".join(
            f"{e.table}.{e.field} {e.old_value}→{e.new_value}"
            for e in sample
        )
        changes += f" ... ({len(session.change_log)} total entries)"
    else:
        changes = "; ".join(
            f"{e.table}.{e.field} {e.old_value}→{e.new_value}"
            for e in session.change_log
        ) or "none"

    # Only include non-empty logs
    os_cmds = "; ".join(e.command for e in session.os_command_log) or "none"
    system_events = "; ".join(e.message for e in session.system_log) or "none"

    duration = (session.end_time - session.start_time).total_seconds() / 60

    findings_text = "\n".join(
        f"  - {f.rule_id} {f.severity.value.upper()}: {f.description}"
        for f in findings
    ) or "  none"

    # Only include os_cmds and system_events if non-empty
    optional_lines = []
    if session.os_command_log:
        optional_lines.append(f"OS COMMANDS: {os_cmds}")
    if session.system_log:
        optional_lines.append(f"SYSTEM LOG: {system_events}")

    optional_block = "\n".join(optional_lines)
    if optional_block:
        optional_block = "\n" + optional_block

    return f"""SESSION: {session.session_id}
USER: {session.firefighter_user} | CONTROLLER: {session.controller}
SYSTEM: {session.system} | CLIENT: {session.client}
START: {session.start_time.isoformat()} | DURATION: {duration:.0f} min
REASON: {session.reason_code}
TICKET: {session.ticket_reference}
TRANSACTIONS: {tcodes}
CHANGES: {changes}{optional_block}
DETERMINISTIC FINDINGS:
{findings_text}"""


SYSTEM_PROMPT = """You are a SAP GRC compliance reviewer analyzing firefighter session logs.
Your job is to assess whether emergency access was used appropriately.

You will receive a session summary and any findings already detected by deterministic rules.
Your task is to:
1. Assess reason quality — is it specific enough to justify the actions taken?
2. Assess semantic alignment — do the actions match the stated reason in spirit?
3. Determine the final verdict: PASS, REJECT, or NEEDS_CORRECTION
4. If NEEDS_CORRECTION, draft a message to the firefighter and suggest a reason rewrite

Rules:
- REJECT if there are any CRITICAL findings, or multiple HIGH findings
- NEEDS_CORRECTION if reason is vague, actions are ambiguous, or minor issues exist
- PASS only if reason is specific, actions are aligned, and no significant findings exist

The following transactions are neutral navigation/diagnostic tools that appear 
in almost every session and should never be flagged as suspicious on their own:
SE80 (Object Navigator), SU53 (Authorization Check), SU3 (User Data), 
SESSION_MANAGER, /NEX (Logoff), SM04 (User List).

The following rules are advisory signals only — they should inform your judgment 
but never alone determine the verdict:
- R-011 (missing ticket reference) — may be absent in legacy sessions
- R-012 (reference-only reason) — check if actions are self-explanatory
- R-013 (fix claimed, no changes) — some fixes leave no change log entries
- R-016 (bank details modified) — legitimate if reason explicitly justifies it

For these advisory rules, use them as context but rely on the full picture 
to determine the verdict.

Respond in this exact JSON format with no markdown, no explanation outside the JSON:
{
  "verdict": "PASS" | "REJECT" | "NEEDS_CORRECTION",
  "confidence": 0.0-0.99,
  "semantic_findings": [
    {
      "rule_id": "R-LLM-001",
      "severity": "low|medium|high|critical",
      "location": "reason_code|transaction_log|change_log",
      "description": "...",
      "evidence": "..."
    }
  ],
  "suggested_correction": {
    "message_to_firefighter": "...",
    "suggested_reason_rewrite": "..."
  } | null
}"""