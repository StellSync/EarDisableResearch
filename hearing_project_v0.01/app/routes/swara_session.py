# app/routes/swara_session.py
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from uuid import uuid4
from datetime import datetime, timezone
import os
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from bson import ObjectId
 
router = APIRouter()
 
DEFAULT_MONGO = os.getenv(
    "MONGO_URI",
    "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority",
)
DB_NAME = os.getenv("DB_NAME", "hearingdb")
SWARA_COLL = "swara_words"
SESSIONS_COLL = "sessions"
SWARA_CHOICES_COLL = "swara_choices"
 
# Module-level DB handles (lazy init)
_client = None
_db = None
_swara_coll = None
_sessions_coll = None
_swara_choices_coll = None
 
# try import-time init but allow lazy init on first request
try:
    _client = MongoClient(DEFAULT_MONGO, serverSelectionTimeoutMS=3000)
    _client.admin.command("ping")
    _db = _client[DB_NAME]
    _swara_coll = _db[SWARA_COLL]
    _sessions_coll = _db[SESSIONS_COLL]
    _swara_choices_coll = _db[SWARA_CHOICES_COLL]
except Exception:
    _client = None
    _db = None
    _swara_coll = None
    _sessions_coll = None
    _swara_choices_coll = None
 
VOWEL_ORDER = ["අ", "ඉ", "උ", "ඒ", "ඊ", "ඕ", "ඌ"]
 
# --------------------
# Pydantic models
# --------------------
class StartSessionRequest(BaseModel):
    user_id: str = Field(..., example="test_user_1143")
 
 
class StartSessionResponse(BaseModel):
    id: str
    session_id: str
    user_id: str
    started_at: datetime
    is_active: bool
    consonants_tested: List[Any] = []
 
 
class QuestionOption(BaseModel):
    id: str
    sinhala_word: str
    singlish_word: Optional[str] = None
    audio_path: Optional[str] = None
    main_vowel_char: Optional[str] = None
    main_vowel_name: Optional[str] = None
    index: Optional[str] = None
    section: Optional[str] = None
 
 
class NextQuestionResponse(BaseModel):
    session_id: str
    question_id: str
    correct: QuestionOption
    similar: Optional[QuestionOption] = None
    other_hint: Optional[str] = "other"
 
 
class AnswerRequest(BaseModel):
    selected_key: Optional[str] = Field(None, example="correct")  # 'correct'|'similar'|'other'
    selected_id: Optional[str] = Field(None, example="690b2afd04974d8adfc0adea")  # prefer this
 
 
class AnswerResponse(BaseModel):
    session_id: str
    question_id: str
    result: str
    message: Optional[str] = None
    next_action: Optional[str] = None
    # optionally include next question payload fields if server prepared next
    correct: Optional[QuestionOption] = None
    similar: Optional[QuestionOption] = None
    other_hint: Optional[str] = None
 
 
# --------------------
# Helpers
# --------------------
def utcnow():
    return datetime.now(timezone.utc)
 
 
def objid_str(oid):
    return str(oid)
 
 
