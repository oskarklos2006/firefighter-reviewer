from __future__ import annotations
from collections import Counter
from rules.models import Finding, Severity, SessionData

# Thresholds — all in config ideally but defined here for clarity
_MAX_CHANGES_SINGLE_TABLE = 5
_BUSINESS_HOURS_START = 7   # 07:00 UTC
_BUSINESS_HOURS_END = 18    # 18:00 UTC
_MAX_SESSION_MINUTES = 120

# Generic reason keywords that suggest the reason won't justify high volume
_SINGLE_ITEM_KEYWORDS = [
    "one vendor", "one user", "single vendor", "single user",
    "one record", "fix one", "one entry"
]


def check_r006(session: SessionData) -> list[Finding]:
    """Change volume disproportionate to stated reason."""
    findings = []

    changes_by_table = Counter(e.table for e in session.change_log)

    for table, count in changes_by_table.items():
        if count <= _MAX_CHANGES_SINGLE_TABLE:
            continue

        reason_lower = session.reason_code.lower()
        single_item_claimed = any(
            keyword in reason_lower for keyword in _SINGLE_ITEM_KEYWORDS
        )

        if single_item_claimed:
            severity = Severity.HIGH
            description = (
                f"{count} changes to table {table} in a single session, "
                f"but reason claims a single-item fix. "
                f"This volume requires change management approval, not a firefighter session."
            )
        else:
            severity = Severity.MEDIUM
            description = (
                f"{count} changes to table {table} in a single session. "
                f"Verify this volume is consistent with the stated reason."
            )

        findings.append(Finding(
            rule_id="R-006",
            severity=severity,
            location="change_log",
            description=description,
            evidence=(
                f"{count} entries in {table} vs. reason: '{session.reason_code}'"
            ),
        ))

    return findings


def check_r007(session: SessionData) -> list[Finding]:
    """Session outside business hours without clear emergency justification."""
    hour = session.start_time.hour
    is_outside_hours = hour < _BUSINESS_HOURS_START or hour >= _BUSINESS_HOURS_END

    if not is_outside_hours:
        return []

    reason_lower = session.reason_code.lower()
    emergency_keywords = [
        "emergency", "critical", "urgent", "outage", "down", "failed",
        "failure", "blocked", "incident", "inc", "production issue"
    ]
    has_emergency_signal = any(kw in reason_lower for kw in emergency_keywords)

    if has_emergency_signal:
        return []

    return [Finding(
        rule_id="R-007",
        severity=Severity.MEDIUM,
        location="start_time",
        description=(
            "Session started outside business hours (07:00–18:00 UTC) "
            "without a clear emergency indicator in the reason code."
        ),
        evidence=session.start_time.isoformat(),
    )]


def check_r009(session: SessionData) -> list[Finding]:
    """Session duration exceeds maximum allowed without re-justification."""
    duration_minutes = (
        session.end_time - session.start_time
    ).total_seconds() / 60

    if duration_minutes <= _MAX_SESSION_MINUTES:
        return []

    return [Finding(
        rule_id="R-009",
        severity=Severity.MEDIUM,
        location="end_time",
        description=(
            f"Session ran for {duration_minutes:.0f} minutes, "
            f"exceeding the {_MAX_SESSION_MINUTES}-minute limit. "
            f"No re-justification documented."
        ),
        evidence=(
            f"start: {session.start_time.isoformat()}, "
            f"end: {session.end_time.isoformat()}"
        ),
    )]