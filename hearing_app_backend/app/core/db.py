# app/core/db.py
import os
from typing import Any
from dotenv import load_dotenv

# load .env from repo root if present
load_dotenv()

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority&appName=hearingCluster"
)
DB_NAME = os.getenv("DB_NAME", "farm_auditory")

# Lazily import motor so module import doesn't instantly fail in editors missing motor
try:
    import motor.motor_asyncio as _motor
except Exception as e:
    _motor = None
    # keep a helpful error later if someone tries to use db without motor installed

# Create client & collections (if motor available)
class _DBContainer:
    """Simple container exposing collections as attributes."""
    client: Any = None
    database: Any = None
    words: Any = None
    sessions: Any = None
    results: Any = None

db = _DBContainer()

def init_db():
    """Initialize motor client and collection handles. Safe to call multiple times."""
    global db
    if _motor is None:
        raise RuntimeError("motor is not installed. Please `pip install motor`.")

    if getattr(db, "client", None) is None:
        client = _motor.AsyncIOMotorClient(MONGO_URI)
        database = client[DB_NAME]

        db.client = client
        db.database = database
        db.words = database["words"]
        db.sessions = database["sessions"]
        db.results = database["results"]

# call on import to keep behavior same as before
try:
    init_db()
except Exception:
    # don't raise during import in environments without motor;
    # callers will get a clear error when trying to use db if motor isn't installed.
    pass

def close_db():
    """Close motor client (call on shutdown)."""
    try:
        if getattr(db, "client", None) is not None:
            db.client.close()
    except Exception:
        pass
