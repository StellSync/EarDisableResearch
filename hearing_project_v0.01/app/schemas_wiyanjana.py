from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class WiyanjanaAnswer(BaseModel):
    word: str
    audio_path: str
    changing_consonant: Dict[str, str]

class WiyanjanaOptions(BaseModel):
    correct_answer: WiyanjanaAnswer
    similar_answer: WiyanjanaAnswer  # Word with similar consonant
    other_option: bool = True  # Always true as "Other" is always an option

class WiyanjanaSessionStart(BaseModel):
    session_id: str
    user_id: str  # For now we'll use random/fake IDs
    started_at: datetime

class WiyanjanaUserChoice(BaseModel):
    session_id: str
    user_id: str
    word_presented: str
    chosen_option: str = Field(
        ...,
        description="The option chosen by the user",
        pattern="^(correct|similar|other)$"  # Only allow these three values
    )
    is_verification: bool  # True if this was a verification question
    consonant_tested: Dict[str, str]  # The consonant being tested
    timestamp: datetime

class WiyanjanaSessionResult(BaseModel):
    session_id: str
    user_id: str
    consonants_tested: List[Dict[str, Any]]  # List of consonants and their test results
    started_at: datetime
    ended_at: datetime
    total_words_tested: int