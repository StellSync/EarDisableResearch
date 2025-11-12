from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class WiyanjanaAnswer(BaseModel):
    word: str
    audio_path: str
    changing_consonant: Dict[str, str]

class WiyanjanaOptions(BaseModel):
    correct_answer: WiyanjanaAnswer
    similar_answer: WiyanjanaAnswer
    other_option: bool = True

class WiyanjanaSessionStartRequest(BaseModel):
    """Request model for starting a new session"""
    user_id: str

class WiyanjanaSessionStart(BaseModel):
    session_id: str
    user_id: str
    started_at: datetime

class WiyanjanaSimpleChoice(BaseModel):
    selected_key: str = Field(..., pattern="^(correct|similar|other)$")
    selected_id: str

class WiyanjanaUserChoice(BaseModel):
    session_id: str
    user_id: str
    word_presented: str
    chosen_option: str = Field(..., pattern="^(correct|similar|other)$")
    is_verification: bool
    consonant_tested: Dict[str, str]
    timestamp: datetime

# NEW: per-consonant result model
class WiyanjanaConsonantResult(BaseModel):
    consonant: str
    correct: int
    incorrect: int
    attempts: int

class WiyanjanaSessionResult(BaseModel):
    session_id: str
    user_id: str
    consonants_tested: List[WiyanjanaConsonantResult]
    started_at: datetime
    ended_at: datetime
    total_words_tested: int
