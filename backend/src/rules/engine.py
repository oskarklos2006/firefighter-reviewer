# ─────────────────────────────────────────────────────────────
# engine.py
# Runs all deterministic rules against a session and returns
# a sorted list of findings. This is the only file that imports
# from all catalog modules - add new rules here to register them.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from rules.models import Finding, SessionData
from rules.catalog.dangerous_actions import check_r003, check_r004, check_r005
from rules.catalog.access_control import check_r008, check_r010
from rules.catalog.volume_timing import check_r006, check_r007, check_r009
from rules.catalog.reason_quality import check_r001, check_r002
from rules.catalog.extended import check_r011, check_r012, check_r013, check_r016

# All active rules in evaluation order.
# To add a new rule: implement it in the appropriate catalog file,
# import it here, and append it to this list.
_RULES = [
    check_r001,
    check_r002,
    check_r003,
    check_r004,
    check_r005,
    check_r006,
    check_r007,
    check_r008,
    check_r009,
    check_r010,
    check_r011,
    check_r012,
    check_r013,
    check_r016,
]


def run_rules(session: SessionData) -> list[Finding]:
    findings: list[Finding] = []

    for rule_fn in _RULES:
        try:
            results = rule_fn(session)
            findings.extend(results)
        except Exception as e:
            # A broken rule must never stop the pipeline - log R-ERR and continue
            findings.append(Finding(
                rule_id="R-ERR",
                severity="low",
                location="engine",
                description=f"Rule {rule_fn.__name__} failed during execution.",
                evidence=str(e),
            ))

    _SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.severity.value, 99))

    return findings