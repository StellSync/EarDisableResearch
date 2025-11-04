# app/schemas.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class WordPayload(BaseModel):
    _id: str
    section: Optional[str] = None
    index: Optional[str] = None
    sinhala_word: Optional[str] = None
    singlish: Optional[str] = None
    main_vowel_name: Optional[str] = None
    audio_path: Optional[str] = None

class StartResponse(BaseModel):
    session_id: str
    vowel_sequence: List[str]
    first_word: Optional[Dict[str, Any]] = None

class SubmitRequest(BaseModel):
    session_id: str
    word_id: str
    choice: str  # "correct" | "similar" | "other"

class NextActionResponse(BaseModel):
    next_action: str  # "present_confirm" | "present_primary" | "finished" | "present_next"
    word: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, str]] = None
    session_id: Optional[str] = None
