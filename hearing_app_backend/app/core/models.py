# app/models.py
import uuid
from datetime import datetime

def now_ts() -> str:
    return datetime.utcnow().isoformat()

def make_session_id() -> str:
    return str(uuid.uuid4())
