# Firefighter Log Reviewer — Personal Development Notes
> Written at end of Day 1. This is NOT the submission README. This is your cold-head analysis document.

---

## How to Run Right Now

```bash
# 1. Start the backend (from backend/ folder)
cd backend
uvicorn src.main:app --reload

# 2. Open the frontend
# Just double-click frontend/index.html in your file explorer

# 3. Run fast tests (no LLM, instant)
cd backend
pytest tests/ -m "not llm" -v

# 4. Run LLM tests (slow, rate-limited, use sparingly)
pytest tests/ -m "llm" -v
```

**Prerequisites:**
- Python 3.12 venv activated (`.venv` in project root)
- `.env` file in project root with your OpenRouter API key
- Dependencies installed: `pip install -e ".[dev]"` from `backend/`

---

## What This System Does (Plain English)

SAP production systems have emergency access accounts called "Firefighter IDs". When something breaks at 3am, a consultant uses one of these to fix it. Every action they take is logged. A compliance officer (called a "Controller") must review each session and decide: was this legitimate?

Today there are 30-80 sessions per month per client. Controllers read them manually — 20-40 minutes each. They make mistakes. They rubber-stamp logs they didn't fully read.

This tool pre-screens each session automatically and gives the controller a structured verdict with specific findings and a draft message to send back if something is wrong.

**Three possible verdicts:**
- `PASS` — everything looks fine, approve it
- `REJECT` — clear violation, escalate it
- `NEEDS_CORRECTION` — something's off but not certain, ask the firefighter to explain

---

## Project Structure

```
firefighter-reviewer/
├── .env                        ← YOUR API KEY (never commit this)
├── .env.example                ← template showing what variables are needed
├── .gitignore
│
├── backend/
│   ├── pyproject.toml          ← dependencies and project config
│   ├── data/
│   │   └── verdicts.db         ← SQLite database (auto-created on first run)
│   ├── src/
│   │   ├── main.py             ← entry point, just imports the FastAPI app
│   │   ├── config.py           ← reads .env into typed settings object
│   │   ├── api/
│   │   │   └── routes.py       ← HTTP endpoints
│   │   ├── rules/
│   │   │   ├── models.py       ← data structures
│   │   │   ├── parser.py       ← converts raw JSON to typed objects
│   │   │   ├── engine.py       ← runs all rules, returns findings
│   │   │   └── catalog/
│   │   │       ├── dangerous_actions.py   ← R003, R004, R005
│   │   │       ├── access_control.py      ← R008, R010
│   │   │       ├── volume_timing.py       ← R006, R007, R009
│   │   │       └── reason_quality.py      ← R001, R002
│   │   ├── llm/
│   │   │   ├── client.py       ← HTTP calls to OpenRouter API
│   │   │   ├── prompts.py      ← session summary builder + system prompt
│   │   │   └── analyzer.py     ← orchestrates LLM call + fallback logic
│   │   └── storage/
│   │       ├── database.py     ← SQLAlchemy engine setup
│   │       ├── models.py       ← ORM table definition
│   │       └── repository.py   ← save/load/update functions
│   └── tests/
│       ├── test_parser.py      ← 5 tests for JSON parsing
│       ├── test_rules.py       ← 26 tests for all 10 rules + engine
│       └── test_analyzer.py    ← 3 LLM integration tests (marked @llm)
│
├── frontend/
│   └── index.html              ← entire UI in one file, no build step
│
├── dataset_candidate/          ← provided dataset (DO NOT MODIFY)
│   ├── train/
│   │   ├── sessions/           ← 50 labeled session JSONs
│   │   └── labels.jsonl        ← gold labels for training set
│   └── test/
│       └── sessions/           ← 25 unlabeled session JSONs
│
└── eval/                       ← TODO: build eval harness tomorrow
    └── test_set/
```

---

## File-by-File Explanation

---

### `main.py`
**One line. Just starts the app.**

