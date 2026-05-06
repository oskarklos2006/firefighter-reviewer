# ─────────────────────────────────────────────────────────────
# access_control.py
# Rules about who did what and whether the combination is allowed.
#   R-008: self-approval - firefighter raised their own ticket
#   R-010: SoD conflict - dangerous tcode pairs in same session
# Both rules are fully deterministic - no LLM needed.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from rules.models import Finding, Severity, SessionData

# Each pair represents two sides of a known segregation of duties conflict.
# If tcodes from both sides appear in the same session, it is a critical violation.
# Left side: transactions that modify master data or configuration
# Right side: transactions that execute financial processes using that data
_SOD_CONFLICT_PAIRS: list[tuple[set[str], set[str]]] = [
    ({"XK02", "FK02", "XK01", "FK01"}, {"F110", "F-53", "F-58"}),  # vendor change + payment
    ({"SU01"}, {"SU10", "PFCG"}),                                    # user create + role assign
    ({"MIGO"}, {"MIRO"}),                                            # goods receipt + invoice
    ({"XD02", "FD02"}, {"VF01", "VF02"}),                           # customer change + billing
]


def check_r008(session: SessionData) -> list[Finding]:
    # ticket_requester is optional - skip if not present in the session
    if not session.ticket_requester:
        return []

    if session.firefighter_user.upper() == session.ticket_requester.upper():
        return [Finding(
            rule_id="R-008",
            severity=Severity.HIGH,
            location="ticket_requester",
            description=(
                "Firefighter user is also the ticket requester. "
                "This self-approval pattern violates segregation of duties - "
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
    findings = []
    tcodes_used = {e.tcode for e in session.transaction_log}

    for modify_set, execute_set in _SOD_CONFLICT_PAIRS:
        modify_hits = tcodes_used & modify_set
        execute_hits = tcodes_used & execute_set

        # Both sides must be present - one side alone is not a violation
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