# ─────────────────────────────────────────────────────────────
# dangerous_actions.py
# Rules that detect technically dangerous activity in a session.
# All three rules are fully deterministic - no LLM needed.
#   R-003: debug mode activity in system log
#   R-004: direct table edit via SE16N or SM30
#   R-005: OS-level commands executed from SAP
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from rules.models import Finding, Severity, SessionData

# Keywords that indicate debug mode was active in the system log
_DEBUG_KEYWORDS = ["/h", "debug", "replace", "value modified", "variable value changed"]

# SE16N and SM30 allow direct database writes, bypassing SAP input validation
_DANGEROUS_TCODES = {"SE16N", "SM30"}

# Tables containing financial config, vendor data, user credentials, or payroll
_SENSITIVE_TABLES = {"T001", "T001W", "LFBK", "LFA1", "KNA1", "USR02", "PA0008", "BSEG"}

# Commands that are destructive or could exfiltrate data
_DANGEROUS_OS_COMMANDS = {"rm", "chmod", "chown", "kill", "wget", "curl", "bash", "sh", "zsh"}


def check_r003(session: SessionData) -> list[Finding]:
    findings = []
    for i, entry in enumerate(session.system_log):
        message_lower = entry.message.lower()
        if any(keyword in message_lower for keyword in _DEBUG_KEYWORDS):
            findings.append(Finding(
                rule_id="R-003",
                severity=Severity.CRITICAL,
                location=f"system_log[{i}]",
                description=(
                    "Debug session detected during firefighter window. "
                    "Debug & replace cannot be ruled out without further inspection."
                ),
                evidence=f"{entry.timestamp.isoformat()} - {entry.message}",
            ))
    return findings


def check_r004(session: SessionData) -> list[Finding]:
    findings = []

    dangerous_tcodes_used = {
        e.tcode for e in session.transaction_log
        if e.tcode in _DANGEROUS_TCODES
    }

    sensitive_tables_modified = {
        e.table for e in session.change_log
        if e.table in _SENSITIVE_TABLES
    }

    for tcode in dangerous_tcodes_used:
        # Include which sensitive tables were touched if any - stronger evidence
        if sensitive_tables_modified:
            evidence = (
                f"{tcode} executed; sensitive tables modified: "
                f"{', '.join(sorted(sensitive_tables_modified))}"
            )
        else:
            evidence = f"{tcode} executed in firefighter session"

        findings.append(Finding(
            rule_id="R-004",
            severity=Severity.HIGH,
            location="transaction_log",
            description=(
                f"Direct table edit via {tcode} without documented data-fix approval. "
                f"This bypasses normal change management."
            ),
            evidence=evidence,
        ))

    return findings


def check_r005(session: SessionData) -> list[Finding]:
    # Any OS command from SAP is a violation regardless of what it does.
    # The destructive flag is added for commands that could cause immediate damage.
    findings = []
    for i, entry in enumerate(session.os_command_log):
        command_lower = entry.command.lower()
        is_destructive = any(cmd in command_lower for cmd in _DANGEROUS_OS_COMMANDS)

        findings.append(Finding(
            rule_id="R-005",
            severity=Severity.CRITICAL,
            location=f"os_command_log[{i}]",
            description=(
                "OS-level command executed during firefighter session. "
                "Any OS access from SAP requires separate authorization and justification."
                + (" Command appears destructive." if is_destructive else "")
            ),
            evidence=(
                f"{entry.timestamp.isoformat()} - "
                f"{entry.command} {entry.parameters} (executed by {entry.executed_by})"
            ),
        ))

    return findings