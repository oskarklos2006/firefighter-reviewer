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
    findings = []
    reason_lower = session.reason_code.lower()
    tcodes_used = {e.tcode for e in session.transaction_log}

    for module_keyword, expected_tcodes in _MODULE_TCODE_MAP.items():
        if module_keyword not in reason_lower:
            continue

        # Reason mentions this module — check for tcodes from OTHER modules
        other_module_tcodes: set[str] = set()
        for other_keyword, other_tcodes in _MODULE_TCODE_MAP.items():
            if other_keyword == module_keyword:
                continue
            # Only flag tcodes that are clearly from a different domain
            out_of_scope = (tcodes_used & other_tcodes) - expected_tcodes
            other_module_tcodes.update(out_of_scope)

        if other_module_tcodes:
            findings.append(Finding(
                rule_id="R-002",
                severity=Severity.HIGH,
                location="transaction_log",
                description=(
                    f"Reason references '{module_keyword}' activity but session "
                    f"also contains transactions outside that scope."
                ),
                evidence=(
                    f"Reason: '{session.reason_code}'; "
                    f"Out-of-scope tcodes: {', '.join(sorted(other_module_tcodes))}"
                ),
            ))
            break  # one finding per session for R-002 is enough

    return findings