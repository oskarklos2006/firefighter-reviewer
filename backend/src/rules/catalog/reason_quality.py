from __future__ import annotations
from rules.models import Finding, Severity, SessionData

_MIN_REASON_LENGTH = 20
_GENERIC_REASONS = {
    "test", "fix", "asap", "urgent", "tbd", "n/a", "na",
    "production issue", "issue", "issue resolution",
    "system error fix", "investigating", "temp", "temporary"
}

# Module keyword mapping: if reason mentions these → expected tcode families
_MODULE_TCODE_MAP: dict[str, set[str]] = {
    "payment":      {"F110", "F-53", "F-58", "FBL1N", "FB02"},
    "vendor":       {"XK02", "FK02", "XK01", "FK01", "FBL1N"},
    "user":         {"SU01", "SU10", "SU53", "SU3"},
    "hr":           {"PA30", "PA20", "PA40", "PT60"},
    "inventory":    {"MIGO", "MB51", "MM60"},
    "invoice":      {"MIRO", "MIR4", "FB60"},
    "gl":           {"FBL3N", "FB03", "F.01", "OB52"},
    "period":       {"OB52", "MMPV"},
}

# Tcodes that are diagnostic/navigational and appear in any session
# regardless of module — never flag these as out-of-scope
_NEUTRAL_TCODES = {
    "SU53",           # Display Authorization Check
    "SU3",            # Maintain Own User Data
    "SE80",           # Object Navigator
    "SESSION_MANAGER", # Session Manager
    "/NEX",           # Logoff
    "SM04",           # User List
}

def check_r001(session: SessionData) -> list[Finding]:
    """Reason code is empty, too short, or generically useless."""
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
    """Reason mentions one module but transactions touch a different one."""
    reason_lower = session.reason_code.lower()
    tcodes_used = {e.tcode for e in session.transaction_log}

    # Collect ALL modules mentioned in the reason
    matched_modules = {
        keyword for keyword in _MODULE_TCODE_MAP
        if keyword in reason_lower
    }

    if not matched_modules:
        return []

    # All tcodes that are expected given the stated reason
    all_expected_tcodes: set[str] = set()
    for keyword in matched_modules:
        all_expected_tcodes.update(_MODULE_TCODE_MAP[keyword])

    # Tcodes used that belong to a known module but not any expected one
    all_known_tcodes: set[str] = set()
    for tcodes in _MODULE_TCODE_MAP.values():
        all_known_tcodes.update(tcodes)

    out_of_scope = (
        tcodes_used
        & all_known_tcodes          # only flag tcodes we know about
        - all_expected_tcodes       # that aren't expected
        - _NEUTRAL_TCODES           # that aren't neutral/diagnostic
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
    return findings