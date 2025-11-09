# app/routes/activityResults_Session.py
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.schemas_ActivityResults import (
    PaginatedResults, ResultItem, SessionSummaryItem,
    UserSummary, OverallSummary, PerUserAggregate
)
# use the same dependency name as your sample routes
from app.db import get_database

router = APIRouter(prefix="/doctor", tags=["doctor"])

# helper to map a Mongo document -> ResultItem
def _doc_to_resultitem(doc: dict) -> ResultItem:
    ts = doc.get("timestamp")
    return ResultItem(
        id=str(doc.get("_id")),
        session_id=doc.get("session_id"),
        user_id=doc.get("user_id"),
        word_presented=doc.get("word_presented"),
        chosen_option=doc.get("chosen_option"),
        is_verification=doc.get("is_verification"),
        consonant_tested=doc.get("consonant_tested"),
        timestamp=ts,
        section=doc.get("section"),
        index=doc.get("index")
    )

@router.get("/users/{user_id}/results", response_model=PaginatedResults)
async def get_user_results(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    session_id: Optional[str] = None,
    activity_section: Optional[str] = None,
    activity_index: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Paginated user results (collection: wiyanjana_choices).
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll = db["wiyanjana_choices"]
    q = {"user_id": user_id}
    if session_id:
        q["session_id"] = session_id
    if activity_section:
        q["section"] = activity_section
    if activity_index:
        q["index"] = activity_index

    total = await coll.count_documents(q)
    skip = (page - 1) * page_size
    cursor = coll.find(q).sort("timestamp", 1).skip(skip).limit(page_size)
    docs = await cursor.to_list(length=page_size)
    items = [_doc_to_resultitem(d) for d in docs]
    return PaginatedResults(total=total, page=page, page_size=page_size, items=items)


@router.get("/users/{user_id}/sessions", response_model=List[SessionSummaryItem])
async def get_user_sessions_summary(user_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Session-wise summary for a user (group by session_id).
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll = db["wiyanjana_choices"]
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": "$session_id",
            "first_ts": {"$min": "$timestamp"},
            "last_ts": {"$max": "$timestamp"},
            "attempts": {"$sum": 1},
            "correct": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "correct"]}, 1, 0]}},
            "similar": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "similar"]}, 1, 0]}},
            "other": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "other"]}, 1, 0]}}
        }},
        {"$sort": {"first_ts": -1}}
    ]

    rows = await coll.aggregate(pipeline).to_list(length=None)
    out = []
    for r in rows:
        attempts = int(r.get("attempts", 0))
        correct = int(r.get("correct", 0))
        similar = int(r.get("similar", 0))
        other = int(r.get("other", 0))
        acc = (correct / attempts) if attempts else None
        out.append(SessionSummaryItem(
            session_id=r["_id"],
            user_id=user_id,
            first_timestamp=r.get("first_ts"),
            last_timestamp=r.get("last_ts"),
            attempts=attempts,
            correct=correct,
            similar=similar,
            other=other,
            accuracy=acc
        ))
    return out


@router.get("/users/{user_id}/summary", response_model=UserSummary)
async def get_user_summary(user_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Full summary for a user across all sessions.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll = db["wiyanjana_choices"]
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": None,
            "attempts": {"$sum": 1},
            "correct": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "correct"]}, 1, 0]}},
            "similar": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "similar"]}, 1, 0]}},
            "other": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "other"]}, 1, 0]}},
            "sessions": {"$addToSet": "$session_id"}
        }},
        {"$project": {
            "attempts": 1,
            "correct": 1,
            "similar": 1,
            "other": 1,
            "sessions_count": {"$size": "$sessions"}
        }}
    ]
    rows = await coll.aggregate(pipeline).to_list(length=1)
    if not rows:
        return UserSummary(user_id=user_id, total_sessions=0, total_attempts=0, total_correct=0, total_similar=0, total_other=0, accuracy=None)

    r = rows[0]
    attempts = int(r.get("attempts", 0))
    correct = int(r.get("correct", 0))
    similar = int(r.get("similar", 0))
    other = int(r.get("other", 0))
    sessions = int(r.get("sessions_count", 0))
    acc = (correct / attempts) if attempts else None

    return UserSummary(
        user_id=user_id,
        total_sessions=sessions,
        total_attempts=attempts,
        total_correct=correct,
        total_similar=similar,
        total_other=other,
        accuracy=acc
    )


