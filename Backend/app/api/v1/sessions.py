from fastapi import APIRouter, HTTPException
from uuid import uuid4
from datetime import datetime
from ...db import get_mongo
from ...auth.token import create_token

router = APIRouter(prefix="/api/v1/session", tags=["session"])

@router.post("")
def create_session(payload: dict):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    sid = str(uuid4())
    rec = {"id": sid, "user_id": user_id, "created_at": datetime.utcnow().isoformat(), "device_info": payload.get("device_info")}
    db = get_mongo()
    try:
        # attempt to insert into real Mongo if available, else fallback
        if hasattr(db, "sessions"):
            db.sessions.insert_one(rec)
        else:
            db.collection("sessions").insert_one(rec)
    except Exception:
        pass
    token = create_token(user_id)
    return {"session_id": sid, "token": token}
