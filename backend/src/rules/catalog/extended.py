from __future__ import annotations
import re
from rules.models import Finding, Severity, SessionData

# ── R-011: Missing or invalid ticket reference ─────────────────────────────
_INVALID_TICKETS = {
    "", "n/a", "na", "tbd", "000000", "none", "null", "test", "unknown"
}


def check_r011(session: SessionData) -> list[Finding]:
    """Ticket reference is missing, empty, or a placeholder value."""
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


# ── R-012: Reason is reference-only placeholder ────────────────────────────
_REFERENCE_ONLY_REASONS = {
    "see ticket", "see inc", "see incident", "refer to ticket",
    "check ticket", "as per ticket", "per ticket", "ticket",
    "see change", "as discussed", "as per mail", "see email",
}


def check_r012(session: SessionData) -> list[Finding]:
    """Reason code is a reference placeholder with no actual justification."""
    reason = session.reason_code.strip().lower()

    if reason in _REFERENCE_ONLY_REASONS:
        return [Finding(
            rule_id="R-012",
            severity=Severity.MEDIUM,
            location="reason_code",
            description=(
                "Reason code is a reference placeholder with no actual justification. "
                "The reason must describe what broke, what was done, and why — "
                "not just point to a ticket."
            ),
            evidence=session.reason_code,
        )]
    return []


# ── R-013: Fix claimed but no changes recorded ─────────────────────────────
_FIX_KEYWORDS = [
    "fixed", "resolved", "corrected", "updated", "changed",
    "modified", "adjusted", "repaired", "patched"
]

_READONLY_KEYWORDS = [
    "investigating", "investigation", "checking",
    "monitoring", "display", "reviewed"
]


def check_r013(session: SessionData) -> list[Finding]:
    """Reason implies changes were made but change_log is empty."""
    reason_lower = session.reason_code.lower()

    reason_implies_fix = any(kw in reason_lower for kw in _FIX_KEYWORDS)
    no_changes = len(session.change_log) == 0

    if not reason_implies_fix or not no_changes:
        return []

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


# ── R-016: Vendor bank account or IBAN modified ────────────────────────────
_BANK_TABLES = {"LFBK"}
_BANK_FIELDS = {"BANKN", "IBAN", "BKONT", "SWIFT"}


def check_r016(session: SessionData) -> list[Finding]:
    """Vendor bank account or IBAN modified during firefighter session."""
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
            "Changing bank account numbers or IBANs is a known fraud vector "
            "and requires dual approval outside of emergency access. "
            "Seen in FF-TRAIN-0001 and FF-TRAIN-0018 — both labeled REJECT."
        ),
        evidence=evidence,
    )]