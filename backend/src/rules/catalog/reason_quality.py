# ─────────────────────────────────────────────────────────────
# reason_quality.py
# Rules that assess the quality and accuracy of the reason code.
#   R-001: reason is empty, too short, or a known generic phrase
#   R-002: reason mentions one SAP module but actions touch another
# R-002 is the weakest baseline rule - module boundaries in SAP are
# fuzzy and keyword matching misses many real mismatches. See README
# for proposed semantic embedding improvement.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from rules.models import Finding, Severity, SessionData

_MIN_REASON_LENGTH = 20

# Exact matches that pass the length check but provide no real justification
_GENERIC_REASONS = {
    "test", "fix", "asap", "urgent", "tbd", "n/a", "na",
    "production issue", "issue", "issue resolution",
    "system error fix", "investigating", "temp", "temporary"
}

# Maps reason keywords to the tcodes expected for that module.
# If reason mentions "payment" we expect F110, F-53 etc. - not HR tcodes.
_MODULE_TCODE_MAP: dict[str, set[str]] = {
    "payment":   {"F110", "F-53", "F-58", "FBL1N", "FB02"},
    "vendor":    {"XK02", "FK02", "XK01", "FK01", "FBL1N"},
    "user":      {"SU01", "SU10", "SU53", "SU3"},
    "hr":        {"PA30", "PA20", "PA40", "PT60"},
    "inventory": {"MIGO", "MB51", "MM60"},
    "invoice":   {"MIRO", "MIR4", "FB60"},
    "gl":        {"FBL3N", "FB03", "F.01", "OB52"},
    "period":    {"OB52", "MMPV"},
}

# Tcodes that appear in virtually every session regardless of module.
# Flagging these as out-of-scope would generate constant false positives.
_NEUTRAL_TCODES = {
    "SU53",            # Display Authorization Check
    "SU3",             # Maintain Own User Data
    "SE80",            # Object Navigator
    "SESSION_MANAGER",
    "/NEX",            # Logoff
    "SM04",            # User List
}


def check_r001(session: SessionData) -> list[Finding]:
    reason = session.reason_code.strip()

    if not reason:
        return [Finding(
            rule_id="R-001",
            severity=Severity.MEDIUM,
            location="reason_code",
            description="Reason code is empty. A justification is mandatory for every firefighter session.",
            evidence="(empty)",
        )]

    if len(reason) < _MIN_REASON_LENGTH:
        return [Finding(
            rule_id="R-001",
            severity=Severity.MEDIUM,
            location="reason_code",
            description=(
                f"Reason code is too short ({len(reason)} characters). "
                f"Minimum is {_MIN_REASON_LENGTH} characters."
            ),
            evidence=reason,
        )]

    if reason.lower() in _GENERIC_REASONS:
        return [Finding(
            rule_id="R-001",
            severity=Severity.MEDIUM,
            location="reason_code",
            description=(
                "Reason code is generic and provides no business justification. "
                "It must describe what broke, what was done, and reference a ticket."
            ),
            evidence=reason,
        )]

    return []


def check_r002(session: SessionData) -> list[Finding]:
    reason_lower = session.reason_code.lower()
    tcodes_used = {e.tcode for e in session.transaction_log}

    # Collect all modules mentioned - reason may reference multiple legitimately
    # e.g. "updated vendor bank details and triggered payment" mentions both
    matched_modules = {
        keyword for keyword in _MODULE_TCODE_MAP
        if keyword in reason_lower
    }

    if not matched_modules:
        return []

    # Build the full set of expected tcodes across all matched modules
    all_expected_tcodes: set[str] = set()
    for keyword in matched_modules:
        all_expected_tcodes.update(_MODULE_TCODE_MAP[keyword])

    all_known_tcodes: set[str] = set()
    for tcodes in _MODULE_TCODE_MAP.values():
        all_known_tcodes.update(tcodes)

    # Flag only tcodes that belong to a known module outside the expected set
    out_of_scope = (
        tcodes_used
        & all_known_tcodes
        - all_expected_tcodes
        - _NEUTRAL_TCODES
    )

    if not out_of_scope:
        return []

    return [Finding(
        rule_id="R-002",
        severity=Severity.HIGH,
        location="transaction_log",
        description=(
            f"Reason references {', '.join(sorted(matched_modules))} activity "
            f"but session contains transactions outside that scope."
        ),
        evidence=(
            f"Reason: '{session.reason_code}'; "
            f"Out-of-scope tcodes: {', '.join(sorted(out_of_scope))}"
        ),
    )]