def _lazy_init_db():
    """
    Initialize DB handles if they are None. Raise HTTPException(500) if can't connect.
    """
    global _client, _db, _swara_coll, _sessions_coll, _swara_choices_coll
    if _swara_coll is not None and _sessions_coll is not None and _swara_choices_coll is not None:
        return
    try:
        client = MongoClient(DEFAULT_MONGO, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
        _client = client
        _db = db
        _swara_coll = db[SWARA_COLL]
        _sessions_coll = db[SESSIONS_COLL]
        _swara_choices_coll = db[SWARA_CHOICES_COLL]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database connection not available: {exc}")
 
 
def to_option(doc: Dict):
    """Return option payload with an 'id' field (stringified ObjectId)."""
    return {
        "id": objid_str(doc["_id"]),
        "sinhala_word": doc.get("sinhala_word"),
        "singlish_word": doc.get("singlish_word"),
        "audio_path": doc.get("audio_path"),
        "main_vowel_char": doc.get("main_vowel_char"),
        "main_vowel_name": doc.get("main_vowel_name"),
        "index": doc.get("index"),
        "section": doc.get("section"),
    }
 
 
def pick_word_by_vowel(vowel_char: str, exclude_ids: Optional[List[str]] = None):
    """
    Return a random swara word matching vowel_char, not in exclude_ids.
    """
    _lazy_init_db()
    query = {"main_vowel_char": vowel_char}
    if exclude_ids:
        try:
            query["_id"] = {"$nin": [ObjectId(x) for x in exclude_ids]}
        except Exception:
            pass
    res = list(_swara_coll.aggregate([{"$match": query}, {"$sample": {"size": 1}}]))
    return res[0] if res else None
 
 
def pick_random_word(exclude_ids: Optional[List[str]] = None):
    """Pick any random swara word (fallback)."""
    _lazy_init_db()
    query = {}
    if exclude_ids:
        try:
            query["_id"] = {"$nin": [ObjectId(x) for x in exclude_ids]}
        except Exception:
            pass
    res = list(_swara_coll.aggregate([{"$match": query}, {"$sample": {"size": 1}}]))
    return res[0] if res else None
 
 
def find_similar_by_index_and_section(base_doc: Dict):
    """Find another word with same index+section (prefer different vowel)."""
    _lazy_init_db()
    q = {
        "index": base_doc.get("index"),
        "section": base_doc.get("section"),
        "_id": {"$ne": base_doc["_id"]},
        "main_vowel_char": {"$ne": base_doc.get("main_vowel_char")},
    }
    doc = _swara_coll.find_one(q)
    if doc:
        return doc
    q2 = {"index": base_doc.get("index"), "section": base_doc.get("section"), "_id": {"$ne": base_doc["_id"]}}
    return _swara_coll.find_one(q2)
 
 
def session_tested_ids(session_doc: Dict) -> List[str]:
    """Return all word ids already tested in this session (from history/current)."""
    ids = []
    history = session_doc.get("history", [])
    for h in history:
        cid = h.get("correct_id")
        if cid:
            ids.append(cid)
    cur = session_doc.get("current")
    if cur and cur.get("correct_id"):
        ids.append(cur.get("correct_id"))
    return ids
 
 
def save_swara_choice(session_id: str, user_id: str, word_doc: Dict, chosen_option: str, is_verification: bool = False):
    """
    Save a swara_choices document as per your provided shape.
    """
    _lazy_init_db()
    doc = {
        "session_id": session_id,
        "user_id": user_id,
        "word_presented": word_doc.get("sinhala_word"),
        "chosen_option": chosen_option,  # 'correct'|'similar'|'other'
        "is_verification": is_verification,
        "timestamp": utcnow(),
        "word_id": objid_str(word_doc["_id"]),
    }
    res = _swara_choices_coll.insert_one(doc)
    return res.inserted_id
 
 
def append_session_tested_entry(session_id: str, vowel_char: str, result: str, word_doc: Dict, is_verification: bool = False):
    """
    Append an entry to sessions.consonants_tested with the structure you showed.
    """
    _lazy_init_db()
    entry = {
        "consonant": {"character": word_doc.get("sinhala_word"), "name": word_doc.get("singlish_word")},
        "result": result,
        "is_verification": is_verification,
        "timestamp": utcnow(),
        "word_id": objid_str(word_doc["_id"]),
    }
    _sessions_coll.update_one({"session_id": session_id}, {"$push": {"consonants_tested": entry}})
 
 
def next_vowel_after(vowel_char: Optional[str]) -> str:
    if vowel_char in VOWEL_ORDER:
        i = VOWEL_ORDER.index(vowel_char)
        return VOWEL_ORDER[(i + 1) % len(VOWEL_ORDER)]
    return VOWEL_ORDER[0]
 
 
# --------------------
# Routes
# --------------------
@router.post("/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest):
    _lazy_init_db()
    session_id = str(uuid4())
    now = utcnow()
    doc = {
        "session_id": session_id,
        "user_id": payload.user_id,
        "started_at": now,
        "consonants_to_verify": [],
        "verified_consonants": [],
        "current_consonant": None,
        "consonants_tested": [],
        "is_active": True,
        "current": None,
        "history": [],
        "vowel_progress": {"current_vowel": None, "attempts_for_vowel": 0},
    }
    res = _sessions_coll.insert_one(doc)
    return StartSessionResponse(
        id=objid_str(res.inserted_id),
        session_id=session_id,
        user_id=payload.user_id,
        started_at=now,
        is_active=True,
        consonants_tested=[],
    )
 
 
@router.post("/{session_id}/next", response_model=NextQuestionResponse)
def next_question(session_id: str = Path(..., description="UUID session_id")):
    """
    Return the current prepared question, or prepare a new one according to vowel_progress rules.
 
    Behavior:
      - If session.current exists -> return it (server-prepared question).
      - Else prepare a question:
          * If vowel_progress.current_vowel is set and attempts_for_vowel < 2 -> pick a new word with same vowel, excluding tested ids.
          * Else pick a word from next vowel in VOWEL_ORDER (or first if none).
      - Each question contains 'correct' (word chosen) and a 'similar' (same index+section) if available.
    """
    _lazy_init_db()
    session = _sessions_coll.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(404, "Session not found")
    if not session.get("is_active", True):
        raise HTTPException(400, "Session is not active")
 
    # If server already prepared a current question, return that to avoid races
    current = session.get("current")
    if current:
        # fetch correct doc and similar
        try:
            correct_doc = _swara_coll.find_one({"_id": ObjectId(current["correct_id"])})
        except Exception:
            correct_doc = None
        if not correct_doc:
            # clear current and fall through to prepare new
            _sessions_coll.update_one({"session_id": session_id}, {"$set": {"current": None}})
        else:
            similar_doc = find_similar_by_index_and_section(correct_doc)
            return {
                "session_id": session_id,
                "question_id": current["question_id"],
                "correct": to_option(correct_doc),
                "similar": to_option(similar_doc) if similar_doc else None,
                "other_hint": "other",
            }
 
    # prepare new question
    vp = session.get("vowel_progress", {"current_vowel": None, "attempts_for_vowel": 0})
    cur_vowel = vp.get("current_vowel")
    attempts = vp.get("attempts_for_vowel", 0)
    tested_ids = session_tested_ids(session)
 
    chosen_doc = None
    # If we already have a vowel to continue and attempts < 2 -> keep same vowel
    if cur_vowel and attempts < 2:
        chosen_doc = pick_word_by_vowel(cur_vowel, exclude_ids=tested_ids)
    # else pick next vowel
    if not chosen_doc:
        next_v = next_vowel_after(cur_vowel)
        chosen_doc = pick_word_by_vowel(next_v, exclude_ids=tested_ids)
        # set progress to the newly chosen vowel (even if attempts reset)
        cur_vowel = next_v
        attempts = 0
 
    # If still no chosen_doc, fallback to any random not tested, then any
    if not chosen_doc:
        chosen_doc = pick_random_word(exclude_ids=tested_ids)
    if not chosen_doc:
        chosen_doc = _swara_coll.find_one({})
    if not chosen_doc:
        raise HTTPException(500, "No swara words found")
 
    similar_doc = find_similar_by_index_and_section(chosen_doc)
 
    # prepare session.current
    question_id = str(uuid4())
    now = utcnow()
    new_current = {
        "question_id": question_id,
        "correct_id": objid_str(chosen_doc["_id"]),
        "correct_index": chosen_doc.get("index"),
        "correct_vowel": chosen_doc.get("main_vowel_char"),
        "attempts_for_this_vowel": attempts,  # attempts so far before asking this question
        "started_at": now,
    }
    # set vowel_progress.current_vowel and attempts_for_vowel preserved
    _sessions_coll.update_one(
        {"session_id": session_id},
        {"$set": {"current": new_current, "vowel_progress.current_vowel": cur_vowel, "vowel_progress.attempts_for_vowel": attempts}},
    )
 
    return {
        "session_id": session_id,
        "question_id": question_id,
        "correct": to_option(chosen_doc),
        "similar": to_option(similar_doc) if similar_doc else None,
        "other_hint": "other",
    }
 
 
@router.post("/{session_id}/answer", response_model=AnswerResponse)
def submit_answer(session_id: str, payload: AnswerRequest):
    """
    Save the user's choice, update session history and vowel_progress, and either:
      - present another word with same vowel (but not previously tested), up to 2 times, or
      - move to next vowel and present a new word.
    """
    _lazy_init_db()
    session = _sessions_coll.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(404, "Session not found")
    if not session.get("current"):
        raise HTTPException(400, "No active question; call /next first")
 
    current = session["current"]
    correct_id = current.get("correct_id")
    try:
        correct_doc = _swara_coll.find_one({"_id": ObjectId(correct_id)})
    except Exception:
        correct_doc = None
    if not correct_doc:
        # clear current and error
        _sessions_coll.update_one({"session_id": session_id}, {"$set": {"current": None}})
        raise HTTPException(500, "Current word not found in DB")
 
    # interpret selection
    selected_is_correct = False
    selected_is_similar = False
    selected_is_other = False
 
    if payload.selected_id:
        try:
            sel_doc = _swara_coll.find_one({"_id": ObjectId(payload.selected_id)})
            if sel_doc and str(sel_doc["_id"]) == correct_id:
                selected_is_correct = True
            else:
                if sel_doc and sel_doc.get("index") == correct_doc.get("index"):
                    selected_is_similar = True
                else:
                    selected_is_other = True
        except Exception:
            return {
                "session_id": session_id,
                "question_id": current.get("question_id"),
                "result": "invalid",
                "message": "selected_id is not a valid ObjectId",
            }
    else:
        key = (payload.selected_key or "").lower()
        if key == "correct":
            selected_is_correct = True
        elif key == "similar":
            selected_is_similar = True
        elif key == "other":
            selected_is_other = True
        else:
            return {
                "session_id": session_id,
                "question_id": current.get("question_id"),
                "result": "invalid",
                "message": "Provide selected_key as one of: correct, similar, other or selected_id.",
            }
 
    user_id = session.get("user_id")
 
    # save swara_choices doc
    chosen_option = "correct" if selected_is_correct else ("similar" if selected_is_similar else "other")
    save_swara_choice(session_id, user_id, correct_doc, chosen_option, is_verification=False)
 
    # append session tested entry
    append_session_tested_entry(session_id, correct_doc.get("main_vowel_char"), chosen_option, correct_doc, is_verification=False)
 
    # update vowel progress
    vp = session.get("vowel_progress", {"current_vowel": None, "attempts_for_vowel": 0})
    current_vowel = vp.get("current_vowel") or current.get("correct_vowel")
    attempts = vp.get("attempts_for_vowel", 0) + 1  # one more attempt for this vowel
    # persist attempts
    _sessions_coll.update_one({"session_id": session_id}, {"$set": {"vowel_progress.attempts_for_vowel": attempts}})
 
    # record history
    history_entry = {
        "question_id": current.get("question_id"),
        "correct_id": current.get("correct_id"),
        "selected": chosen_option,
        "result": "correct" if selected_is_correct else "incorrect",
        "timestamp": utcnow(),
    }
    _sessions_coll.update_one({"session_id": session_id}, {"$push": {"history": history_entry}, "$set": {"current": None}})
 
    # Decide next action:
    # if attempts < 2 -> present another word with same vowel (excluding already tested)
    tested_ids = session_tested_ids(session)  # includes the word we just recorded (it was in history before we appended? ensure unique)
    tested_ids = list(set(tested_ids))
    # include the just-tested word id as well
    tested_ids.append(current.get("correct_id"))
 
    if attempts < 2:
        # try to find another word with same vowel not in tested_ids
        next_doc = pick_word_by_vowel(current_vowel, exclude_ids=tested_ids)
        if next_doc:
            # prepare new current for same vowel
            new_qid = str(uuid4())
            new_current = {
                "question_id": new_qid,
                "correct_id": objid_str(next_doc["_id"]),
                "correct_index": next_doc.get("index"),
                "correct_vowel": next_doc.get("main_vowel_char"),
                "attempts_for_this_vowel": attempts,
                "started_at": utcnow(),
            }
            _sessions_coll.update_one(
                {"session_id": session_id},
                {"$set": {"current": new_current, "vowel_progress.current_vowel": current_vowel, "vowel_progress.attempts_for_vowel": attempts}},
            )
            similar_doc = find_similar_by_index_and_section(next_doc)
            return {
                "session_id": session_id,
                "question_id": new_qid,
                "result": "incorrect_similar_or_other" if not selected_is_correct else "correct_then_repeat",
                "message": f"Next: another example of same vowel ({current_vowel}).",
                "next_action": "repeat_same_vowel",
                "correct": to_option(next_doc),
                "similar": to_option(similar_doc) if similar_doc else None,
                "other_hint": "other",
            }
        # else: couldn't find another same-vowel word -> fallthrough to move to next vowel
 
    # attempts >= 2 or no alternative found -> move to next vowel
    next_vowel = next_vowel_after(current_vowel)
    # reset attempts to 0 for the new vowel in DB
    _sessions_coll.update_one({"session_id": session_id}, {"$set": {"vowel_progress.current_vowel": next_vowel, "vowel_progress.attempts_for_vowel": 0}})
 
    # pick a new word for next_vowel not in tested_ids
    next_doc = pick_word_by_vowel(next_vowel, exclude_ids=tested_ids)
    if not next_doc:
        next_doc = pick_random_word(exclude_ids=tested_ids)
    if not next_doc:
        next_doc = _swara_coll.find_one({})
 
    if not next_doc:
        return {
            "session_id": session_id,
            "question_id": current.get("question_id"),
            "result": "finished",
            "message": "No more words available",
            "next_action": "no_more_words",
        }
 
    new_qid = str(uuid4())
    new_current = {
        "question_id": new_qid,
        "correct_id": objid_str(next_doc["_id"]),
        "correct_index": next_doc.get("index"),
        "correct_vowel": next_doc.get("main_vowel_char"),
        "attempts_for_this_vowel": 0,
        "started_at": utcnow(),
    }
    _sessions_coll.update_one(
        {"session_id": session_id},
        {"$set": {"current": new_current, "vowel_progress.current_vowel": next_vowel, "vowel_progress.attempts_for_vowel": 0}},
    )
    similar_doc = find_similar_by_index_and_section(next_doc)
    return {
        "session_id": session_id,
        "question_id": new_qid,
        "result": "moved_to_next_vowel",
        "message": f"Moving to next vowel: {next_vowel}",
        "next_action": "next_vowel",
        "correct": to_option(next_doc),
        "similar": to_option(similar_doc) if similar_doc else None,
        "other_hint": "other",
    }