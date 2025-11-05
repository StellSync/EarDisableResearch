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
    WiyanjanaOptions,
    WiyanjanaUserChoice,
    WiyanjanaSessionResult,
    WiyanjanaAnswer
)

router = APIRouter(prefix="/wiyanjana", tags=["wiyanjana"])

# Helper functions
async def get_verification_word_pair(db: AsyncIOMotorDatabase, consonant: str, previous_word_id: str = None):
    """Get a word with the testing consonant and a similar-sounding word with a different consonant"""
    # Build match for main word; only include _id exclusion if previous_word_id provided
    match_stage = {
        "changing_consonant.character": consonant
    }
    if previous_word_id:
        try:
            match_stage["_id"] = {"$ne": ObjectId(previous_word_id)}
        except Exception:
            # if previous_word_id isn't a valid ObjectId, ignore _id filter
            pass

    pipeline = [
        {"$match": match_stage},
        {"$sample": {"size": 1}}  # Get random word with this consonant
    ]
    
    main_word_cursor = await db["consonant_words"].aggregate(pipeline).to_list(1)
    if not main_word_cursor:
        return None, None
        
    main_word = main_word_cursor[0]
    main_word["_id"] = str(main_word["_id"])
    
    # Find a similar-sounding word but with a different consonant
    # For example, if testing 'ත' in 'කත', find 'කද'
    match_stage_similar = {
        "section": main_word["section"],  # Same section for similar words
        "index": main_word["index"],      # Same index for similar words
        "changing_consonant.character": {"$ne": consonant}
    }
    # ensure we don't match the exact same document
    try:
        match_stage_similar["_id"] = {"$ne": ObjectId(main_word["_id"])}
    except Exception:
        pass

    pipeline = [
        {"$match": match_stage_similar},
        {"$sample": {"size": 1}}  # Get random similar word
    ]
    
    similar_word_cursor = await db["consonant_words"].aggregate(pipeline).to_list(1)
    similar_word = similar_word_cursor[0] if similar_word_cursor else None
    
    if similar_word:
        similar_word["_id"] = str(similar_word["_id"])
    
    return main_word, similar_word

async def get_random_word_pair(db: AsyncIOMotorDatabase, exclude_consonants: List[str] = None):
    """Get a random word and a similar-sounding word with a different consonant"""
    # First get a random word, excluding already verified consonants
    pipeline = []
    if exclude_consonants:
        pipeline.append({
            "$match": {
                "changing_consonant.character": {"$nin": exclude_consonants}
            }
        })
    pipeline.append({"$sample": {"size": 1}})
    
    main_word_cursor = await db["consonant_words"].aggregate(pipeline).to_list(1)
    
    if not main_word_cursor:
        return None, None
    
    main_word = main_word_cursor[0]
    main_word["_id"] = str(main_word["_id"])

    # Find a similar-sounding word with a different consonant
    # For example, if we got 'කත', find 'කද'
    match_stage = {
        "section": main_word["section"],  # Same section for similar words
        "index": main_word["index"],      # Same index for similar pattern
        "changing_consonant.character": {"$ne": main_word["changing_consonant"]["character"]}
    }
    try:
        match_stage["_id"] = {"$ne": ObjectId(main_word["_id"])}
    except Exception:
        pass

    pipeline = [
        {"$match": match_stage},
        {"$sample": {"size": 1}}
    ]
    
    similar_word_cursor = await db["consonant_words"].aggregate(pipeline).to_list(1)
    similar_word = similar_word_cursor[0] if similar_word_cursor else None
    
    if similar_word:
        similar_word["_id"] = str(similar_word["_id"])
    
    return main_word, similar_word

