from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime
import random
import uuid
from bson.objectid import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..db import db, get_database
from ..schemas_wiyanjana import (
    WiyanjanaSessionStart,
    WiyanjanaSessionStartRequest,
    WiyanjanaOptions,
    WiyanjanaUserChoice,
    WiyanjanaSessionResult,
    WiyanjanaAnswer
)

router = APIRouter(prefix="/wiyanjana", tags=["wiyanjana"])


# Helper functions
async def get_verification_word_pair(db: AsyncIOMotorDatabase, consonant: str, previous_word_id: str = None):
    """Return a main word that contains the given consonant and a similar-sounding alternative with a different consonant.
    Exclude previous_word_id (if provided) so verification shows a different word from the first presentation.
    Both words MUST have the same index AND section to ensure consistent word patterns."""
    
    # First, find all words with the target consonant and their indices
    match_stage = {"changing_consonant.character": consonant}
    if previous_word_id:
        try:
            match_stage["_id"] = {"$ne": ObjectId(previous_word_id)}
        except Exception:
            # ignore invalid ObjectId
            pass

    # Add a lookup to check which indices/sections have matching pairs
    pipeline = [
        {"$match": match_stage},
        # First, get the section/index combinations that have alternatives
        {"$lookup": {
            "from": "consonant_words",
            "let": {
                "word_index": "$index", 
                "word_section": "$section"
            },
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$index", "$$word_index"]},
                            {"$eq": ["$section", "$$word_section"]},
                            {"$ne": ["$changing_consonant.character", consonant]}
                        ]
                    }
                }},
                {"$limit": 1}
            ],
            "as": "alternatives"
        }},
        # Only keep words that have alternatives
        {"$match": {"alternatives": {"$ne": []}}},
        # Add a sort by section and index to prioritize lower activity numbers
        {"$sort": {"section": 1, "index": 1}},
        {"$sample": {"size": 1}}
    ]
    
    main_cursor = await db["consonant_words"].aggregate(pipeline).to_list(1)
    if not main_cursor:
        return None, None

    main_word = main_cursor[0]
    main_word["_id"] = str(main_word["_id"])

    # Get the matching similar word - we know it exists because of the lookup
    match_sim = {
        "section": main_word.get("section"),
        "index": main_word.get("index"),
        "changing_consonant.character": {"$ne": consonant}
    }
    try:
        match_sim["_id"] = {"$ne": ObjectId(main_word["_id"])}
    except Exception:
        pass

    pipeline = [{"$match": match_sim}, {"$sample": {"size": 1}}]
    sim_cursor = await db["consonant_words"].aggregate(pipeline).to_list(1)
    similar_word = sim_cursor[0] if sim_cursor else None
    if similar_word:
        similar_word["_id"] = str(similar_word["_id"])
        # Double check indices match
        if similar_word.get("index") != main_word.get("index"):
            return None, None
    else:
        return None, None

    return main_word, similar_word


