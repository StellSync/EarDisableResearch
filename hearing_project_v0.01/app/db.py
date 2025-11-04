# app/db.py
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority")
DB_NAME = os.getenv("DB_NAME", "hearingdb")

_client = None
db = None

def init_client():
    """
    Initialize the AsyncIOMotorClient and set the module-level `db`.
    Should be called at FastAPI startup.
    """
    global _client, db
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
        db = _client[DB_NAME]
    return _client

def close_client():
    global _client, db
    if _client:
        _client.close()
        _client = None
        db = None
