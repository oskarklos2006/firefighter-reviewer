from __future__ import annotations
import json
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from rules.parser import parse_session
from rules.engine import run_rules
from llm.analyzer import analyze_session
from storage.repository import save_verdict, get_all_sessions, update_decision
from storage.database import init_db
from pipeline import review_session_data


app = FastAPI(title="Firefighter Log Reviewer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/review")
async def review_session(file: UploadFile = File(...)):
    try:
        content = await file.read()
        raw = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    try:
        response = await review_session_data(raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    save_verdict(response)
    return response


class DecisionUpdate(BaseModel):
    decision: str  # "PASS", "REJECT", "SEND_BACK"
    controller_note: Optional[str] = None


@app.patch("/sessions/{session_id}/decision")
async def record_decision(session_id: str, body: DecisionUpdate):
    """Record controller's final decision on a session."""
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


@app.get("/sessions")
async def list_sessions():
    """Return all reviewed sessions for the controller dashboard."""
    return get_all_sessions()