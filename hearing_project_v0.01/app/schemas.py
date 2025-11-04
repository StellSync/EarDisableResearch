# app/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class RowIn(BaseModel):
    section: str
    index: str
    sinhala_word: str
    main_vowel_name: str
    main_vowel_char: Optional[str] = ""

class DocOut(BaseModel):
    id: str = Field(..., alias="_id")
    section: str
    index: str
    sinhala_word: str
    singlish: Optional[str] = ""
    main_vowel_name: Optional[str] = ""
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None

class SessionStartResp(BaseModel):
    session_id: str
    vowel_sequence: List[str]
    started_at: str

class UserChoice(BaseModel):
    session_id: str
    vowel: str
    role: str  # "primary" or "confirm"
    choice: str  # "correct"|"similar"|"other"
    presented_doc_id: str
    chosen_doc_id: Optional[str] = None