```python
from api.routes import app
```

Uvicorn runs this file. It finds `app` and starts the HTTP server. All actual logic lives elsewhere. Think of it as the front door — it just points you inside.

---

### `config.py`
**Reads your `.env` file and makes settings available everywhere — typed and validated.**

Without it you'd scatter this across every file:
```python
import os
key = os.getenv("LLM_API_KEY")  # could be None, no warning
```

With it, you import `settings` once and it's always correct:
```python
from config import settings
settings.llm_api_key            # always a string
settings.llm_model              # "google/gemma-4-31b-it:free"
settings.max_session_minutes    # 120
```

If you forget to add `LLM_API_KEY` to `.env`, the app refuses to start with a clear error. No silent failures at 3am.

---

### `rules/models.py`
**Defines the shape of every object the system passes around internally.**

Without it, rules would work with raw dicts:
```python
session["transaction_log"][0]["tcode"]  # crashes if key missing
```

With it, every rule gets clean typed objects:
```python
session.transaction_log[0].tcode        # always a string
session.start_time                       # always UTC-aware datetime
session.change_log[0].old_value         # always a string
```

Key types:
- `SessionData` — the whole session (logs, timestamps, reason code, etc.)
- `Finding` — one compliance issue detected
- `Severity` — low / medium / high / critical
- `Verdict` — PASS / REJECT / NEEDS_CORRECTION

---

### `rules/parser.py`
**Takes raw uploaded JSON and converts it into a clean `SessionData` object.**

Raw input:
```json
{
  "start_time": "2026-05-12T12:35:53Z",
  "reason_code": "fix",
  "change_log": [{"table": "LFA1", "key": 100234}]
}
```

What you get back:
```python
session.start_time              # datetime(2026, 5, 12, 12, 35, 53, tzinfo=UTC)
session.reason_code             # "fix"
session.change_log[0].key       # "100234"  ← integer cast to string
session.ticket_requester        # None  ← missing field, defaulted safely
```

It silently fixes: missing timezone on timestamps, integers where strings expected, absent optional fields.
It loudly raises `ValueError` for missing required fields like `session_id` — the API catches this and returns 422 instead of 500.

---

### `rules/catalog/dangerous_actions.py`
**R003, R004, R005 — technically dangerous activity. Pure yes/no checks.**

**R003 — Debug & Replace**
Did someone use SAP's debugger to change values directly, bypassing all validation?
```
system_log: "Variable value changed in debug mode (/h replace): WRBTR 50000.00 → 5000.00"
→ CRITICAL finding
```
Classic fraud technique. Changes a posting amount from 50,000 to 5,000 with no audit trail.

**R004 — Direct Table Edit**
Did someone use SE16N or SM30 to write directly to a database table?
```
transaction_log: SE16N at 22:07
change_log: table T001, WAERS field, EUR → USD
→ HIGH finding: direct edit of company code currency table
```
Normal SAP transactions validate input. SE16N does not. You can corrupt anything.

**R005 — OS Commands**
Did someone run shell commands from SAP?
```
os_command_log: "rm -rf /tmp/sapdumps/" by KZIELINSKA
→ CRITICAL finding, flagged as destructive
```
Any OS access from SAP is already a violation. The "destructive" flag is added for `rm`, `chmod`, `kill` etc.

---

### `rules/catalog/access_control.py`
**R008, R010 — who did what, and whether the combination is allowed.**

**R008 — Self Approval**
Did the firefighter request their own emergency access?
```
firefighter_user: MNOWAK
ticket_requester: MNOWAK
→ HIGH finding: self-approval pattern
```
Like a bank employee approving their own loan. The person requesting access must be different from the person who justified it.

