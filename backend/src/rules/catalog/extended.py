# ─────────────────────────────────────────────────────────────
# extended.py
# Additional rules beyond the baseline R-001 to R-010.
# All four were identified by analyzing patterns in the 50 labeled
# training sessions - each has specific session IDs as evidence.
# These rules act as advisory signals - they inform the LLM but
# do not independently force a verdict. See analyzer.py for details.
#   R-011: missing or invalid ticket reference
#   R-012: reason is a reference-only placeholder
#   R-013: reason claims a fix but change log is empty
#   R-016: vendor bank account or IBAN modified
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from rules.models import Finding, Severity, SessionData

# Common placeholder values that provide no audit trail
_INVALID_TICKETS = {
    "", "n/a", "na", "tbd", "000000", "none", "null", "test", "unknown"
}


def check_r011(session: SessionData) -> list[Finding]:
    ticket = session.ticket_reference.strip().lower()

    if ticket in _INVALID_TICKETS:
        return [Finding(
            rule_id="R-011",
            severity=Severity.MEDIUM,
            location="ticket_reference",
            description=(
                "Ticket reference is missing or contains a placeholder value. "
                "Every firefighter session must be traceable to an approved ticket. "
                "Without a valid reference, the controller has no audit trail."
            ),
            evidence=f"ticket_reference: '{session.ticket_reference}'",
        )]
    return []


# Reasons that only point elsewhere instead of explaining the actual activity
_REFERENCE_ONLY_REASONS = {
    "see ticket", "see inc", "see incident", "refer to ticket",
    "check ticket", "as per ticket", "per ticket", "ticket",
    "see change", "as discussed", "as per mail", "see email",
}


def check_r012(session: SessionData) -> list[Finding]:
    reason = session.reason_code.strip().lower()

    if reason in _REFERENCE_ONLY_REASONS:
        return [Finding(
            rule_id="R-012",
            severity=Severity.MEDIUM,
            location="reason_code",
            description=(
                "Reason code is a reference placeholder with no actual justification. "
                "The reason must describe what broke, what was done, and why - "
                "not just point to a ticket."
            ),
            evidence=session.reason_code,
        )]
    return []


# Words that imply a change was made
_FIX_KEYWORDS = [
    "fixed", "resolved", "corrected", "updated", "changed",
    "modified", "adjusted", "repaired", "patched"
]

# Words that indicate read-only intent - suppress R-013 if present
# e.g. "investigated and resolved" would fire without this guard
_READONLY_KEYWORDS = [
    "investigating", "investigation", "checking",
    "monitoring", "display", "reviewed"
]


def check_r013(session: SessionData) -> list[Finding]:
    reason_lower = session.reason_code.lower()

    reason_implies_fix = any(kw in reason_lower for kw in _FIX_KEYWORDS)
    no_changes = len(session.change_log) == 0

    if not reason_implies_fix or not no_changes:
        return []

    # Skip if reason also contains investigation keywords - mixed intent is common
    if any(kw in reason_lower for kw in _READONLY_KEYWORDS):
        return []

    return [Finding(
        rule_id="R-013",
        severity=Severity.MEDIUM,
        location="change_log",
        description=(
            "Reason code implies changes were made but the change log is empty. "
            "Either the fix happened outside this session, was not logged, "
            "or the reason code is inaccurate."
        ),
        evidence=(
            f"Reason implies fix: '{session.reason_code}' "
            f"but change_log has 0 entries."
        ),
    )]


# LFBK stores vendor bank account data - changing it redirects payments
_BANK_TABLES = {"LFBK"}
_BANK_FIELDS = {"BANKN", "IBAN", "BKONT", "SWIFT"}


def check_r016(session: SessionData) -> list[Finding]:
    bank_changes = [
        e for e in session.change_log
        if e.table in _BANK_TABLES and e.field in _BANK_FIELDS
    ]

    if not bank_changes:
        return []

    evidence = "; ".join(
        f"{e.table}.{e.field} {e.old_value}→{e.new_value}"
        for e in bank_changes
    )

    return [Finding(
        rule_id="R-016",
        severity=Severity.HIGH,
        location="change_log",
        description=(
            "Vendor bank account details modified during firefighter session. "
            "Changing bank account numbers or IBANs is a known fraud vector - "
            "it enables redirecting payments to unauthorized accounts. "
            "This type of change requires dual approval outside of emergency access."
        ),
        evidence=evidence,
    )]