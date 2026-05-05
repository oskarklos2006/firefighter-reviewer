from __future__ import annotations
from rules.models import Finding, Severity, SessionData

# R-011: Custom ABAP programs (Z* or Y* namespace)
_CUSTOM_PROGRAM_PREFIXES = ("Z", "Y")

# R-012: Reason is reference-only with no actual justification
_REFERENCE_ONLY_REASONS = {
    "see ticket", "see inc", "see incident", "refer to ticket",
    "check ticket", "as per ticket", "per ticket", "ticket",
    "see change", "as discussed", "as per mail", "see email",
}

# R-013: Reason implies a fix was made but no changes recorded
_FIX_KEYWORDS = [
    "fixed", "resolved", "corrected", "updated", "changed",
    "modified", "adjusted", "repaired", "patched"
]

# R-014: Transport management tcodes
_TRANSPORT_TCODES = {"STMS", "STMS_IMPORT", "SE09", "SE10", "CG3Y", "CG3Z"}


def check_r011(session: SessionData) -> list[Finding]:
    """Custom ABAP program (Z*/Y* namespace) executed in firefighter session."""
    findings = []
    custom_tcodes = [
        e.tcode for e in session.transaction_log
        if e.tcode.startswith(_CUSTOM_PROGRAM_PREFIXES)
        and len(e.tcode) > 1  # exclude /NEX etc
    ]

    if not custom_tcodes:
        return []

    findings.append(Finding(
        rule_id="R-011",
        severity=Severity.HIGH,
        location="transaction_log",
        description=(
            "Custom ABAP program(s) executed during firefighter session. "
            "Programs in the Z/Y namespace are customer-developed and not "
            "subject to standard SAP audit controls. Execution must be "
            "explicitly justified in the reason code."
        ),
        evidence=f"Custom tcodes used: {', '.join(sorted(set(custom_tcodes)))}",
    ))
    return findings


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


def check_r013(session: SessionData) -> list[Finding]:
    """Reason implies a fix was made but change_log is empty."""
    reason_lower = session.reason_code.lower()

    reason_implies_fix = any(kw in reason_lower for kw in _FIX_KEYWORDS)
    no_changes = len(session.change_log) == 0

    if not reason_implies_fix or not no_changes:
        return []

    # Exclude read-only investigation reasons
    readonly_keywords = ["investigating", "investigation", "checking", "monitoring", "display"]
    if any(kw in reason_lower for kw in readonly_keywords):
        return []

    return [Finding(
        rule_id="R-013",
        severity=Severity.MEDIUM,
        location="change_log",
        description=(
            "Reason code implies changes were made but the change log is empty. "
            "Either the fix was not logged, happened outside this session, "
            "or the reason code is inaccurate."
        ),
        evidence=(
            f"Reason implies fix: '{session.reason_code}' "
            f"but change_log has 0 entries."
        ),
    )]


def check_r014(session: SessionData) -> list[Finding]:
    """Transport management executed in firefighter session."""
    transport_tcodes_used = {
        e.tcode for e in session.transaction_log
        if e.tcode in _TRANSPORT_TCODES
    }

    if not transport_tcodes_used:
        return []

    return [Finding(
        rule_id="R-014",
        severity=Severity.HIGH,
        location="transaction_log",
        description=(
            "Transport management transactions executed during firefighter session. "
            "Releasing or importing transports in production bypasses the normal "
            "transport approval and quality gate process."
        ),
        evidence=f"Transport tcodes: {', '.join(sorted(transport_tcodes_used))}",
    )]