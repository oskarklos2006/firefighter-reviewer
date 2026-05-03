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
# OR open http://127.0.0.1:5500 if using VSCode Live Server

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

### `backend/src/config.py`
Reads the `.env` file and exposes everything as a typed Python object called `settings`. Every other file imports `settings` instead of calling `os.getenv()` directly. This means:
- Type errors caught at startup, not at runtime
- One place to change any configuration
- Easy to see all config options at a glance

**Key settings:** `llm_api_key`, `llm_model`, `llm_base_url`, plus rule thresholds like `max_session_minutes` (120) and `max_changes_single_table` (5).

---

### `rules/models.py`
Defines all internal data structures as Python dataclasses. The important ones:

- `SessionData` — the full parsed session (all logs, metadata, timestamps)
- `Finding` — one compliance issue detected (rule_id, severity, location, description, evidence)
- `Severity` — enum: low / medium / high / critical
- `Verdict` — enum: PASS / REJECT / NEEDS_CORRECTION

**Why dataclasses not Pydantic?** These are internal objects — rule functions pass them around. Pydantic is only used at the HTTP boundary (API input/output). Mixing the two would couple rule logic to API concerns.

---

### `rules/parser.py`
Takes a raw Python dict (from `json.load()`) and returns a clean `SessionData` object.

**Key decisions made here:**
- Uses `dateutil` not `datetime.fromisoformat` — handles timezone quirks in real SAP logs
- Always attaches UTC timezone to timestamps — prevents comparison crashes
- Casts all values to `str` — SAP sometimes logs numbers as integers in JSON
- Optional fields default to `None` — `ticket_requester` isn't always present
- Raises `ValueError` with clear messages on malformed input — API returns 422 instead of 500

---

### `rules/catalog/dangerous_actions.py` — R003, R004, R005

**R003 — Debug & Replace**
Scans `system_log` for messages containing `/h`, "debug", "value modified", etc.
Why deterministic: either the word appears in the log or it doesn't. No judgment needed.
Severity: CRITICAL — modifying values via debugger bypasses all change management.

**R004 — Direct Table Modification**
Checks if `SE16N` or `SM30` appear in `transaction_log`.
Additionally checks if any `change_log` entries touched known sensitive tables (T001, LFBK, USR02, etc.).
Why deterministic: presence of these tcodes is a binary fact.
Severity: HIGH — direct table edits bypass the normal SAP validation layer.

**R005 — OS Commands**
Checks if `os_command_log` is non-empty. Flags every entry.
Adds "appears destructive" to description for commands like `rm`, `chmod`, `kill`.
Why deterministic: any OS command from SAP is already a violation regardless of what it does.
Severity: CRITICAL.

---

### `rules/catalog/access_control.py` — R008, R010

**R008 — Self Approval**
Compares `firefighter_user` to `ticket_requester` (case-insensitive).
Only fires if `ticket_requester` field exists — it's optional in the dataset.
Why deterministic: it's a string comparison.
Severity: HIGH — segregation of duties requires the person requesting access to be different from the person who justified it.

**R010 — SoD Conflict**
Maintains a list of conflict pairs — sets of tcodes that should never appear together:
- Vendor master change (XK02/FK02) + payment run (F110/F-53) → classic fraud enabler
- User creation (SU01) + role assignment (PFCG) → privilege escalation
- Goods receipt (MIGO) + invoice verification (MIRO) → procurement fraud
Checks if BOTH sides of any pair appear in the same session's `transaction_log`.
Why deterministic: tcode presence is a fact. No interpretation needed.
Severity: CRITICAL.

---

### `rules/catalog/volume_timing.py` — R006, R007, R009

