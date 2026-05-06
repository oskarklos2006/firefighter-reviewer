# ─────────────────────────────────────────────────────────────
# routes.py
# FastAPI application and HTTP endpoints. This is the only place
# the outside world communicates with the system. Three endpoints:
#   POST /review        - accepts a session JSON, runs the pipeline
#   PATCH /sessions/:id - records the controller final decision
#   GET  /sessions      - returns all reviewed sessions for the UI
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from typing import Optional
from storage.repository import save_verdict, get_all_sessions, update_decision
from storage.database import init_db
from pipeline import review_session_data
from api.schemas import SessionSchema


app = FastAPI(title="Firefighter Log Reviewer", version="0.1.0")

# Allow all origins - this is a local tool, no auth required
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Create SQLite tables on startup if they don't exist yet
@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


# Main review endpoint
# Accepts a session JSON file, validates structure, runs the full pipeline,
# saves the result to the database, and returns the verdict.
# force_llm=true bypasses the LLM skip logic for hard REJECT sessions,
# used by the "Re-analyze with LLM" button in the UI.
@app.post("/review")
async def review_session(
    file: UploadFile = File(...),
    force_llm: bool = Query(default=False)
):
    # Parse JSON - return 400 for malformed files
    try:
        content = await file.read()
        raw = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    # Validate session structure against Pydantic schema
    # Returns 422 with a clear message if required fields are missing
    try:
        SessionSchema(**raw)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid session structure: {e.errors()[0]['msg']}"
        )

    try:
        response = await review_session_data(raw, force_llm=force_llm)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    save_verdict(response)
    return response


# Controller decision model
# decision must be one of: PASS, REJECT, SEND_BACK
class DecisionUpdate(BaseModel):
    decision: str
    controller_note: Optional[str] = None


# Records the controller final decision on a reviewed session.
# In a production system this would also trigger an email to the firefighter.
@app.patch("/sessions/{session_id}/decision")
async def record_decision(session_id: str, body: DecisionUpdate):
    allowed = {"PASS", "REJECT", "SEND_BACK"}
    if body.decision not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Decision must be one of {allowed}"
        )
    updated = update_decision(session_id, body.decision, body.controller_note)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "updated", "session_id": session_id}


# Returns all reviewed sessions ordered by date, newest first.
# Used by the UI to populate the review history table.
@app.get("/sessions")
async def list_sessions():
    return get_all_sessions()