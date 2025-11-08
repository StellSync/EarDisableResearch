# app/routes/sentence_session.py
from fastapi import APIRouter, HTTPException, Path
from typing import Optional, List, Any, Dict
from uuid import uuid4
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient

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

DEFAULT_MONGO = "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "hearingdb"
COLL_SENTENCE = "sentences"  # Updated to use the correct collection name
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
        sentence_translit=doc["sentences_translit"][pair_index],
        audio_path=doc["audio_paths"][pair_index],
        highlighted_word=doc["highlighted_words"][pair_index],
        vowel_char=doc["highlighted_vowels"][pair_index]["main_vowel_char"],
        vowel_name=doc["highlighted_vowels"][pair_index]["main_vowel_name"],
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
        "vowel_progress": {"current_vowel": None, "attempts": 0},
        "current": None,
    }
    res = _sess_coll.insert_one(doc)
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
    attempts = session.get("vowel_progress", {}).get("attempts", 0)

    # Get a new sentence where the first highlighted word matches vowel
    query = {}
    if cur_vowel:
        query["highlighted_vowels.main_vowel_char"] = cur_vowel

    try:
        # Check if we have any documents in the collection
        total_docs = _sent_coll.count_documents({})
        print(f"Total documents in sentences collection: {total_docs}")
        
        # Log the query we're using
        print(f"Query for sentence: {query}")
        
        doc = _sent_coll.aggregate([{"$match": query}, {"$sample": {"size": 1}}])
        doc = next(doc, None)
        if not doc:
            # Get sample document to check structure
            sample = _sent_coll.find_one()
            print(f"Sample document structure: {sample}")
            raise HTTPException(404, "No sentence found")
    except Exception as e:
        print(f"Error retrieving sentence: {str(e)}")
        raise HTTPException(500, f"Error retrieving sentence: {str(e)}")

    question_id = str(uuid4())
    new_current = {
        "question_id": question_id,
        "correct_id": str(doc["_id"]),
        "vowel": cur_vowel or doc["highlighted_vowels"][0]["main_vowel_char"],
        "started_at": utcnow(),
    }
    _sess_coll.update_one({"session_id": session_id}, {"$set": {"current": new_current}})

    correct = to_option(doc, 0)
    similar = to_option(doc, 1) if len(doc["sentences"]) > 1 else None

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

    result = payload.selected_key or "unknown"
    is_correct = result == "correct"  # Track if answer was correct

    _choice_coll.insert_one({
        "session_id": session_id,
        "question_id": question_id,
        "user_choice": result,
        "vowel": vowel,
        "is_correct": is_correct,  # Add correct/incorrect tracking
        "timestamp": utcnow()
    })

    # Get already tested vowels for this session to avoid repetition
    tested_choices = list(_choice_coll.find({"session_id": session_id}))
    tested_vowels = {c["vowel"] for c in tested_choices}
    
    # Find the next available vowel with untested sentences
    next_doc = None
    next_vowel = None
    attempts = 0
    start_index = VOWEL_ORDER.index(vowel) if vowel in VOWEL_ORDER else 0
    
    # Try each vowel in order until we find one with available sentences
    while attempts < len(VOWEL_ORDER):
        candidate_vowel = VOWEL_ORDER[(start_index + attempts + 1) % len(VOWEL_ORDER)]
        
        # If we've tested all vowels, allow repeating from the start
        if len(tested_vowels) >= len(VOWEL_ORDER):
            pipeline = [
                {"$match": {"highlighted_vowels.main_vowel_char": candidate_vowel}},
                {"$sample": {"size": 1}}
            ]
        else:
            # Only get untested vowels
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
        # If we couldn't find any untested sentences, try any available sentence
        next_doc = _sent_coll.aggregate([{"$sample": {"size": 1}}]).next()
        if not next_doc:
            return SentenceAnswerResponse(
                session_id=session_id, 
                question_id=question_id, 
                result=result, 
                message="No more sentences available"
            )
        next_vowel = next_doc["highlighted_vowels"][0]["main_vowel_char"]
    
    # Update session with next vowel
    _sess_coll.update_one(
        {"session_id": session_id},
        {"$set": {"vowel_progress": {"current_vowel": next_vowel, "attempts": 0}, "current": None}}
    )

    next_question_id = str(uuid4())
    # Set up next question in the session
    new_current = {
        "question_id": next_question_id,
        "correct_id": str(next_doc["_id"]),
        "vowel": next_vowel,
        "started_at": utcnow(),
    }
    
    # Update session with next question and progress
    _sess_coll.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "vowel_progress": {
                    "current_vowel": next_vowel,
                    "attempts": 0,
                    "total_tested": len(tested_vowels)
                },
                "current": new_current
            }
        }
    )

    correct = to_option(next_doc, 0)
    similar = to_option(next_doc, 1) if len(next_doc["sentences"]) > 1 else None

    return SentenceAnswerResponse(
        session_id=session_id,
        question_id=next_question_id,
        result=result,
        message=f"Next vowel: {next_vowel}",
        correct=correct,
        similar=similar,
    )

@router.get("/{session_id}/result", response_model=SentenceSessionResult)
def get_result(session_id: str):
    session = _sess_coll.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(404, "Session not found")

    tested = list(_choice_coll.find({"session_id": session_id}))
    vowels_stats: Dict[str, Dict[str, Any]] = {}
    
    # Initialize stats for each vowel
    for c in tested:
        v = c.get("vowel", "Unknown")
        if v not in vowels_stats:
            vowels_stats[v] = {
                "vowel": v,
                "correct": 0,
                "incorrect": 0,
                "attempts": 0
            }
        
        # Update stats based on correctness
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