async def create_word_options(main_word: Dict, similar_word: Optional[Dict], db: AsyncIOMotorDatabase) -> WiyanjanaOptions:
    """Create the three options for a word test: correct, similar, and 'other'"""
    correct_answer = WiyanjanaAnswer(
        word=main_word["sinhala_word"],
        audio_path=main_word.get("audio_path", ""),
        changing_consonant=main_word["changing_consonant"]
    )

    # If no similar word is found, try to find another word with a different consonant
    if not similar_word:
        similar_word_cursor = await db["consonant_words"].find({
            "section": main_word["section"],
            "changing_consonant.character": {"$ne": main_word["changing_consonant"]["character"]},
            "_id": {"$ne": ObjectId(main_word["_id"])} if main_word.get("_id") else {}
        }).to_list(1)
        
        if similar_word_cursor:
            similar_word = similar_word_cursor[0]
            similar_word["_id"] = str(similar_word["_id"])

    # Create similar answer
    if similar_word:
        similar_answer = WiyanjanaAnswer(
            word=similar_word["sinhala_word"],
            audio_path=similar_word.get("audio_path", ""),
            changing_consonant=similar_word["changing_consonant"]
        )
    else:
        similar_answer = WiyanjanaAnswer(
            word="වෙනත්",  # Default to "Other" if no similar word found
            audio_path="",
            changing_consonant={"character": "", "name": ""}
        )

    return WiyanjanaOptions(
        correct_answer=correct_answer,
        similar_answer=similar_answer,
        other_option=True  # This indicates that "වෙනත්" is always an available option
    )