**R010 — SoD Conflict**
Did they perform two actions that should never happen together?
```
XK02 (changed vendor bank account number)
F110 (ran automatic payment to that vendor)
→ CRITICAL finding: SoD violation
```
This is textbook fraud — change where money goes, then send the money. We check 4 known conflict pairs:
- Vendor change (XK02/FK02) + payment run (F110/F-53)
- User creation (SU01) + role assignment (PFCG)
- Goods receipt (MIGO) + invoice verification (MIRO)
- Customer change (XD02) + billing (VF01)

---

### `rules/catalog/volume_timing.py`
**R006, R007, R009 — suspicious numbers and timing.**

**R006 — Too Many Changes**
Did they change far more records than the reason justifies?
```
reason: "Fix one vendor blocked status"
change_log: 265 rows in LFA1, same field, all in 4 minutes
→ HIGH finding: 265 changes vs claimed single-vendor fix
```
Threshold: more than 5 changes to a single table triggers the rule. If reason claims "one vendor" → HIGH. If no such claim → MEDIUM (still flag but less certain).

**R007 — After Hours Without Emergency**
Did they work at 3am without a documented emergency?
```
start_time: 22:06 UTC
reason: "Fix one vendor blocked status"  ← no emergency keywords
→ MEDIUM finding: after-hours session without emergency justification
```
We look for: "emergency", "critical", "urgent", "outage", "incident", "system down" etc.

**Bug fixed today:** "blocked" was in the keyword list. "Fix one vendor **blocked** status" matched as emergency, rule didn't fire. Removed it — business vocabulary ("blocked vendor") overlaps with emergency vocabulary.

**R009 — Session Too Long**
Did the session run over 2 hours?
```
start: 07:12   end: 12:29   → 317 minutes (limit: 120)
→ MEDIUM finding: session ran 317 minutes
```

---

### `rules/catalog/reason_quality.py`
**R001, R002 — is the written justification actually useful?**

**R001 — Reason Too Vague**
```
""                   → empty → fire
"fix"                → 3 chars, minimum 20 → fire
"production issue"   → exact match on blacklist → fire
"Resolved failed payment run F110 per INC0045231"  → passes
```
Blacklist: "fix", "tbd", "n/a", "production issue", "issue", "issue resolution", "system error fix", "temp".

**R002 — Module Mismatch**
Does the reason claim one module but the actions touch another?
```
reason: "Reset user lock for HR consultant"
transactions: FB02 (accounting), XK02 (vendor), F-53 (payment)
→ HIGH finding: reason references user activity but FI/vendor tcodes used
```

How it works:
1. Find all modules mentioned in the reason ("user", "payment", "vendor"...)
2. Build the full set of expected tcodes for ALL matched modules
3. Find tcodes used that belong to a KNOWN module but NOT the expected set
4. Ignore neutral tcodes: SE80, SU53, SU3, SESSION_MANAGER, /NEX

**Bug fixed today:** original code picked one module keyword and flagged the other's tcodes as out-of-scope. FF-TRAIN-0001 reason says "vendor...and...payment" — XK02 (vendor) and F110 (payment) are both legitimate. Fix: collect ALL matched modules first, then check.

---

### `rules/engine.py`
**Runs all 10 rules and returns all findings sorted by severity.**

```python
findings = run_rules(session)
# → [CRITICAL: R-010 SoD violation, HIGH: R-002 module mismatch, ...]
```

Two important decisions:
- Each rule returns `list[Finding]` — one session can trigger R-004 on multiple dangerous tcodes
- `try/except` around every rule — a broken rule logs `R-ERR` and the pipeline continues. One broken rule never kills the whole review

---

### `llm/client.py`
**Makes the actual HTTP call to the LLM API.**

```python
text = await call_llm(
    prompt="SESSION: FF-TRAIN-0001\nREASON: ...\nFINDINGS: R-010 CRITICAL...",
    system="You are a SAP GRC compliance reviewer..."
)
# → '{"verdict": "REJECT", "confidence": 0.95, "semantic_findings": [...]}'
```

Key settings:
- `temperature: 0.1` — low randomness. Compliance verdicts should not vary between runs
- Retries 3 times on 429 (rate limit): waits 10s, 20s, 30s
- 60 second timeout — free tier LLMs can be slow

