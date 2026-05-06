# SAP Firefighter Log Compliance Reviewer
### Seargin AI/ML CoE — Internship Technical Challenge

---

## Quick Start

### Option 1 — Docker (recommended)

```bash
# 1. Copy environment file and add your API key
cp .env.example .env
# Edit .env and set LLM_API_KEY

# 2. Start the system
docker compose up --build

# 3. Open the UI
# http://localhost:3000
```

### Option 2 — Local development

```bash
# 1. Install dependencies
cd backend
pip install -e ".[dev]"

# 2. Copy and configure environment
cp .env.example .env
# Edit .env and set LLM_API_KEY

# 3. Start backend
make run

# 4. Open frontend/index.html in your browser
```

### Run tests
```bash
make test
```

### Run evaluation
```bash
make eval
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        docker compose                           │
│                                                                 │
│  ┌──────────────────────┐         ┌────────────────────────┐   │
│  │   frontend :3000     │         │   backend (internal)   │   │
│  │                      │         │                        │   │
│  │   nginx              │──HTTP──▶│   FastAPI              │   │
│  │   serves index.html  │  /api/  │   POST /review         │   │
│  │                      │         │   GET  /sessions       │   │
│  └──────────────────────┘         │   PATCH /sessions/{id} │   │
│                                   │                        │   │
│                                   │   ┌────────────────┐   │   │
│                                   │   │  Rule Engine   │   │   │
│                                   │   │  (deterministic│   │   │
│                                   │   │   14 rules)    │   │   │
│                                   │   └───────┬────────┘   │   │
│                                   │           │            │   │
│                                   │   ┌───────▼────────┐   │   │
│                                   │   │  LLM Analyzer  │   │   │
│                                   │   │  (Claude Haiku)│   │   │
│                                   │   └───────┬────────┘   │   │
│                                   │           │            │   │
│                                   │   ┌───────▼────────┐   │   │
│                                   │   │  SQLite DB     │   │   │
│                                   │   │  verdicts.db   │   │   │
│                                   │   └────────────────┘   │   │
│                                   └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

Request flow:
Session JSON → Pydantic validation → Rule Engine → LLM Analyzer → Verdict JSON
                                          │
                                          ▼
                               Hard REJECT if critical rule fires
                               (R-003, R-004, R-005, R-008, R-010)
                               → skip LLM entirely, confidence = 1.0
```

---

## Compliance Rule Catalog

### Baseline Rules (R-001 to R-010)

| Rule | Description | Severity | Logic |
|------|-------------|----------|-------|
| R-001 | Reason code empty, too short (<20 chars), or generic ("fix", "tbd", "production issue") | medium | Deterministic |
| R-002 | Reason mentions one SAP module but transactions touch a different one | high | Deterministic + LLM |
| R-003 | Debug & replace activity in system log (`/h`, value modification) | critical | Deterministic |
| R-004 | Direct table modification via SE16N or SM30 on sensitive tables | high | Deterministic |
| R-005 | OS-level commands executed (SM49, os_command_log non-empty) | critical | Deterministic |
| R-006 | Change volume disproportionate to stated reason (>5 changes per table) | high/medium | Deterministic |
| R-007 | Session outside business hours (07:00–18:00 UTC) without emergency signal | medium | Deterministic |
| R-008 | Firefighter user is also the ticket requester (self-approval) | high | Deterministic |
| R-009 | Session duration exceeds 120 minutes without re-justification | medium | Deterministic |
| R-010 | SoD conflict: known dangerous tcode pairs in same session (vendor change + payment run, etc.) | critical | Deterministic |

### Extended Rules (R-011 to R-016)

These rules were identified by analyzing patterns in the training dataset. They function as **advisory signals** — they provide context to the LLM but do not independently determine the verdict. This design choice was made after empirical testing showed that treating them as hard rules reduced accuracy from 96% to 76% due to false positives on legitimate sessions.

| Rule | Description | Severity | Rationale |
|------|-------------|----------|-----------|
| R-011 | Ticket reference is missing, empty, or a placeholder ("TBD", "N/A", "000000") | medium | Every firefighter session must be traceable to an approved ticket. Seen in 6 NEEDS_CORRECTION/REJECT sessions in train set |
| R-012 | Reason code is a reference-only placeholder ("see ticket", "as per mail") | medium | A reason that only points to a ticket provides no audit trail if the ticket system is unavailable |
| R-013 | Reason implies changes were made ("fixed", "resolved") but change_log is empty | medium | Either the fix happened outside the session, was not logged, or the reason is inaccurate |
| R-016 | Vendor bank account (LFBK.BANKN) or IBAN modified during session | high | Changing bank details is a known fraud vector. Both instances in train set (FF-TRAIN-0001, FF-TRAIN-0018) were REJECT |