**R006 — Excessive Changes**
Counts changes per table using `collections.Counter`.
Threshold: 5 changes to a single table.
If the reason claims "one vendor" / "single record" etc. → severity HIGH.
Otherwise → severity MEDIUM (still flag but less certain it's wrong).
**Important insight from FF-TRAIN-0004:** 265 changes happened in 4 minutes, all same field. Reason said "fix one vendor". The mismatch between claim and reality is the signal, not the count alone. LLM is asked to judge this context.

**R007 — After Hours**
Checks if `start_time.hour` is outside 07:00–18:00 UTC.
If outside hours → checks reason for emergency keywords (emergency, critical, urgent, outage, incident, etc.).
If no emergency signal found → fires.
**Bug we fixed:** "blocked" was originally in emergency keywords. FF-TRAIN-0004 reason said "Fix one vendor blocked status" — "blocked" matched as emergency keyword, rule didn't fire. Lesson: business vocabulary overlaps with emergency vocabulary. Document this as a known failure mode.

**R009 — Session Too Long**
Calculates `(end_time - start_time).total_seconds() / 60`.
Fires if over 120 minutes with no re-justification documented.
FF-TRAIN-0016 ran 5h17m — only doing read-only FB03 display transactions. Verdict: NEEDS_CORRECTION.

---

### `rules/catalog/reason_quality.py` — R001, R002

**R001 — Reason Quality**
Three checks in order:
1. Empty → fire
2. Under 20 characters → fire
3. Exact match against blacklist ("fix", "tbd", "production issue", "issue resolution", etc.) → fire

**R002 — Module Mismatch**
Maps reason keywords to expected tcode families:
- "payment" → {F110, F-53, FBL1N, ...}
- "vendor" → {XK02, FK02, ...}
- "user" → {SU01, SU10, ...}
etc.

**Algorithm:**
1. Find ALL modules mentioned in the reason
2. Combine ALL their expected tcodes into one allowed set
3. Find tcodes used that are in a known module but NOT in the allowed set
4. Exclude neutral/diagnostic tcodes (SE80, SU53, SU3, SESSION_MANAGER, /NEX)

**Bug we fixed:** original code picked one module keyword and flagged others as out-of-scope. FF-TRAIN-0001 reason mentions both "vendor" and "payment" — both XK02 and F110 are legitimate. Fix: collect all matched modules first, then check for violations.

---

### `rules/engine.py`
Imports all rule functions into a list `_RULES` and runs them all against a session.

**Key design decisions:**
- Each rule returns `list[Finding]` not `Finding | None` — a single session can trigger R-004 multiple times (multiple dangerous tcodes)
- `try/except` around each rule — a broken rule must never crash the pipeline. Creates an `R-ERR` finding instead
- Sorts findings by severity (critical first) — controller sees the worst thing first

---

### `llm/client.py`
Simple async HTTP client using `httpx`. Calls the OpenAI-compatible `/v1/chat/completions` endpoint.

**Key decisions:**
- `temperature: 0.1` — we want consistent, deterministic output. Compliance decisions shouldn't vary between runs
- Retry logic with exponential backoff — free tier rate limits hit at 429. Waits 10s, 20s, 30s before giving up
- 60 second timeout — LLM calls can be slow

---

### `llm/prompts.py`
Two things:

**`build_session_summary()`** — flattens the `SessionData` object into a compact text string for the LLM. No nested JSON. Changes become `TABLE.FIELD old→new`. Deterministic findings are included so the LLM doesn't re-discover them.

**Why flatten?** Deeply nested JSON wastes tokens and can confuse models. A flat text representation is cheaper and clearer.

**`SYSTEM_PROMPT`** — tells the LLM its role, the rules for each verdict, which tcodes are neutral (never flag SE80, SU53 etc.), and the exact JSON output format required.

---

### `llm/analyzer.py`
Orchestrates the full LLM interaction.

**Flow:**
1. Build session summary with deterministic findings already included
2. Call LLM
3. Parse JSON response (strips markdown fences if present)
4. Convert LLM findings to `Finding` objects
5. Merge with deterministic findings
6. Apply hard override: if any deterministic CRITICAL finding exists → verdict is always REJECT, LLM cannot override

**Hard override rationale:** If R-010 (SoD violation) fires deterministically, we are 100% certain there's a violation. Letting the LLM potentially return PASS on a confirmed SoD violation would be dangerous. Deterministic certainty beats LLM judgment.

**Fallback:** If LLM fails for any reason (timeout, rate limit, bad JSON), returns a verdict based purely on deterministic findings with `confidence: 0.5`. System never crashes.

---

### `api/routes.py`
Three endpoints:

**`POST /review`**
- Accepts a JSON file upload
- Parses it → runs rule engine → calls LLM analyzer → saves to DB → returns verdict
- Returns 400 for invalid JSON, 422 for missing required fields

**`PATCH /sessions/{session_id}/decision`**
- Controller clicks PASS/REJECT/SEND_BACK
- Saves their decision to the database
- Returns 404 if session not found

**`GET /sessions`**
- Returns all reviewed sessions ordered by date
- Used by the frontend to populate the history table

**CORS is open (`allow_origins=["*"]`)** — fine for local development. In production you'd restrict this to your frontend domain.

---

### `storage/`

**`database.py`** — SQLAlchemy engine pointing at `backend/data/verdicts.db`. Creates the file and directory automatically. `init_db()` called at FastAPI startup.

**`models.py`** — one table: `verdicts`. Stores session_id (primary key), verdict, confidence, findings as JSON string, suggested_correction as JSON string, controller_decision, controller_note, timestamps.

**Why store findings as JSON string?** SQLite doesn't have a native JSON array type. Serializing to text is simpler than creating a separate findings table, and we never need to query by individual finding fields.

**`repository.py`** — three functions: `save_verdict()`, `get_all_sessions()`, `update_decision()`. Nothing outside this file touches the database directly. This is the repository pattern — if you ever switch to Postgres, you change this file and nothing else.

---

### `frontend/index.html`
Single HTML file, no build step, no Node, no npm. Opens directly in browser.

**Design:** Dark navy (#0a1628) + blue (#1e6fff) matching Seargin branding. Sora font for UI, JetBrains Mono for all code/IDs/evidence. Grid background pattern, glow orbs, glassmorphism cards.

**Three sections:**
1. Upload zone — click or drag JSON file
2. Result panel — verdict banner, decision buttons, findings list, correction card, session info
3. History table — all previously reviewed sessions with their controller decisions

**JavaScript:** Vanilla JS, no framework. Three async functions: `handleFile()`, `recordDecision()`, `loadSessions()`. Calls the FastAPI backend on `localhost:8000`.

---

## Key Design Decisions (For Interview)

### Why deterministic rules run before LLM?
The LLM receives the rule findings as context in its prompt. This way the LLM focuses only on what deterministic logic can't answer — semantic judgment. Running in parallel would waste tokens re-discovering things we already know for certain.

### Why not use the OpenAI SDK?
We call the OpenAI-compatible HTTP endpoint directly via `httpx`. Provider-agnostic — same code works with Anthropic, OpenRouter, Gemini, or local Ollama by changing one environment variable.

### Why SQLite not Postgres?
Zero infrastructure. SQLite ships with Python, creates itself on first run, needs no server. Perfectly sufficient for this use case. Postgres would add complexity with zero benefit.

### Why dataclasses for models, Pydantic for API?
Dataclasses = internal data, no serialization overhead, pure Python.
Pydantic = API boundary, handles validation and JSON serialization automatically.
Mixing them would couple rule logic to HTTP concerns.

### Why does R-010 always override the LLM verdict?
SoD violations are binary facts. XK02 + F110 in the same session IS a violation, period. No semantic interpretation can change that. Allowing the LLM to return PASS on a confirmed SoD violation would defeat the purpose of having deterministic checks.

---

## Known Issues / Bugs Found Today

1. **R-007 false negative** — "blocked" was in emergency keywords. Business vocabulary ("vendor blocked status") overlapped with emergency vocabulary. Fixed by removing it.

2. **R-002 false positive** — original logic picked one module keyword and flagged others as out-of-scope. Sessions with multi-module reasons (vendor + payment) triggered false findings. Fixed by collecting ALL matched modules first.

3. **LLM false positive on SE80** — LLM flagged SE80 (Object Navigator) as suspicious on a clean session. Fixed by adding neutral tcode list to system prompt.

4. **Confidence 50%** — not a real confidence score. Means LLM rate-limited and fell back to deterministic verdict. Real confidence comes from LLM (typically 0.85-0.95).

---

## What's Left (Tomorrow)

- [ ] `eval/run_eval.py` — run all 75 sessions, produce confusion matrix
- [ ] `Makefile` — `make run`, `make test`, `make eval`, `make clean`
- [ ] `Dockerfile` for backend
- [ ] `Dockerfile` for frontend (nginx)
- [ ] `docker-compose.yml`
- [ ] Additional rules beyond baseline R001-R010 (worth 15% of grade)
- [ ] Submission README (architecture diagram, rule rationale, failure modes, cost estimate)
- [ ] `.github/workflows/ci.yml` for CI/CD bonus

## Additional Rules to Think About Tonight

The baseline gives us R001-R010. We need to propose more. Think about:
- Sensitive financial fields changed (IBAN, bank account number) — we saw this in FF-TRAIN-0001
- Session with zero changes but reason implies changes were needed
- Firefighter ID module mismatch (FF_FI_01 doing BASIS work)
- Multiple logoffs mid-session (/NEX appearing multiple times) — suggests session hand-off
- Change timestamps outside session window
- Same vendor modified multiple times suggesting iterative testing not a fix

---

## Cost Estimate (For README)

Using `google/gemma-4-31b-it:free` on OpenRouter:
- **Current cost: $0.00** — free tier model
- If switching to Claude Haiku: ~$0.001 per session × 75 sessions = **~$0.075 total**
- If switching to Claude Sonnet: ~$0.01 per session × 75 sessions = **~$0.75 total**

The system is designed to use the cheapest model for triage. A model routing strategy (Haiku for clear-cut cases, Sonnet for borderline) would keep costs under $0.005 per session in production.
