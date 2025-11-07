from fastapi import APIRouter, Depends, HTTPException, Query
from ...auth.token import verify_token
from ...db import get_mongo
from ...services.adaptive_service import pick_next

router = APIRouter(prefix="/api/v1/activity", tags=["activity"])

@router.get("/word")
def get_next_word(session_id: str = Query(...), difficulty_hint: str = None, user=Depends(verify_token)):
    db = get_mongo()
    events = []
    try:
        if hasattr(db, "responses"):
            events = list(db.responses.find({"session_id": session_id}))
        else:
            events = db.collection("responses").find({})
    except Exception:
        events = []
    try:
        item = pick_next(events, difficulty_hint)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail="No lexicon items available")
    # naive options (TODO: improve distractor selection)
    return {"item": item, "options": [item["word_id"]]}

@router.get("/sentence")
def get_next_sentence(session_id: str = Query(...), user=Depends(verify_token)):
    # placeholder: return word item for now
    return get_next_word(session_id)