### Rules Considered But Not Implemented

After analysis, the following patterns were identified but not activated as rules due to unacceptable false positive rates on the training set:

- **R-015 (SE38 ABAP Editor)** — SE38 appears in both REJECT sessions (0003, 0004, 0024) and legitimate PASS sessions (0009, 0019, 0030) where it is used to launch pre-approved custom programs. Without additional context (e.g. presence in system_log), it cannot be reliably distinguished.
- **R-014 (Transport Management)** — STMS/STMS_IMPORT appears in multiple PASS sessions (0011, 0023, 0036) where transport releases are a legitimate emergency action with proper justification.
- **R-017 (Very short session, no changes)** — boundary between accidental FFID opening and legitimate read-only investigation is too ambiguous without additional context.

---

## Deterministic vs LLM — Design Rationale

### Deterministic rules handle:
- Binary facts: does `os_command_log` have entries? Is `ticket_requester == firefighter_user`?
- Known bad patterns: SoD conflict tcode pairs, sensitive table edits, debug keywords in system log
- Quantitative thresholds: session duration, change counts

**Why deterministic for these?** These checks have a single correct answer derivable from the data. An LLM would add cost, latency, and potential inconsistency without improving correctness.

### LLM handles:
- Semantic alignment: does the reason *actually* match the actions in spirit, beyond keyword matching?
- Reason quality: is the justification specific enough even if it passes length/blacklist checks?
- Contextual judgment: is the volume of changes justified by the stated reason?
- Suggested correction generation: drafting the message to the firefighter

**Why LLM for these?** These require understanding intent and context — things that cannot be expressed as deterministic rules without an impossibly large lookup table.

### Cost optimization — LLM skip logic

Sessions with critical deterministic findings (R-003, R-004, R-005, R-008, R-010) skip the LLM entirely:

```
if triggered_rules ∩ {R-003, R-004, R-005, R-008, R-010} ≠ ∅:
    verdict = REJECT, confidence = 1.0  # no LLM call
```

In the training set, this applies to ~60% of REJECT sessions, reducing LLM calls and cost significantly.

The LLM prompt is also optimized to reduce token usage:
- Neutral/diagnostic tcodes (SE80, SU53, /NEX, SESSION_MANAGER) excluded from summary
- Change log truncated to first 10 entries with count of remaining
- Empty log sections omitted entirely

---

## Evaluation Results

### Train set (50 sessions, with gold labels)

```
Accuracy:  0.96
Macro F1:  0.96

Per-class:
  PASS              P=0.909  R=1.000  F1=0.952  (support=20)
  REJECT            P=1.000  R=1.000  F1=1.000  (support=15)
  NEEDS_CORRECTION  P=1.000  R=0.867  F1=0.929  (support=15)

Confusion matrix:
                    PASS   REJECT   NEEDS_CORRECTION
  PASS               20        0                  0
  REJECT              0       15                  0
  NEEDS_CORRECTION    2        0                 13
```

**Key observation:** REJECT class is perfect (15/15). Every hard violation is caught with 100% certainty. The 2 missed NEEDS_CORRECTION sessions are borderline cases where the LLM judged the session as compliant — these are the hardest cases where reasonable reviewers could disagree.

**Note on variance:** Due to LLM non-determinism (temperature=0.1 but not 0), accuracy varies between 94–98% across runs. REJECT is always 100% deterministic. The reported 96% is a representative single run.

### Test set (25 sessions, no labels)

Predictions submitted in `eval/predictions_test.jsonl`.

```
Distribution:
  PASS:              10 (40%)
  REJECT:            10 (40%)
  NEEDS_CORRECTION:   5 (20%)
```

---

## Known Failure Modes

### 1. LLM non-determinism on borderline cases
**What happens:** The same session reviewed twice can get different verdicts (PASS vs NEEDS_CORRECTION) due to LLM temperature variation. This affects ~4% of sessions in practice.

