from fastapi import APIRouter, HTTPException, Path
from typing import Optional, List, Any, Dict
from uuid import uuid4
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient
import logging

from ..schemas_sentence import (
    SentenceStartSessionRequest,
    SentenceStartSessionResponse,
    SentenceNextQuestionResponse,
    SentenceAnswerRequest,
    SentenceAnswerResponse,
    SentenceQuestionOption,
    SentenceSessionResult,
    VowelResult,
)

router = APIRouter()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_MONGO = "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "hearingdb"
COLL_SENTENCE = "sentences"       # sentences documents (sentence bank)
COLL_SESSIONS = "sentence_sessions"
COLL_CHOICES = "sentence_choices"

_client = MongoClient(DEFAULT_MONGO)
_db = _client[DB_NAME]
_sent_coll = _db[COLL_SENTENCE]
_sess_coll = _db[COLL_SESSIONS]
_choice_coll = _db[COLL_CHOICES]

VOWEL_ORDER = ["අ", "ඉ", "උ", "ඒ", "ඊ", "ඕ", "ඌ", "ඇ", "ඔ", "ආ"]

def utcnow():
    return datetime.now(timezone.utc)

def to_option(doc: Dict, pair_index: int = 0) -> SentenceQuestionOption:
    return SentenceQuestionOption(
        id=str(doc["_id"]),
        index=doc.get("index"),
        section=doc.get("section"),
        sentence=doc["sentences"][pair_index],
        sentence_translit=doc["sentences_translit"][pair_index] if doc.get("sentences_translit") else None,
        audio_path=doc["audio_paths"][pair_index] if doc.get("audio_paths") else None,
        highlighted_word=doc["highlighted_words"][pair_index] if doc.get("highlighted_words") else None,
        vowel_char=doc["highlighted_vowels"][pair_index].get("main_vowel_char") if doc.get("highlighted_vowels") else None,
        vowel_name=doc["highlighted_vowels"][pair_index].get("main_vowel_name") if doc.get("highlighted_vowels") else None,
    )

# ------------------------------
# Session routes
# ------------------------------

@router.post("/start", response_model=SentenceStartSessionResponse)
def start_session(payload: SentenceStartSessionRequest):
    session_id = str(uuid4())
    now = utcnow()
    doc = {
        "session_id": session_id,
        "user_id": payload.user_id,
        "started_at": now,
        "sentences_tested": [],
        "is_active": True,
        "vowel_progress": {"current_vowel": None, "attempts": 0, "total_tested": 0},
        "current": None,
    }
    res = _sess_coll.insert_one(doc)
    logger.info("Started sentence session %s for user %s", session_id, payload.user_id)
    return SentenceStartSessionResponse(
        id=str(res.inserted_id),
        session_id=session_id,
        user_id=payload.user_id,
        started_at=now,
        is_active=True,
        sentences_tested=[],
    )

@router.post("/{session_id}/next", response_model=SentenceNextQuestionResponse)
def next_question(session_id: str):
    session = _sess_coll.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(404, "Session not found")

    cur_vowel = session.get("vowel_progress", {}).get("current_vowel")
    # build a query for the chosen vowel (if any)
    query = {}
    if cur_vowel:
        query["highlighted_vowels.main_vowel_char"] = cur_vowel

    try:
        total_docs = _sent_coll.count_documents({})
        logger.debug("Sentences collection total docs: %d", total_docs)
        logger.debug("Query for sentence selection: %s", query)

        cursor = _sent_coll.aggregate([{"$match": query}, {"$sample": {"size": 1}}])
        doc = next(cursor, None)
        if not doc:
            sample = _sent_coll.find_one()
            logger.warning("No sentence matched query=%s; sample doc: %s", query, sample)
            raise HTTPException(404, "No sentence found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error retrieving sentence: %s", e)
        raise HTTPException(500, f"Error retrieving sentence: {str(e)}")

    question_id = str(uuid4())
    new_current = {
        "question_id": question_id,
        "correct_id": str(doc["_id"]),
        "vowel": cur_vowel or doc["highlighted_vowels"][0]["main_vowel_char"],
        "started_at": utcnow(),
    }
    _sess_coll.update_one({"session_id": session_id}, {"$set": {"current": new_current}})
    logger.info("Prepared next question %s for session %s (vowel=%s)", question_id, session_id, new_current["vowel"])

    correct = to_option(doc, 0)
    similar = to_option(doc, 1) if len(doc.get("sentences", [])) > 1 else None

    return SentenceNextQuestionResponse(
        session_id=session_id,
        question_id=question_id,
        correct=correct,
        similar=similar,
    )

