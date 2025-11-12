from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class SentenceHighlightedVowel(BaseModel):
    word: str
    singlish: str
    main_vowel_char: Optional[str] = ""
    main_vowel_name: Optional[str] = ""

class SentenceDocOut(BaseModel):
    id: str = Field(..., alias="_id")
    section: str
    index: str
    sentences: List[str]
    sentences_translit: List[str]
    highlighted_words: List[str]
    highlighted_translit: List[str]
    highlighted_vowels: List[SentenceHighlightedVowel]
    audio_paths: List[str]

class SentenceStartSessionRequest(BaseModel):
    user_id: str = Field(..., example="test_user_101")

class SentenceStartSessionResponse(BaseModel):
    id: str
    session_id: str
    user_id: str
    started_at: datetime
    is_active: bool
    sentences_tested: List[Any] = []

class SentenceQuestionOption(BaseModel):
    id: str
    index: str
    section: str
    sentence: str
    sentence_translit: Optional[str] = None
    audio_path: Optional[str] = None
    highlighted_word: Optional[str] = None
    vowel_char: Optional[str] = None
    vowel_name: Optional[str] = None

class SentenceNextQuestionResponse(BaseModel):
    session_id: str
    question_id: str
    correct: SentenceQuestionOption
    similar: Optional[SentenceQuestionOption] = None
    other_hint: Optional[str] = "other"

class SentenceAnswerRequest(BaseModel):
    selected_key: Optional[str] = Field(None, example="correct")
    selected_id: Optional[str] = None

class SentenceAnswerResponse(BaseModel):
    session_id: str
    question_id: str
    result: str
    message: Optional[str] = None
    next_action: Optional[str] = None
    correct: Optional[SentenceQuestionOption] = None
    similar: Optional[SentenceQuestionOption] = None
    other_hint: Optional[str] = None

class VowelResult(BaseModel):
    """Model for individual vowel test results"""
    vowel: str
    correct: int = 0
    incorrect: int = 0
    attempts: int = 0

class SentenceSessionResult(BaseModel):
    session_id: str
    user_id: str
    vowels_tested: List[VowelResult]
    started_at: datetime
    ended_at: Optional[datetime]
    total_sentences_tested: int