---

### `llm/prompts.py`
**Flattens session data for the LLM, and defines the system prompt.**

Why flatten? Nested JSON wastes tokens and confuses models. Instead of sending the raw JSON:
```
# Raw (expensive, confusing):
{"transaction_log": [{"timestamp": "2026-05-12T12:45:52Z", "tcode": "XK02"...}]}

# Flattened (cheap, clear):
TRANSACTIONS: XK02, FK02, SU53, F110, FBL1N
CHANGES: LFBK.BANKN 1234567890→5434337882; LFBK.IBAN DE89...→DE97...
DETERMINISTIC FINDINGS:
  - R-010 CRITICAL: SoD violation — XK02/FK02 + F110 in same session
```

The system prompt tells the LLM its role, the verdict rules, which tcodes are neutral (never flag SE80, SU53 etc.), and the exact JSON format to return.

---

### `llm/analyzer.py`
**Orchestrates the full LLM interaction — call, parse, merge, override, fallback.**

Full flow:
```
1. Flatten session + deterministic findings into text
2. Call LLM
3. Parse JSON response (strips markdown fences if LLM adds them)
4. Convert LLM findings → Finding objects
5. Merge: deterministic + LLM findings
6. Hard override: any CRITICAL deterministic finding → verdict = REJECT always
7. Return combined result
```

**Hard override:** If R-010 fired, we are 100% certain. The LLM cannot override a confirmed SoD violation to PASS.

**Fallback:** LLM fails → return deterministic verdict with `confidence: 0.5`. Never crashes.

**Confidence 50%** = LLM didn't respond (rate limit). In production (one session at a time) this never happens.

---

### `api/routes.py`
**Three HTTP endpoints. The only place the outside world talks to the system.**

**`POST /review`** — main endpoint
```
Upload FF-TRAIN-0001.json
→ parse → rules → LLM → save to DB → return JSON verdict
```
Returns 400 for invalid JSON, 422 for missing required fields.

**`PATCH /sessions/{session_id}/decision`** — controller clicks a button
```
PATCH /sessions/FF-TRAIN-0001/decision
Body: {"decision": "REJECT"}
→ saves to database, returns 404 if session not found
```

**`GET /sessions`** — history table
```
GET /sessions
→ all reviewed sessions, newest first
```

---

### `storage/database.py`
**Sets up SQLite. Creates the database file and folder on first run.**

```python
DB_PATH = backend/data/verdicts.db   # auto-created if missing
```

`init_db()` runs at FastAPI startup and creates the `verdicts` table if it doesn't exist. You never run migrations manually.

---

### `storage/models.py`
**Defines what the database table looks like.**

One table: `verdicts`. Columns:
```
session_id              (primary key)
verdict                 ("PASS" / "REJECT" / "NEEDS_CORRECTION")
confidence              (0.0 - 1.0 float)
findings_json           (all findings as JSON string)
suggested_correction_json  (JSON string or null)
controller_decision     ("PASS" / "REJECT" / "SEND_BACK" or null)
controller_note         (optional text)
created_at / updated_at (auto timestamps)
```

Findings stored as a JSON string because SQLite has no native array type and we never query by individual finding fields.

---

### `storage/repository.py`
**The only file that touches the database. Everyone else calls these three functions.**

```python
save_verdict(result)               # after every review
get_all_sessions()                 # GET /sessions endpoint
update_decision(id, decision)      # controller clicks button
```

If you switch from SQLite to Postgres tomorrow, you change `database.py` and this file. Nothing else.

---

### `frontend/index.html`
**Entire UI in one HTML file. Open directly in browser. No Node, no build step.**

