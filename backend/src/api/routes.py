from __future__ import annotations
import json
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
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
async def review_session(
    file: UploadFile = File(...),
    force_llm: bool = Query(default=False)
):
    try:
        content = await file.read()
        raw = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    try:
        response = await review_session_data(raw, force_llm=force_llm)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    save_verdict(response)
    return response


class DecisionUpdate(BaseModel):
    decision: str
    controller_note: Optional[str] = None


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


@app.get("/sessions")
async def list_sessions():
    return get_all_sessions()