# app/routes/test_routes.py
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

# import the Pydantic schemas from core.schemas
from ..core.schemas import StartResponse, SubmitRequest, NextActionResponse, WordPayload
from ..services.vowel_service import start_session, submit_answer

router = APIRouter(prefix="/api/tests", tags=["tests"])

@router.get("/start", response_model=StartResponse)
async def api_start(user_id: Optional[str] = Query(None), max_tests: int = Query(5)):
    """
    Start a new test session and return the session_id, vowel sequence and the first word to present.
    """
    res = await start_session(user_id=user_id, max_tests=max_tests)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    session = res.get("session")
    first_word = res.get("first_word")
    return {"session_id": session["session_id"], "vowel_sequence": session["vowel_sequence"], "first_word": first_word}

@router.post("/submit", response_model=NextActionResponse)
async def api_submit(body: SubmitRequest):
    """
    Submit a user's answer for the current presented word.
    Returns the next action: present_confirm / present_primary / finished / present_next plus the next word if applicable.
    """
    res = await submit_answer(body.session_id, body.word_id, body.choice)
    if not res:
        raise HTTPException(status_code=404, detail="Session or word not found")
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res
