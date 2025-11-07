from fastapi import APIRouter, Depends
from ...auth.token import verify_token
from ...db import get_mongo
from datetime import datetime

router = APIRouter(prefix="/api/v1/response", tags=["response"])

@router.post("")
def submit_response(payload: dict, user=Depends(verify_token)):
    payload["received_at"] = datetime.utcnow().isoformat()
    db = get_mongo()
    try:
        if hasattr(db, "responses"):
            db.responses.insert_one(payload)
        else:
            db.collection("responses").insert_one(payload)
    except Exception:
        pass
    return {"status": "ok"}