async def get_random_word_pair(db: AsyncIOMotorDatabase, exclude_consonants: List[str] = None):
    """Return a random main word excluding consonants in exclude_consonants and a similar-sounding alternative.
    Both words MUST have the same index AND section to ensure consistent word patterns."""
    
    pipeline = []
    match_stage = {}
    if exclude_consonants:
        match_stage["changing_consonant.character"] = {"$nin": exclude_consonants}
    
    # Find word pairs that have matching alternatives
    pipeline = [
        {"$match": match_stage} if match_stage else {"$match": {}},
        # First get the section/index combinations that have alternatives
        {"$lookup": {
            "from": "consonant_words",
            "let": {
                "word_index": "$index",
                "word_section": "$section",
                "word_consonant": "$changing_consonant.character"
            },
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$index", "$$word_index"]},
                            {"$eq": ["$section", "$$word_section"]},
                            {"$ne": ["$changing_consonant.character", "$$word_consonant"]}
                        ]
                    }
                }},
                {"$limit": 1}
            ],
            "as": "alternatives"
        }},
        # Only keep words that have alternatives
        {"$match": {"alternatives": {"$ne": []}}},
        # Add a sort by section and index to prioritize lower activity numbers
        {"$sort": {"section": 1, "index": 1}},
        {"$sample": {"size": 1}}
    ]

    main_cursor = await db["consonant_words"].aggregate(pipeline).to_list(1)
    if not main_cursor:
        return None, None

    main_word = main_cursor[0]
    main_word["_id"] = str(main_word["_id"])

    # Get the matching similar word - we know it exists because of the lookup
    match_sim = {
        "section": main_word.get("section"),  # MUST match section
        "index": main_word.get("index"),      # MUST match index
        "changing_consonant.character": {"$ne": main_word["changing_consonant"]["character"]}
    }
    try:
        match_sim["_id"] = {"$ne": ObjectId(main_word["_id"])}
    except Exception:
        pass

    pipeline = [{"$match": match_sim}, {"$sample": {"size": 1}}]
    sim_cursor = await db["consonant_words"].aggregate(pipeline).to_list(1)
    similar_word = sim_cursor[0] if sim_cursor else None
    if similar_word:
        similar_word["_id"] = str(similar_word["_id"])
        # Double check both index AND section match
        if (similar_word.get("index") != main_word.get("index") or 
            similar_word.get("section") != main_word.get("section")):
            return None, None
    else:
        return None, None

    return main_word, similar_word


def make_options_from_words(main_word: Dict, similar_word: Optional[Dict]) -> Dict:
    """Return serializable options dict for the frontend / Swagger."""
    correct = {
        "word": main_word["sinhala_word"],
        "audio_path": main_word.get("audio_path", ""),
        "changing_consonant": main_word["changing_consonant"]
    }

    if similar_word:
        similar = {
            "word": similar_word["sinhala_word"],
            "audio_path": similar_word.get("audio_path", ""),
            "changing_consonant": similar_word["changing_consonant"]
        }
    else:
        similar = {
            "word": "වෙනත්",
            "audio_path": "",
            "changing_consonant": {"character": "", "name": ""}
        }

    return {"correct_answer": correct, "similar_answer": similar, "other_option": True}