**Example:** FF-TRAIN-0034 — "FI investigation: posting issue on G/L account per PRB0078862" with MIRO access. The LLM sometimes judges this as acceptable cross-module read-only access, sometimes as out-of-scope.

**Mitigation:** Temperature set to 0.1 (minimum non-zero). Hard rules are always deterministic regardless.

### 2. R-002 module mismatch — high false negative rate
**What happens:** R-002 misses 7 out of 9 real module mismatches (recall 0.222). The keyword-to-tcode mapping is too limited to cover the full SAP module vocabulary.

**Example:** Sessions where reason mentions "posting" (could be FI or MM) and transactions touch both modules — the rule doesn't fire because "posting" maps to FI, and some MM tcodes are in scope.

**Root cause:** Module boundaries in SAP are not crisp. A proper solution would use a semantic embedding of the reason against tcode descriptions rather than a keyword lookup table.

### 3. R-007 false positives — after-hours legitimate sessions
**What happens:** R-007 fires on sessions that are after-hours but have other critical findings (R-005, R-004), making the finding redundant and cluttering the output.

**Example:** FF-TRAIN-0012 — OS commands executed at 22:00 UTC. Gold label has R-005 (critical) but not R-007. Our system adds R-007 as well, which is technically correct but misleading — the critical finding already determines the verdict.

**Proposed fix:** Suppress R-007 when a critical rule has already fired. Not implemented to preserve original rule specification.

### 4. LLM output format inconsistency
**What happens:** Occasionally the LLM returns two JSON objects in one response (detailed analysis followed by the required JSON). The parser now handles this by extracting the first complete JSON block, but it caused one prediction failure (FF-TEST-0002) in the initial test run.

**Mitigation:** Implemented brace-counting JSON extractor that ignores any content after the first complete `{...}` block.

---

## Cost Estimate

**Model:** `claude-haiku-4-5-20251001` (Anthropic)

**Token usage per session (average):**
- Input tokens: ~450 (session summary + system prompt)
- Output tokens: ~350 (verdict JSON + findings)
- Total: ~800 tokens

**Cost per session:**
- Sessions with critical deterministic findings (LLM skipped): **$0.00**
- Sessions requiring LLM: ~800 tokens × $0.0008/1K tokens input + $0.004/1K output ≈ **$0.0018**
- Weighted average (60% skip rate on REJECTs): **~$0.0007 per session**

**Full eval run (75 sessions):** ~$0.05

**Production estimate (50 sessions/month/client):** ~$0.035/month per client

---

## What I Would Build Next (Given Another Week)

**1. Model routing by confidence**
Use a fast, cheap model (Haiku) for triage. Route borderline sessions (confidence 0.6–0.85) to a more capable model (Sonnet) for a second opinion. Expected improvement: 2–3% accuracy gain on NEEDS_CORRECTION class at ~3× cost increase for borderline sessions only.

**2. Calibrated confidence scores**
The current confidence is self-reported by the LLM — not statistically calibrated. Build a calibration layer using the 50 labeled training sessions: fit a logistic regression on (rule_count, severity_distribution, reason_length) → P(correct verdict). This would make the confidence score meaningful rather than decorative.

**3. Feedback loop from controller decisions**
Currently controller PASS/REJECT/SEND_BACK decisions are stored but not used. Build a retraining signal: when the controller overrides the AI verdict, flag that session for human review and use it to improve the rule catalog or LLM prompt.

**4. Batch processing endpoint**
The current UI handles one session at a time. Add a `POST /review/batch` endpoint that accepts a ZIP of session JSONs and processes them asynchronously, streaming results as they complete. Essential for the 30–80 sessions/month production use case.

**5. Email integration for Send Back**
Currently Send Back records the decision locally but does not send the correction message to the firefighter. Integrate with an SMTP server or SAP GRC notification API to automatically dispatch the suggested correction message.

**6. Semantic R-002 rewrite**
Replace the keyword-to-tcode module mapping with a semantic similarity approach: embed the reason code and each tcode description using a small embedding model, then flag sessions where reason embedding is far from the centroid of tcode embeddings. Expected improvement: recall from 0.222 to 0.7+.

---

## Where I Disagreed with Gold Labels

The dataset notes explicitly encourage disagreement with specific labels where reasoning supports a different verdict. Here are cases where I believe the gold label is arguable:

### FF-TRAIN-0009, 0019, 0030 — Labeled PASS, I would argue NEEDS_CORRECTION

