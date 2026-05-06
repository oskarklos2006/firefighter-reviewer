# ─────────────────────────────────────────────────────────────
# prompts.py
# Builds the LLM input from session data and defines the system prompt.
# Two responsibilities:
#   - build_session_summary: flattens SessionData into token-efficient text
#   - SYSTEM_PROMPT: instructs the LLM on its role and output format
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from rules.models import Finding, SessionData
import random

# Tcodes that appear in virtually every session regardless of activity.
# Including them in the LLM summary adds noise without adding signal.
_NEUTRAL_TCODES = {"SE80", "SU53", "SU3", "SESSION_MANAGER", "/NEX", "SM04", "SMEN"}


def build_session_summary(session: SessionData, findings: list[Finding]) -> str:
    meaningful_tcodes = [
        e.tcode for e in session.transaction_log
        if e.tcode not in _NEUTRAL_TCODES
    ]
    tcodes = ", ".join(meaningful_tcodes) or "none"

    # Sample across beginning, middle, and end rather than taking first N.
    # A simple head-truncation would allow an attacker to hide malicious changes
    # after position 10 by front-loading innocent ones.
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

    duration = (session.end_time - session.start_time).total_seconds() / 60

    findings_text = "\n".join(
        f"  - {f.rule_id} {f.severity.value.upper()}: {f.description}"
        for f in findings
    ) or "  none"

    # OS commands and system log are rare - only include when present
    optional_lines = []
    if session.os_command_log:
        os_cmds = "; ".join(e.command for e in session.os_command_log)
        optional_lines.append(f"OS COMMANDS: {os_cmds}")
    if session.system_log:
        system_events = "; ".join(e.message for e in session.system_log)
        optional_lines.append(f"SYSTEM LOG: {system_events}")

    optional_block = "\n" + "\n".join(optional_lines) if optional_lines else ""

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
1. Assess reason quality - is it specific enough to justify the actions taken?
2. Assess semantic alignment - do the actions match the stated reason in spirit?
3. Determine the final verdict: PASS, REJECT, or NEEDS_CORRECTION
4. If NEEDS_CORRECTION, draft a message to the firefighter and suggest a reason rewrite

Rules:
- REJECT if there are any CRITICAL findings, or multiple HIGH findings
- NEEDS_CORRECTION if reason is vague, actions are ambiguous, or minor issues exist
- PASS only if reason is specific, actions are aligned, and no significant findings exist

The following transactions are neutral navigation/diagnostic tools that appear in almost
every session and should never be flagged as suspicious on their own:
SE80 (Object Navigator), SU53 (Authorization Check), SU3 (User Data),
SESSION_MANAGER, /NEX (Logoff), SM04 (User List).

The following rules are advisory signals only - they should inform your judgment
but never alone determine the verdict:
- R-011 (missing ticket reference) - may be absent in legacy sessions
- R-012 (reference-only reason) - check if actions are self-explanatory
- R-013 (fix claimed, no changes) - some fixes leave no change log entries
- R-016 (bank details modified) - legitimate if reason explicitly justifies it

For each semantic finding, evidence must quote the actual value from the session data.
Never write generic evidence like "reason is vague" - write the actual reason text.
Never write "transaction present" - write the actual tcode and timestamp.

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
      "evidence": "exact quoted value from session data"
    }
  ],
  "suggested_correction": {
    "message_to_firefighter": "...",
    "suggested_reason_rewrite": "..."
  } | null
}"""