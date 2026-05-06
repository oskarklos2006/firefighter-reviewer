from __future__ import annotations
from rules.models import Finding, SessionData


def build_session_summary(session: SessionData, findings: list[Finding]) -> str:
    """
    Flatten session into a token-efficient string for the LLM.
    No nested JSON — just the facts the LLM needs.
    """
    tcodes = ", ".join(e.tcode for e in session.transaction_log) or "none"
    changes = "; ".join(
        f"{e.table}.{e.field} {e.old_value}→{e.new_value}"
        for e in session.change_log
    ) or "none"
    os_cmds = "; ".join(
        e.command for e in session.os_command_log
    ) or "none"
    system_events = "; ".join(
        e.message for e in session.system_log
    ) or "none"

    duration = (session.end_time - session.start_time).total_seconds() / 60

    findings_text = "\n".join(
        f"  - {f.rule_id} {f.severity.value.upper()}: {f.description}"
        for f in findings
    ) or "  none"

    return f"""SESSION: {session.session_id}
USER: {session.firefighter_user} | CONTROLLER: {session.controller}
SYSTEM: {session.system} | CLIENT: {session.client}
START: {session.start_time.isoformat()} | DURATION: {duration:.0f} min
REASON: {session.reason_code}
TICKET: {session.ticket_reference}
TRANSACTIONS: {tcodes}
CHANGES: {changes}
OS COMMANDS: {os_cmds}
SYSTEM LOG: {system_events}
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