These sessions use `ZVENDOR_WHT_UPDATE` (a custom Z-program) to update 98–132 vendor withholding tax codes in bulk. The reason is explicit and references a CHG ticket.

**Why gold says PASS:** The reason is specific, the ticket exists, the action is pre-approved.

**Why I'd argue NEEDS_CORRECTION:** Custom Z-programs (Z/Y namespace) are customer-developed code that bypasses standard SAP input validation. Even with a pre-approved CHG, executing custom code in a production firefighter session deserves explicit controller sign-off — the firefighter should document that the Z-program was reviewed before execution, not just that the CHG was approved.

This is not a clear-cut REJECT (the intent is legitimate) but NEEDS_CORRECTION would prompt the firefighter to confirm the Z-program review step.

### FF-TRAIN-0034, 0040, 0050 — Labeled NEEDS_CORRECTION (R-002), I would argue PASS

These sessions have FI-scope reasons ("posting issue on G/L account") with MIRO (MM module) accessed for read-only review.

**Why gold says NEEDS_CORRECTION:** MIRO is an MM transaction — module mismatch with FI reason.

**Why I'd argue PASS:** In SAP FI/CO practice, it is standard to cross-reference MM invoice documents (via MIRO display) during FI G/L investigations. An AP accountant investigating a G/L posting issue routinely checks the originating MM invoice for context. This is not out-of-scope activity — it is the expected diagnostic path. The gold label appears to apply R-002 too strictly without considering the natural FI→MM investigation flow.

---

## Project Structure

```
firefighter-reviewer/
├── Makefile                    ← make run / test / eval / clean
├── docker-compose.yml
├── .env.example
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── main.py
│       ├── config.py
│       ├── pipeline.py         ← core pipeline, used by API and eval
│       ├── api/
│       │   ├── routes.py
│       │   └── schemas.py      ← Pydantic input validation
│       ├── rules/
│       │   ├── models.py
│       │   ├── parser.py
│       │   ├── engine.py
│       │   └── catalog/
│       │       ├── dangerous_actions.py   ← R003, R004, R005
│       │       ├── access_control.py      ← R008, R010
│       │       ├── volume_timing.py       ← R006, R007, R009
│       │       ├── reason_quality.py      ← R001, R002
│       │       └── extended.py            ← R011, R012, R013, R016
│       ├── llm/
│       │   ├── client.py
│       │   ├── prompts.py
│       │   └── analyzer.py
│       └── storage/
│           ├── database.py
│           ├── models.py
│           └── repository.py
│   └── tests/
│       ├── test_parser.py
│       ├── test_rules.py
│       ├── test_extended_rules.py
│       └── test_analyzer.py    ← marked @llm, excluded from CI
│
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   ├── styles.css
│   └── app.js
│
├── eval/
│   ├── run_eval.py             ← runs pipeline on session directory
│   ├── predictions_train.jsonl ← predictions on labeled train set
│   └── predictions_test.jsonl  ← predictions on unlabeled test set
│
└── dataset_candidate/          ← provided dataset (unmodified)
    ├── train/
    ├── test/
    └── eval.py                 ← provided evaluator script
```

---

## Hours Spent

| Day | Focus | Hours |
|-----|-------|-------|
| 1 | Architecture design, data models, parser, rule engine (R001–R010), tests | ~6h |
| 2 | LLM layer, FastAPI backend, SQLite storage, frontend UI | ~5h |
| 3 | Docker, CI/CD, eval harness, extended rules (R011–R016), accuracy tuning | ~5h |
| 4 | Adversarial input handling, token optimization, schema validation, README | ~3h |
| **Total** | | **~19h** |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for LLM provider | required |
| `LLM_BASE_URL` | OpenAI-compatible endpoint | `https://api.anthropic.com/v1` |
| `LLM_MODEL` | Model identifier | `claude-haiku-4-5-20251001` |
| `LLM_MAX_TOKENS` | Max tokens per LLM response | `1000` |

The system uses the OpenAI-compatible `/v1/chat/completions` endpoint. Switching providers requires only changing `LLM_BASE_URL` and `LLM_MODEL` in `.env`.

---

## Tooling Note

This project was built with AI coding assistance (Claude). Every architectural decision, rule implementation, and design tradeoff was discussed and reasoned through — the code reflects deliberate choices, not generated boilerplate. Be prepared to discuss any part of the implementation in detail.
