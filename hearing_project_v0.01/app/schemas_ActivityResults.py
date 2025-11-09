# app/schemas_ActivityResults.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class ResultItem(BaseModel):
    id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    word_presented: Optional[str] = None
    chosen_option: Optional[str] = None  # "correct" | "similar" | "other"
    is_verification: Optional[bool] = None
    consonant_tested: Optional[Dict[str, str]] = None
    timestamp: Optional[datetime] = None
    section: Optional[str] = None
    index: Optional[str] = None

class PaginatedResults(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ResultItem]

class SessionSummaryItem(BaseModel):
    session_id: Optional[str]
    user_id: Optional[str]
    first_timestamp: Optional[datetime]
    last_timestamp: Optional[datetime]
    attempts: int
    correct: int
    similar: int
    other: int
    accuracy: Optional[float] = None  # correct / attempts

class UserSummary(BaseModel):
    user_id: str
    total_sessions: int
    total_attempts: int
    total_correct: int
    total_similar: int
    total_other: int
    accuracy: Optional[float] = None

class PerUserAggregate(BaseModel):
    user_id: str
    attempts: int
    correct: int
    similar: int
    other: int
    accuracy: Optional[float] = None

class OverallSummary(BaseModel):
    total_users: int
    total_attempts: int
    total_correct: int
    total_similar: int
    total_other: int
    accuracy: Optional[float]
    per_user: List[PerUserAggregate] = []
