# Add these new classes to app/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ConsonantRowIn(BaseModel):
    section: str
    index: str
    sinhala_word: str
    changing_consonant_character: str
    changing_consonant_name: str

class ConsonantDocOut(BaseModel):
    id: str = Field(..., alias="_id")
    section: str
    index: str
    sinhala_word: str
    singlish: str
    changing_consonant: Dict[str, str]  # {"character": "...", "name": "..."}
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None

class ConsonantChangeInfo(BaseModel):
    character: str
    name: str