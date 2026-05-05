from __future__ import annotations
from rules.models import Finding, Severity, SessionData

# R-010: Known SoD conflict pairs
# Each tuple: (set of tcodes that modify, set of tcodes that execute/approve)
# If both sides appear in the same session - critical violation
_SOD_CONFLICT_PAIRS: list[tuple[set[str], set[str]]] = [
    # Vendor master change + payment execution
    ({"XK02", "FK02", "XK01", "FK01"}, {"F110", "F-53", "F-58"}),
    # User creation/modification + role assignment
    ({"SU01"}, {"SU10", "PFCG"}),
    # Goods receipt + invoice verification
    ({"MIGO"}, {"MIRO"}),
    # Customer master change + billing
    ({"XD02", "FD02"}, {"VF01", "VF02"}),
]


def check_r008(session: SessionData) -> list[Finding]:
    """Firefighter user is also the ticket requester — self-approval pattern."""
    if not session.ticket_requester:
        return []

    if session.firefighter_user.upper() == session.ticket_requester.upper():
        return [Finding(
            rule_id="R-008",
            severity=Severity.HIGH,
            location="ticket_requester",
            description=(
                "Firefighter user is also the ticket requester. "
                "This self-approval pattern violates segregation of duties — "
                "the person requesting emergency access should not be the same "
                "person who raised the ticket justifying it."
            ),
            evidence=(
                f"firefighter_user: {session.firefighter_user}, "
                f"ticket_requester: {session.ticket_requester}"
            ),
        )]

    return []


def check_r010(session: SessionData) -> list[Finding]:
    """SoD conflict: both sides of a known conflict pair used in same session."""
    findings = []
    tcodes_used = {e.tcode for e in session.transaction_log}

    for modify_set, execute_set in _SOD_CONFLICT_PAIRS:
        modify_hits = tcodes_used & modify_set
        execute_hits = tcodes_used & execute_set

        if modify_hits and execute_hits:
            findings.append(Finding(
                rule_id="R-010",
                severity=Severity.CRITICAL,
                location="transaction_log",
                description=(
                    "Segregation of duties violation: a transaction that modifies "
                    "master data and a transaction that executes a financial process "
                    "were both run in the same session by the same user."
                ),
                evidence=(
                    f"Modify side: {', '.join(sorted(modify_hits))} - "
                    f"Execute side: {', '.join(sorted(execute_hits))}"
                ),
            ))

    return findings