# Routes
@router.get("/all")
async def get_all_consonant_words(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get all consonant words from database"""
    cursor = db["consonant_words"].find()
    words = await cursor.to_list(None)
    # Convert MongoDB documents to serializable format
    serializable_words = []
    for word in words:
        word['_id'] = str(word['_id'])  # Convert ObjectId to string
        serializable_words.append(word)
    return {"words": serializable_words}

@router.post("/start", response_model=WiyanjanaSessionStart)
async def start_session(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Start a new Wiyanjana testing session"""
    session = {
        "session_id": str(uuid.uuid4()),
        "user_id": f"test_user_{random.randint(1000, 9999)}",  # Fake user ID for now
        "started_at": datetime.utcnow(),
        "consonants_to_verify": [],  # Consonants that need verification (queue)
        "verified_consonants": [],    # Consonants that have been verified (done)
        "current_consonant": None,    # Currently being tested consonant
        "consonants_tested": [],
        "verification_counts": {},    # Track number of verifications per consonant
        "is_active": True
    }
    
    await db["wiyanjana_sessions"].insert_one(session)
    return WiyanjanaSessionStart(**session)

@router.get("/next/{session_id}")
async def get_next_word(session_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get next word for testing, with options"""
    # Check if session exists and is active
    session = await db["wiyanjana_sessions"].find_one({"session_id": session_id, "is_active": True})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    
    # Convert session ObjectId to string if present
    if session.get("_id"):
        session['_id'] = str(session['_id'])
    
    # Get last tested word for this session
    last_choice = await db["wiyanjana_choices"].find_one(
        {"session_id": session_id},
        sort=[("timestamp", -1)]
    )
    
    # Check if there are consonants that need verification (we use queue semantics)
    if session.get("consonants_to_verify"):
        consonant = session["consonants_to_verify"][0]
        # Get the ID of the last word to avoid immediate repetition
        last_word_id = last_choice["word_id"] if last_choice else None
        
        # Get a verification word pair with the same consonant
        main_word, similar_word = await get_verification_word_pair(
            db, 
            consonant,
            previous_word_id=last_word_id
        )
        is_verification = True

        # If we couldn't find a verification pair for that consonant, fallback to random
        if not main_word:
            excluded_consonants = session.get("verified_consonants", [])
            main_word, similar_word = await get_random_word_pair(db, excluded_consonants)
            is_verification = False
    else:
        # No pending verifications: get a random word pair, excluding verified consonants
        excluded_consonants = session.get("verified_consonants", [])
        main_word, similar_word = await get_random_word_pair(db, excluded_consonants)
        is_verification = False
        
    if not main_word:
        raise HTTPException(status_code=404, detail="No words available for testing")
    
    # Update session with current word and consonant being tested
    await db["wiyanjana_sessions"].update_one(
        {"session_id": session_id},
        {
            "$set": {
                "current_consonant": main_word["changing_consonant"]["character"],
                "current_word_id": main_word["_id"]
            }
        }
    )
    
    # Create options
    options = await create_word_options(main_word, similar_word, db)
    
    return {
        "options": options,
        "is_verification": is_verification
    }

@router.post("/choice")
async def submit_choice(choice: WiyanjanaUserChoice, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Submit user's choice and update session based on result"""

    # Get current session
    session = await db["wiyanjana_sessions"].find_one({"session_id": choice.session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Add current word ID to the choice record
    choice_dict = choice.dict()
    choice_dict["word_id"] = session.get("current_word_id")
    
    # Record the choice
    await db["wiyanjana_choices"].insert_one(choice_dict)
    
    current_consonant = session.get("current_consonant")
    consonants_to_verify = session.get("consonants_to_verify", [])
    verified_consonants = session.get("verified_consonants", [])
    
    update_data = {
        "$push": {
            "consonants_tested": {
                "consonant": choice.consonant_tested,
                "result": choice.chosen_option,
                "is_verification": choice.is_verification,
                "timestamp": choice.timestamp
            }
        }
    }
    
    # If this was a verification attempt, increment the verification count and possibly finalize that consonant
    if choice.is_verification and current_consonant:
        # current_count is what currently exists in session (may be 0)
        current_count = session.get("verification_counts", {}).get(current_consonant, 0)
        # We'll increment the count by 1
        update_data.setdefault("$inc", {})[f"verification_counts.{current_consonant}"] = 1
        
        # After increment, if this reaches 2 or more, remove from to_verify and mark verified.
        # Note: because we used the session snapshot for current_count, compare current_count + 1
        if (current_count + 1) >= 2:
            # remove from to_verify and add to verified
            update_data.setdefault("$pull", {})["consonants_to_verify"] = current_consonant
            update_data.setdefault("$addToSet", {})["verified_consonants"] = current_consonant
    else:
        # Non-verification attempt (a normal random question)
        # If the consonant hasn't been scheduled for verification or verified yet, schedule it
        if current_consonant and current_consonant not in consonants_to_verify and current_consonant not in verified_consonants:
            # push to the end of the verification queue
            update_data.setdefault("$push", {})["consonants_to_verify"] = current_consonant
            # initialize verification count for that consonant to 0 (only if not present)
            if f"verification_counts.{current_consonant}" not in (session.get("verification_counts", {}) or {}):
                update_data.setdefault("$set", {})[f"verification_counts.{current_consonant}"] = 0

    # Apply the session updates
    await db["wiyanjana_sessions"].update_one(
        {"session_id": choice.session_id},
        update_data
    )
    
    # Re-read session to check progress (fresh)
    session = await db["wiyanjana_sessions"].find_one({"session_id": choice.session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session disappeared after update")
    
    # End session condition: total consonant verification attempts (2 per consonant) or total tested words
    # You previously used len(session["consonants_tested"]) >= 20 as a limit (10 consonants * 2 attempts).
    # Keep that behavior: 20 word checks finish session.
    if len(session.get("consonants_tested", [])) >= 20:
        await db["wiyanjana_sessions"].update_one(
            {"session_id": choice.session_id},
            {
                "$set": {
                    "is_active": False,
                    "ended_at": datetime.utcnow()
                }
            }
        )
        return {"status": "completed"}
    
    return {"status": "continue"}

@router.get("/session/{session_id}/result", response_model=WiyanjanaSessionResult)
async def get_session_result(session_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get the results of a completed session"""
    session = await db["wiyanjana_sessions"].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Convert session ObjectId to string
    session['_id'] = str(session['_id'])
        
    choices = await db["wiyanjana_choices"].find(
        {"session_id": session_id}
    ).to_list(None)
    
    # Convert choices ObjectIds to strings
    for choice in choices:
        choice['_id'] = str(choice['_id'])
    
    return WiyanjanaSessionResult(
        session_id=session_id,
        user_id=session["user_id"],
        consonants_tested=session.get("consonants_tested", []),
        started_at=session["started_at"],
        ended_at=session.get("ended_at", datetime.utcnow()),
        total_words_tested=len(choices)
    )