@router.post("/{session_id}/answer", response_model=SentenceAnswerResponse)
def answer_sentence(session_id: str, payload: SentenceAnswerRequest):
    session = _sess_coll.find_one({"session_id": session_id})
    if not session or not session.get("current"):
        raise HTTPException(404, "Active session not found")

    current = session["current"]
    question_id = current["question_id"]
    vowel = current.get("vowel")
    user_id = session.get("user_id")  # THIS is important — use to store in choices

    # normalize result key
    result = (payload.selected_key or "unknown")
    is_correct = (result == "correct")

    # Insert choice document — now includes user_id and chosen_option for consistency with other activities
    choice_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "question_id": question_id,
        "user_choice": result,
        "chosen_option": result,        # duplicate for other endpoints that expect 'chosen_option'
        "vowel": vowel,
        "is_correct": is_correct,
        "timestamp": utcnow()
    }
    _choice_coll.insert_one(choice_doc)
    logger.info("Inserted choice for session=%s user=%s question=%s result=%s", session_id, user_id, question_id, result)

    # Update session: append tested question and increment total_tested
    _sess_coll.update_one(
        {"session_id": session_id},
        {"$push": {"sentences_tested": {"question_id": question_id, "result": result, "timestamp": utcnow()}},
         "$inc": {"vowel_progress.total_tested": 1}}
    )

    # Compute tested vowels for the session to avoid repetition logic
    tested_choices = list(_choice_coll.find({"session_id": session_id}))
    tested_vowels = {c.get("vowel") for c in tested_choices if c.get("vowel") is not None}

    # Find next available vowel with untested sentences (cycle through VOWEL_ORDER)
    next_doc = None
    next_vowel = None
    attempts = 0
    start_index = VOWEL_ORDER.index(vowel) if vowel in VOWEL_ORDER else 0
    total_vowels = len(VOWEL_ORDER)

    while attempts < total_vowels:
        candidate_vowel = VOWEL_ORDER[(start_index + attempts + 1) % total_vowels]

        # If we've tested all vowels already, allow any candidate
        if len(tested_vowels) >= total_vowels:
            pipeline = [
                {"$match": {"highlighted_vowels.main_vowel_char": candidate_vowel}},
                {"$sample": {"size": 1}}
            ]
        else:
            if candidate_vowel in tested_vowels:
                attempts += 1
                continue
            pipeline = [
                {"$match": {"highlighted_vowels.main_vowel_char": candidate_vowel}},
                {"$sample": {"size": 1}}
            ]

        doc_cursor = _sent_coll.aggregate(pipeline)
        next_doc = next(doc_cursor, None)
        if next_doc:
            next_vowel = candidate_vowel
            break
        attempts += 1

    if not next_doc:
        # fallback: sample any sentence
        try:
            next_doc = next(_sent_coll.aggregate([{"$sample": {"size": 1}}]), None)
        except StopIteration:
            next_doc = None

        if not next_doc:
            return SentenceAnswerResponse(
                session_id=session_id,
                question_id=question_id,
                result=result,
                message="No more sentences available"
            )
        next_vowel = next_doc["highlighted_vowels"][0]["main_vowel_char"]

    # Update session with next vowel & reset current
    next_question_id = str(uuid4())
    new_current = {
        "question_id": next_question_id,
        "correct_id": str(next_doc["_id"]),
        "vowel": next_vowel,
        "started_at": utcnow()
    }

    _sess_coll.update_one(
        {"session_id": session_id},
        {"$set": {
            "vowel_progress": {"current_vowel": next_vowel, "attempts": 0, "total_tested": len(tested_vowels)},
            "current": new_current
        }}
    )

    correct_opt = to_option(next_doc, 0)
    similar_opt = to_option(next_doc, 1) if len(next_doc.get("sentences", [])) > 1 else None

    return SentenceAnswerResponse(
        session_id=session_id,
        question_id=next_question_id,
        result=result,
        message=f"Next vowel: {next_vowel}",
        correct=correct_opt,
        similar=similar_opt
    )

@router.get("/{session_id}/result", response_model=SentenceSessionResult)
def get_result(session_id: str):
    session = _sess_coll.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(404, "Session not found")

    tested = list(_choice_coll.find({"session_id": session_id}))
    vowels_stats: Dict[str, Dict[str, Any]] = {}

    for c in tested:
        v = c.get("vowel", "Unknown")
        if v not in vowels_stats:
            vowels_stats[v] = {"vowel": v, "correct": 0, "incorrect": 0, "attempts": 0}
        stats = vowels_stats[v]
        stats["attempts"] += 1
        if c.get("is_correct"):
            stats["correct"] += 1
        else:
            stats["incorrect"] += 1

    return SentenceSessionResult(
        session_id=session_id,
        user_id=session.get("user_id"),
        vowels_tested=[VowelResult(**stats) for stats in vowels_stats.values()],
        started_at=session.get("started_at"),
        ended_at=utcnow(),
        total_sentences_tested=len(tested),
    )