@router.get("/activity/{activity_key}/results", response_model=PaginatedResults)
async def get_activity_results(
    activity_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=2000),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Activity (section or section:idx) results.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll = db["wiyanjana_choices"]
    section = None
    idx = None
    if ":" in activity_key:
        section, idx = activity_key.split(":", 1)
    else:
        section = activity_key

    q = {}
    if section:
        q["section"] = section
    if idx:
        q["index"] = idx

    total = await coll.count_documents(q)
    skip = (page - 1) * page_size
    docs = await coll.find(q).sort("timestamp", 1).skip(skip).limit(page_size).to_list(length=page_size)
    items = [_doc_to_resultitem(d) for d in docs]
    return PaginatedResults(total=total, page=page, page_size=page_size, items=items)


@router.get("/summary", response_model=OverallSummary)
async def get_overall_summary(db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Overall summary across all users: totals + per-user aggregates.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll = db["wiyanjana_choices"]

    # totals
    totals_pipeline = [
        {"$group": {
            "_id": None,
            "attempts": {"$sum": 1},
            "correct": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "correct"]}, 1, 0]}},
            "similar": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "similar"]}, 1, 0]}},
            "other": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "other"]}, 1, 0]}},
            "users": {"$addToSet": "$user_id"}
        }},
        {"$project": {
            "attempts": 1,
            "correct": 1,
            "similar": 1,
            "other": 1,
            "total_users": {"$size": "$users"}
        }}
    ]
    totals_res = await coll.aggregate(totals_pipeline).to_list(length=1)
    if totals_res:
        t = totals_res[0]
        attempts = int(t.get("attempts", 0))
        correct = int(t.get("correct", 0))
        similar = int(t.get("similar", 0))
        other = int(t.get("other", 0))
        total_users = int(t.get("total_users", 0))
    else:
        attempts = correct = similar = other = total_users = 0

    acc = (correct / attempts) if attempts else None

    # per-user aggregates
    per_user_pipeline = [
        {"$group": {
            "_id": "$user_id",
            "attempts": {"$sum": 1},
            "correct": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "correct"]}, 1, 0]}},
            "similar": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "similar"]}, 1, 0]}},
            "other": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "other"]}, 1, 0]}}
        }},
        {"$sort": {"attempts": -1}}
    ]
    per_user_rows = await coll.aggregate(per_user_pipeline).to_list(length=None)
    per_user = []
    for r in per_user_rows:
        a = int(r.get("attempts", 0))
        c = int(r.get("correct", 0))
        s = int(r.get("similar", 0))
        o = int(r.get("other", 0))
        per_user.append(PerUserAggregate(
            user_id=r["_id"],
            attempts=a,
            correct=c,
            similar=s,
            other=o,
            accuracy=(c / a) if a else None
        ))

    return OverallSummary(
        total_users=total_users,
        total_attempts=attempts,
        total_correct=correct,
        total_similar=similar,
        total_other=other,
        accuracy=acc,
        per_user=per_user
    )


@router.get("/session/{session_id}/result", response_model=SessionSummaryItem)
async def get_session_result(session_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Single-session summary (per-session aggregate). Returns the same shape as SessionSummaryItem.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll = db["wiyanjana_choices"]
    pipeline = [
        {"$match": {"session_id": session_id}},
        {"$group": {
            "_id": "$session_id",
            "first_ts": {"$min": "$timestamp"},
            "last_ts": {"$max": "$timestamp"},
            "attempts": {"$sum": 1},
            "correct": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "correct"]}, 1, 0]}},
            "similar": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "similar"]}, 1, 0]}},
            "other": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "other"]}, 1, 0]}}
        }}
    ]
    rows = await coll.aggregate(pipeline).to_list(length=1)
    if not rows:
        raise HTTPException(status_code=404, detail="Session not found or no choices recorded")

    r = rows[0]
    attempts = int(r.get("attempts", 0))
    correct = int(r.get("correct", 0))
    similar = int(r.get("similar", 0))
    other = int(r.get("other", 0))
    acc = (correct / attempts) if attempts else None

    return SessionSummaryItem(
        session_id=r["_id"],
        user_id=None,
        first_timestamp=r.get("first_ts"),
        last_timestamp=r.get("last_ts"),
        attempts=attempts,
        correct=correct,
        similar=similar,
        other=other,
        accuracy=acc
    )