# Routes
@router.get("/all")
async def get_all_wiyanjana_words(db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db["consonant_words"].find()
    docs = await cursor.to_list(None)
    for d in docs:
        d["_id"] = str(d["_id"])
    return {"words": docs}


@router.post("/start", response_model=WiyanjanaSessionStart)
async def start_session(request: WiyanjanaSessionStartRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Start a new session with the provided user ID"""
    session = {
        "session_id": str(uuid.uuid4()),
        "user_id": request.user_id,
        "started_at": datetime.utcnow(),
        "consonants_to_verify": [],     # list of consonant characters queued for verification (strings)
        "verified_consonants": [],      # list of consonant characters already verified
        "current_consonant": None,
        "current_word_id": None,
        "current_options": None,        # stored serialized options dict while awaiting user's choice
        "current_is_verification": False,
        "awaiting_choice": False,
        "consonants_tested": [],        # history entries
        "verification_counts": {},      # map char -> int (1 or 2)
        "is_active": True
    }
    await db["wiyanjana_sessions"].insert_one(session)
    return WiyanjanaSessionStart(**session)


@router.get("/next/{session_id}")
async def get_next_word(session_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get next word. If session locked (awaiting_choice), return stored options (same payload)."""
    session = await db["wiyanjana_sessions"].find_one({"session_id": session_id, "is_active": True})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")

    # If locked: return the currently stored question unchanged
    if session.get("awaiting_choice"):
        stored = session.get("current_options")
        if not stored:
            raise HTTPException(status_code=500, detail="Session awaiting choice but no stored options")
        return {"options": stored, "is_verification": session.get("current_is_verification", False)}

    # Not locked: decide whether to serve verification (queue) or random new consonant
    consonants_to_verify = session.get("consonants_to_verify", []) or []
    verified_consonants = session.get("verified_consonants", []) or []

    # get last presented word id to avoid repeating same word
    last_choice = await db["wiyanjana_choices"].find_one({"session_id": session_id}, sort=[("timestamp", -1)])
    last_word_id = last_choice["word_id"] if last_choice else None

    main_word = None
    similar_word = None
    is_verification = False

    if consonants_to_verify:
        # Serve verification for the first queued consonant
        consonant = consonants_to_verify[0]
        main_word, similar_word = await get_verification_word_pair(db, consonant, previous_word_id=last_word_id)
        is_verification = True

        # If no verification example found (rare), fallback to random excluding queued+verified to avoid duplication
        if not main_word:
            excluded = list(set(verified_consonants + consonants_to_verify))
            main_word, similar_word = await get_random_word_pair(db, excluded)
            is_verification = False
    else:
        # No queued consonants: pick a random consonant excluding verified and queued
        excluded = list(set(verified_consonants + consonants_to_verify))
        main_word, similar_word = await get_random_word_pair(db, excluded)
        is_verification = False

    if not main_word:
        raise HTTPException(status_code=404, detail="No words available for testing")

    options = make_options_from_words(main_word, similar_word)

    current_consonant_char = main_word["changing_consonant"]["character"]

    # Prepare DB update to store current question and lock session
    # We'll use $set for the stored values; scheduling/initial count uses $addToSet and $set only when needed.
    set_fields = {
        "current_consonant": current_consonant_char,
        "current_word_id": main_word["_id"],
        "current_options": options,
        "current_is_verification": is_verification,
        "awaiting_choice": True
    }

    db_update: Dict[str, Any] = {"$set": set_fields}

    # If this is the initial random presentation (not a verification),
    # treat it as the first check: ensure the consonant is queued and count is set to 1 only if missing.
    if not is_verification:
        # queue the consonant (use addToSet to avoid duplicates)
        db_update.setdefault("$addToSet", {})["consonants_to_verify"] = current_consonant_char
        # set verification_counts.{char} = 1 but only if not already set; we cannot do conditional set easily here,
        # so we'll set unconditionally if missing on server side: use $setOnInsert isn't suitable for embedded fields,
        # so we fetch existing counts and only include $set if not present.
        existing_counts = session.get("verification_counts", {}) or {}
        if existing_counts.get(current_consonant_char) is None:
            # initialize to 1
            db_update.setdefault("$set", {})[f"verification_counts.{current_consonant_char}"] = 1

    # apply update to session
    await db["wiyanjana_sessions"].update_one({"session_id": session_id}, db_update)

    return {"options": options, "is_verification": is_verification}


@router.post("/choice")
async def submit_choice(choice: WiyanjanaUserChoice, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Submit user's choice. This will release the lock and, for verification attempts, increment counts and finalize."""
    session = await db["wiyanjana_sessions"].find_one({"session_id": choice.session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.get("awaiting_choice"):
        raise HTTPException(status_code=400, detail="No question awaiting a choice. Call GET /next first.")

    # Attach word_id for history (if present)
    current_word_id = session.get("current_word_id")
    choice_record = choice.dict()
    choice_record["word_id"] = current_word_id

    # Save choice
    await db["wiyanjana_choices"].insert_one(choice_record)

    # Prefer server-side session flags rather than trusting client-provided is_verification
    current_consonant = session.get("current_consonant")
    is_verification = session.get("current_is_verification", False)

    # Build update ops: save history and release the lock
    update_ops: Dict[str, Any] = {
        "$push": {
            "consonants_tested": {
                "consonant": choice.consonant_tested,
                "result": choice.chosen_option,
                "is_verification": is_verification,
                "timestamp": choice.timestamp
            }
        },
        "$set": {
            "awaiting_choice": False,
            "current_options": None,
            "current_word_id": None,
            "current_is_verification": False,
            "current_consonant": None
        }
    }

    # If this presentation was a verification (server-determined), increment the counter for that consonant
    if is_verification and current_consonant:
        # increment the verification count for this consonant
        update_ops.setdefault("$inc", {})[f"verification_counts.{current_consonant}"] = 1
        # also, if this increment will reach 2, mark as verified and remove from queue
        # we cannot atomically read the existing count here without extra read; check session copy
        existing_count = (session.get("verification_counts") or {}).get(current_consonant, 0)
        if (existing_count + 1) >= 2:
            update_ops.setdefault("$pull", {})["consonants_to_verify"] = current_consonant
            update_ops.setdefault("$addToSet", {})["verified_consonants"] = current_consonant

    # Apply session update
    await db["wiyanjana_sessions"].update_one({"session_id": choice.session_id}, update_ops)

    # Reload session and decide if the entire session should end
    session = await db["wiyanjana_sessions"].find_one({"session_id": choice.session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session disappeared after update")

    verification_counts = session.get("verification_counts", {}) or {}

    # Count consonants fully verified (verification_counts >= 2)
    fully_tested_consonants = sum(1 for v in verification_counts.values() if (v or 0) >= 2)
    if fully_tested_consonants >= 10:  # end session after 10 consonants fully verified
        await db["wiyanjana_sessions"].update_one(
            {"session_id": choice.session_id},
            {"$set": {"is_active": False, "ended_at": datetime.utcnow()}})
        return {"status": "completed"}

    return {"status": "continue"}





from collections import defaultdict
from fastapi import APIRouter, HTTPException, Depends
# ... other imports remain ...

@router.get("/session/{session_id}/result", response_model=WiyanjanaSessionResult)
async def get_session_result(session_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    # load session
    session = await db["wiyanjana_sessions"].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # fetch choices for this session
    choices = await db["wiyanjana_choices"].find({"session_id": session_id}).to_list(None)

    # Build aggregates grouped by consonant character
    agg: Dict[str, Dict[str, int]] = defaultdict(lambda: {"correct": 0, "incorrect": 0, "attempts": 0})

    for ch in choices:
        # chosen_option may be at ch.get("chosen_option") or ch.get("result") depending on how you inserted it
        chosen = ch.get("chosen_option") or ch.get("result")
        consonant_field = ch.get("consonant_tested") or ch.get("consonant")  # handle both saved shapes
        # extract consonant character if stored as dict or string
        if isinstance(consonant_field, dict):
            consonant_char = consonant_field.get("character") or consonant_field.get("consonant") or str(consonant_field)
        else:
            consonant_char = str(consonant_field or "unknown")

        # normalize
        consonant_char = consonant_char.strip()

        # count
        agg[consonant_char]["attempts"] += 1
        if chosen == "correct":
            agg[consonant_char]["correct"] += 1
        else:
            # treat "similar" and "other" as incorrect
            agg[consonant_char]["incorrect"] += 1

    # Convert to list of consonant result dicts (sorted if you like)
    consonant_results = []
    for consonant_char, counts in agg.items():
        consonant_results.append({
            "consonant": consonant_char,
            "correct": counts["correct"],
            "incorrect": counts["incorrect"],
            "attempts": counts["attempts"]
        })

    # Optionally sort by consonant or attempts (here by consonant)
    consonant_results.sort(key=lambda x: x["consonant"])

    started_at = session.get("started_at")
    ended_at = session.get("ended_at") or datetime.utcnow()

    return WiyanjanaSessionResult(
        session_id=session_id,
        user_id=session.get("user_id"),
        consonants_tested=consonant_results,
        started_at=started_at,
        ended_at=ended_at,
        total_words_tested=len(choices)
    )
