from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class SessionCreate(BaseModel):
    user_id: str
    device_info: Optional[str] = None

class ActivityRequest(BaseModel):
    session_id: str
    difficulty_hint: Optional[str] = None

class ResponseSubmit(BaseModel):
    session_id: str
    presented_item_id: str
    options_shown: List[str]
    user_choice: Optional[str] = None
    typed_text: Optional[str] = None
    correct: Optional[bool] = None
    reaction_time_ms: Optional[int] = None
    audio_path: Optional[str] = None
    timestamp: Optional[datetime] = None
    target_phoneme: Optional[str] = None
