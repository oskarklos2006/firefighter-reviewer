from __future__ import annotations
from rules.models import Finding, Severity, SessionData

# R-003: Debug & replace activity
_DEBUG_KEYWORDS = ["/h", "debug", "replace", "value modified", "variable value changed"]

# R-004: Direct table modification via dangerous transactions
_DANGEROUS_TCODES = {"SE16N", "SM30"}
_SENSITIVE_TABLES = {"T001", "T001W", "LFBK", "LFA1", "KNA1", "USR02", "PA0008", "BSEG"}

# R-005: OS-level commands
_DANGEROUS_OS_COMMANDS = {"rm", "chmod", "chown", "kill", "wget", "curl", "bash", "sh", "zsh"}


def check_r003(session: SessionData) -> list[Finding]:
    """Debug & replace activity detected in system log."""
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
                evidence=f"{entry.timestamp.isoformat()} — {entry.message}",
            ))
    return findings


def check_r004(session: SessionData) -> list[Finding]:
    """Direct table modification via SE16N or SM30 on sensitive tables."""
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
    """OS-level commands executed during firefighter session."""
    findings = []
    for i, entry in enumerate(session.os_command_log):
        command_lower = entry.command.lower()
        is_dangerous = any(cmd in command_lower for cmd in _DANGEROUS_OS_COMMANDS)

        findings.append(Finding(
            rule_id="R-005",
            severity=Severity.CRITICAL,
            location=f"os_command_log[{i}]",
            description=(
                "OS-level command executed during firefighter session. "
                "Any OS access from SAP requires separate authorization and justification."
                + (" Command appears destructive." if is_dangerous else "")
            ),
            evidence=(
                f"{entry.timestamp.isoformat()} — "
                f"{entry.command} {entry.parameters} (executed by {entry.executed_by})"
            ),
        ))

    return findings