Three sections:
1. **Upload zone** — click or drag a session JSON. Shows filename after selection
2. **Result panel** — appears after review:
   - Verdict banner (green=PASS, red=REJECT, yellow=NEEDS_CORRECTION)
   - PASS / REJECT / SEND BACK buttons for controller
   - Findings list (color-coded by severity, with rule ID badge, description, raw evidence)
   - Correction message card (only shown for NEEDS_CORRECTION)
3. **History table** — all previously reviewed sessions with controller decisions

Design: dark navy + blue (Seargin branding), Sora font, JetBrains Mono for all code/log data, subtle grid background, glassmorphism cards, animated hover effects.

JavaScript: vanilla, no framework. Three async functions that call the backend on `localhost:8000`.

---

## Key Design Decisions (For Interview)

**Why deterministic rules before LLM?**
The LLM receives rule findings as context. It focuses only on what deterministic logic can't judge — semantic meaning. Running them in parallel wastes tokens re-discovering known facts.

**Why not use the OpenAI SDK?**
Direct HTTP via `httpx`. Provider-agnostic — switch from OpenRouter to Anthropic to Ollama by changing one env variable.

**Why SQLite not Postgres?**
Zero infrastructure. Creates itself on first run. Perfectly sufficient here. Postgres would add complexity with zero benefit.

**Why dataclasses internally, Pydantic at the API boundary?**
Dataclasses are pure Python — fast, no overhead, no coupling to HTTP. Pydantic handles JSON validation and serialization at the boundary where it's actually needed.

**Why does R-010 always override the LLM?**
SoD violations are binary facts. XK02 + F110 in same session IS a violation. No LLM interpretation can change that. Deterministic certainty beats LLM judgment for clear-cut cases.

---

## Known Issues Found Today

**Bug 1 — R-007 false negative**
"blocked" was in emergency keywords. "Fix one vendor **blocked** status" matched. Rule didn't fire.
Fixed: removed "blocked". Lesson: business terminology overlaps with emergency vocabulary.

**Bug 2 — R-002 false positive**
Original code picked one module keyword and flagged the other's tcodes as out-of-scope.
Fixed: collect all matched modules first, combine all expected tcodes, then check.

**Bug 3 — LLM false positive on SE80**
LLM flagged SE80 (Object Navigator) as suspicious on a clean session.
Fixed: added neutral tcode list to system prompt.

**Bug 4 — Confidence always 50% during development**
Not a real bug. Means LLM rate-limited and fell back. In production (one session at a time) never happens.

---

## What's Left Tomorrow

- [ ] `eval/run_eval.py` — run all 75 sessions, confusion matrix + per-rule precision/recall
- [ ] `Makefile` — `make run`, `make test`, `make eval`, `make clean`
- [ ] `Dockerfile` for backend and frontend
- [ ] `docker-compose.yml`
- [ ] Additional rules beyond R001-R010 (worth 15% of grade)
- [ ] Submission README with architecture diagram, rule rationale, failure modes, cost estimate
- [ ] `.github/workflows/ci.yml` for CI/CD bonus

## Additional Rules to Think About Tonight

- **Sensitive financial field changed** — IBAN or bank account modified (LFBK table) without a payment running. Currently only caught if R-010 fires too.
- **Zero changes but reason implies fix** — reason says "fixed the issue" but change_log is empty.
- **Firefighter ID module mismatch** — FF_FI_01 (Finance) doing BASIS work (SU01, SM21).
- **Multiple logoffs mid-session** — /NEX appearing more than once suggests session handed off.
- **Change timestamp outside session window** — change_log entry before start_time or after end_time.
- **Same key modified multiple times** — same vendor number changed 3 times suggests testing not fixing.

---

## Cost Estimate

Using `google/gemma-4-31b-it:free` on OpenRouter: **$0.00**

If switching to paid models:
- Claude Haiku: ~$0.001/session × 75 = ~$0.075 total
- Claude Sonnet: ~$0.01/session × 75 = ~$0.75 total

Model routing strategy (cheap model for clear-cut cases, expensive for borderline) would keep production cost under $0.005 per session.
