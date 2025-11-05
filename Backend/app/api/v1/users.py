from fastapi import APIRouter
from ...db import get_mongo

router = APIRouter(prefix="/api/v1/user", tags=["user"])

@router.get("/{user_id}/progress")
def get_user_progress(user_id: str):
    db = get_mongo()
    try:
        responses = list(db.responses.find({"user_id": user_id})) if hasattr(db, "responses") else db.collection("responses").find({})
    except Exception:
        responses = []
    sessions = {}
    for r in responses:
        sid = r.get("session_id")
        sessions.setdefault(sid, {"correct":0, "total":0, "events":[]})
        if r.get("correct") is True: sessions[sid]["correct"] += 1
        sessions[sid]["total"] += 1
        sessions[sid]["events"].append(r)
    out = []
    for sid, v in sessions.items():
        rate = v["correct"]/v["total"] if v["total"] else None
        out.append({"session_id": sid, "correct": v["correct"], "total": v["total"], "accuracy": rate})
    return {"user_id": user_id, "sessions": out}
