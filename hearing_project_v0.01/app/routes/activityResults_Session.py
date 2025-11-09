# app/routes/activityResults_Session.py
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, date
from motor.motor_asyncio import AsyncIOMotorDatabase
import asyncio
import types
import re
import base64
import logging

from bson import ObjectId, Decimal128, DBRef, Binary

from app.schemas_ActivityResults import (
    PaginatedResults, ResultItem, SessionSummaryItem,
    UserSummary, OverallSummary, PerUserAggregate
)
from app.db import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/doctor", tags=["doctor"])

# mapping logical activity -> choices collection and session collection
ACTIVITY_MAP = {
    "wiyanjana": {"choices": "wiyanjana_choices", "sessions": "wiyanjana_sessions"},
    "sentence":  {"choices": "sentence_choices",  "sessions": "sentence_sessions"},
    "swara":     {"choices": "swara_choices",     "sessions": "sessions"},
}
ALL_ACTIVITIES = list(ACTIVITY_MAP.keys())


def _collections_for_activity(activity: Optional[str]) -> List[Dict[str, str]]:
    """
    Returns a list of {activity, choices, sessions} entries to query.
    activity None or 'all' -> all activities
    otherwise -> single.
    """
    if not activity or activity.lower() == "all":
        return [{"activity": k, "choices": ACTIVITY_MAP[k]["choices"], "sessions": ACTIVITY_MAP[k]["sessions"]} for k in ALL_ACTIVITIES]
    key = activity.lower()
    if key in ACTIVITY_MAP:
        return [{"activity": key, "choices": ACTIVITY_MAP[key]["choices"], "sessions": ACTIVITY_MAP[key]["sessions"]}]
    # fallback to all
    return [{"activity": k, "choices": ACTIVITY_MAP[k]["choices"], "sessions": ACTIVITY_MAP[k]["sessions"]} for k in ALL_ACTIVITIES]


# ---------------- utility: sanitize BSON -> JSON serializable ----------------

def _sanitize_bson(obj: Any) -> Any:
    """
    Convert BSON types into JSON-serializable Python types recursively.
    Handles ObjectId, Decimal128, DBRef, Binary, regex, datetimes, lists, dicts.
    """
    # primitives considered safe
    safe_primitive_types = (str, int, float, bool, type(None), datetime, date)

    if isinstance(obj, safe_primitive_types):
        return obj

    # ObjectId -> str
    if isinstance(obj, ObjectId):
        return str(obj)

    # Decimal128 -> float if possible else string
    if isinstance(obj, Decimal128):
        try:
            return float(obj.to_decimal())
        except Exception:
            return str(obj)

    # DBRef -> dictionary
    if isinstance(obj, DBRef):
        return {"$dbref": {"collection": obj.collection, "id": str(obj.id)}}

    # Binary -> base64 string
    if isinstance(obj, Binary):
        try:
            return base64.b64encode(bytes(obj)).decode("ascii")
        except Exception:
            return str(obj)

    # regex -> pattern string
    if isinstance(obj, re.Pattern):
        return obj.pattern

    if isinstance(obj, dict):
        return {str(k): _sanitize_bson(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_sanitize_bson(v) for v in obj]

    # fallback: try to convert to str
    try:
        return str(obj)
    except Exception:
        return repr(obj)


# ---------------- resolve user_id from session_id helper ----------------

async def resolve_user_id_from_session(db: AsyncIOMotorDatabase, session_id: str) -> Optional[str]:
    """
    Find and return the user_id for a given session_id.
    Searches across all configured session collections (ACTIVITY_MAP).
    Returns the first user_id found, or None if session not found.
    """
    if not session_id:
        return None

    for activity, spec in ACTIVITY_MAP.items():
        sessions_coll = spec.get("sessions")
        if not sessions_coll:
            continue
        try:
            sess = await db[sessions_coll].find_one({"session_id": session_id}, {"user_id": 1, "session_user_id": 1, "user": 1})
            if sess:
                # prefer user_id, fall back to common alternatives
                user_id = sess.get("user_id") or sess.get("session_user_id") or sess.get("user")
                if user_id:
                    logger.debug("resolve_user_id_from_session: found user_id %s in %s", user_id, sessions_coll)
                    return str(user_id)
        except Exception as e:
            logger.exception("Error querying sessions collection %s: %s", sessions_coll, e)
            # continue searching other collections
    return None


# ---------------- normalization and enrichment helpers ----------------

def _normalize_choice_doc(raw: Dict[str, Any], activity_key: str, coll_name: str) -> Dict[str, Any]:
    """
    Normalize different field names into a shared shape but keep original doc in `_raw` (sanitized).
    Pure mapping (no DB calls).
    """
    doc = dict(raw)  # shallow copy
    # normalize chosen option
    chosen = doc.get("chosen_option")
    if chosen is None:
        chosen = doc.get("user_choice") or doc.get("result") or doc.get("selected")
    if chosen is None and "is_correct" in doc:
        chosen = "correct" if doc.get("is_correct") else "other"
    doc["_normalized_chosen"] = chosen

    # word presenters / ids
    doc["_normalized_word_presented"] = doc.get("word_presented") or doc.get("sinhala_word") or doc.get("word") or None
    doc["_normalized_word_id"] = doc.get("word_id") or doc.get("correct_id") or doc.get("correctId") or None
    doc["_normalized_question_id"] = doc.get("question_id") or doc.get("question") or None
    # vowel (sentence choices)
    doc["_normalized_vowel"] = doc.get("vowel") or doc.get("correct_vowel") or (doc.get("current") or {}).get("vowel") or (doc.get("vowel_progress") or {}).get("current_vowel") or None
    # consonant tested
    doc["_normalized_consonant_tested"] = doc.get("consonant_tested") or doc.get("changing_consonant") or doc.get("consonant") or None

    # session & user
    doc["_normalized_session_id"] = doc.get("session_id")
    doc["_normalized_user_id"] = doc.get("user_id") or doc.get("session_user_id") or None

    # timestamps may be stored under different keys; prefer 'timestamp'
    ts = doc.get("timestamp") or doc.get("time") or doc.get("created_at") or None
    doc["_normalized_timestamp"] = ts

    # section/index if present
    doc["_normalized_section"] = doc.get("section")
    doc["_normalized_index"] = doc.get("index")

    # attach metadata for activity + source collection
    doc["_activity"] = activity_key
    doc["_source_collection"] = coll_name

    # sanitize raw for safe JSON output (convert ObjectId -> str recursively)
    try:
        doc["_raw"] = _sanitize_bson(raw)
    except Exception:
        # last-resort: str of doc
        doc["_raw"] = {"_unsanitized": str(raw)}

    # ensure _id in _raw is string
    if "_id" in raw:
        try:
            doc["_raw"]["_id"] = str(raw["_id"])
        except Exception:
            doc["_raw"]["_id"] = raw["_id"]

    return doc


async def _enrich_from_session(db: AsyncIOMotorDatabase, doc: Dict[str, Any], sessions_coll_name: Optional[str]) -> Dict[str, Any]:
    """
    If a normalized doc lacks section/index/vowel and the session doc has those fields,
    copy them into the normalized doc. Returns the doc (possibly modified).
    """
    sid = doc.get("_normalized_session_id")
    if not sid or not sessions_coll_name:
        return doc
    need_section = not doc.get("_normalized_section")
    need_index = not doc.get("_normalized_index")
    need_vowel = not doc.get("_normalized_vowel")
    if not (need_section or need_index or need_vowel):
        return doc
    sess = await db[sessions_coll_name].find_one({"session_id": sid})
    if not sess:
        return doc
    # copy values from session document if present
    if need_section and sess.get("section"):
        doc["_normalized_section"] = sess.get("section")
    if need_index and sess.get("index"):
        doc["_normalized_index"] = sess.get("index")
    # sentence sessions may have current_vowel or vowel_progress.current_vowel
    if need_vowel:
        v = sess.get("current_vowel") or (sess.get("vowel_progress") or {}).get("current_vowel") or sess.get("vowel") or (sess.get("current") or {}).get("vowel")
        if v:
            doc["_normalized_vowel"] = v
    return doc


def _to_result_item_from_normalized(doc: Dict[str, Any]) -> ResultItem:
    """Convert normalized doc (after optional enrichment) to ResultItem pydantic-friendly object."""
    # ensure id is string
    source_id = ""
    if doc.get("_raw") and doc["_raw"].get("_id") is not None:
        source_id = str(doc["_raw"].get("_id"))
    else:
        mid = doc.get("_id") or doc.get("id")
        if isinstance(mid, ObjectId):
            source_id = str(mid)
        else:
            source_id = str(mid) if mid is not None else ""

    timestamp = doc.get("_normalized_timestamp")
    # if timestamp is string, try parse - but FastAPI/pydantic can handle ISO strings as well.
    # we just pass through; pydantic will attempt parsing.
    return ResultItem(
        id=source_id,
        activity=doc.get("_activity"),
        source_collection=doc.get("_source_collection"),
        session_id=doc.get("_normalized_session_id"),
        session_user_id=doc.get("_normalized_user_id"),
        user_id=doc.get("_normalized_user_id"),
        question_id=doc.get("_normalized_question_id"),
        word_id=doc.get("_normalized_word_id"),
        word_presented=doc.get("_normalized_word_presented"),
        vowel=doc.get("_normalized_vowel"),
        chosen_option=doc.get("_normalized_chosen"),
        is_verification=doc.get("is_verification") if "is_verification" in doc else (doc.get("_raw") or {}).get("is_verification"),
        consonant_tested=doc.get("_normalized_consonant_tested"),
        timestamp=timestamp,
        section=doc.get("_normalized_section"),
        index=doc.get("_normalized_index"),
        raw=doc.get("_raw")
    )


# helper: fetch & normalize docs from multiple collections
async def _fetch_and_normalize(db: AsyncIOMotorDatabase, collections: List[Dict[str, str]], query: Dict[str, Any]):
    """
    Query each choices collection with `query`, normalize documents, and return flattened list.
    NOTE: returns all matching docs; caller should sort & paginate in-memory.
    """
    async def _fetch_one(coll_spec):
        coll = db[coll_spec["choices"]]
        cursor = coll.find(query)
        docs = await cursor.to_list(length=None)
        normalized = [_normalize_choice_doc(d, coll_spec["activity"], coll_spec["choices"]) for d in docs]
        return normalized

    tasks = [_fetch_one(cspec) for cspec in collections]
    results = await asyncio.gather(*tasks)
    flat = [d for sub in results for d in sub]
    # sort by timestamp ascending (None last)
    flat.sort(key=lambda x: (x.get("_normalized_timestamp") is None, x.get("_normalized_timestamp")))
    return flat


async def _count_across(db: AsyncIOMotorDatabase, collections: List[Dict[str, str]], query: Dict[str, Any]) -> int:
    async def _count_one(coll_spec):
        return await db[coll_spec["choices"]].count_documents(query)
    counts = await asyncio.gather(*[_count_one(c) for c in collections])
    return sum(counts)


# ---------------- endpoints ----------------

@router.get("/users/{user_id}/results", response_model=PaginatedResults)
async def get_user_results(
    user_id: str,
    activity: Optional[str] = Query("all", description="swara|wiyanjana|sentence|all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=2000),
    session_id: Optional[str] = None,
    activity_section: Optional[str] = None,
    activity_index: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Paginated, normalized results for a user across activities.
    Default activity='all' returns combined results.
    Returned items include 'activity' and 'source_collection' and are enriched from sessions when needed.

    NOTE: if the caller passes only session_id and not a valid user_id (e.g. user_id == "unknown" or "0"),
    we attempt to resolve the user_id from the session document.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    # resolve user_id from session if needed
    if (not user_id or user_id.strip() == "") and session_id:
        resolved = await resolve_user_id_from_session(db, session_id)
        if resolved:
            user_id = resolved

    coll_specs = _collections_for_activity(activity)
    q = {"user_id": user_id}
    if session_id:
        q["session_id"] = session_id
    if activity_section:
        q["section"] = activity_section
    if activity_index:
        q["index"] = activity_index

    total = await _count_across(db, coll_specs, q)
    normalized_docs = await _fetch_and_normalize(db, coll_specs, q)

    # paginate in memory
    start = (page - 1) * page_size
    page_docs = normalized_docs[start:start + page_size]

    # enrich page docs from their session collections when needed (bounded to page size)
    enriched = []
    for nd in page_docs:
        activity_key = nd.get("_activity")
        sessions_coll = ACTIVITY_MAP.get(activity_key, {}).get("sessions")
        nd = await _enrich_from_session(db, nd, sessions_coll)
        enriched.append(nd)

    # convert to ResultItem with safe error handling
    items = []
    for d in enriched:
        try:
            items.append(_to_result_item_from_normalized(d))
        except Exception as e:
            logger.exception("Failed converting normalized doc to ResultItem; doc id=%s activity=%s", d.get('_raw',{}).get('_id'), d.get('_activity'))
            raise HTTPException(status_code=500, detail={
                "message": "Serialization to ResultItem failed — see server logs",
                "doc_id": str(d.get('_raw',{}).get('_id')),
                "activity": d.get("_activity"),
                "raw_preview": str(d.get("_raw"))[:2000],
                "error": repr(e)
            })

    return PaginatedResults(total=total, page=page, page_size=page_size, items=items)


@router.get("/users/{user_id}/sessions", response_model=List[SessionSummaryItem])
async def get_user_sessions_summary(
    user_id: str,
    activity: Optional[str] = Query("all"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Return session-wise aggregates for a user across chosen activities (grouped by session_id).
    Aggregates are merged across collections if activity='all'.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll_specs = _collections_for_activity(activity)

    async def _agg_one(coll_spec):
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
            }}
        ]
        rows = await db[coll_spec["choices"]].aggregate(pipeline).to_list(length=None)
        return rows

    groups = await asyncio.gather(*[_agg_one(c) for c in coll_specs])
    combined = {}
    for rows in groups:
        for r in rows:
            sid = r["_id"]
            cur = combined.setdefault(sid, {"first_ts": None, "last_ts": None, "attempts": 0, "correct": 0, "similar": 0, "other": 0})
            ft = r.get("first_ts"); lt = r.get("last_ts")
            if ft and (cur["first_ts"] is None or ft < cur["first_ts"]): cur["first_ts"] = ft
            if lt and (cur["last_ts"] is None or lt > cur["last_ts"]): cur["last_ts"] = lt
            cur["attempts"] += int(r.get("attempts", 0))
            cur["correct"] += int(r.get("correct", 0))
            cur["similar"] += int(r.get("similar", 0))
            cur["other"] += int(r.get("other", 0))

    out = []
    for sid, v in combined.items():
        attempts = v["attempts"]
        correct = v["correct"]
        similar = v["similar"]
        other = v["other"]
        acc = (correct / attempts) if attempts else None
        out.append(SessionSummaryItem(
            session_id=sid,
            user_id=user_id,
            first_timestamp=v["first_ts"],
            last_timestamp=v["last_ts"],
            attempts=attempts,
            correct=correct,
            similar=similar,
            other=other,
            accuracy=acc
        ))
    out.sort(key=lambda x: (x.first_timestamp is None, x.first_timestamp), reverse=True)
    return out


@router.get("/users/{user_id}/summary", response_model=UserSummary)
async def get_user_summary(
    user_id: str,
    activity: Optional[str] = Query("all"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Full per-user summary across activities (or single activity).
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll_specs = _collections_for_activity(activity)

    async def _agg_one(coll_spec):
        rows = await db[coll_spec["choices"]].aggregate([
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": None,
                "attempts": {"$sum": 1},
                "correct": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "correct"]}, 1, 0]}},
                "similar": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "similar"]}, 1, 0]}},
                "other": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "other"]}, 1, 0]}},
                "sessions": {"$addToSet": "$session_id"}
            }},
            {"$project": {"attempts": 1, "correct": 1, "similar": 1, "other": 1, "sessions_count": {"$size": "$sessions"}}}
        ]).to_list(length=1)
        return rows[0] if rows else None

    rows = await asyncio.gather(*[_agg_one(c) for c in coll_specs])
    attempts = correct = similar = other = sessions = 0
    for r in rows:
        if not r:
            continue
        attempts += int(r.get("attempts", 0))
        correct += int(r.get("correct", 0))
        similar += int(r.get("similar", 0))
        other += int(r.get("other", 0))
        sessions += int(r.get("sessions_count", 0))
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
    Activity-level (section or section:idx) results from a single activity.
    activity_key can be 'swara' or 'wiyanjana' or 'sentence' or 'swara:07' style.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    section = None
    idx = None
    if ":" in activity_key:
        section, idx = activity_key.split(":", 1)
    else:
        section = activity_key

    # determine which activity collections to query
    coll_specs = _collections_for_activity(section)
    q = {}
    if idx:
        q["index"] = idx
    # fetch & normalize across matching collections (should typically be one)
    normalized_docs = await _fetch_and_normalize(db, coll_specs, q)
    total = len(normalized_docs)
    start = (page - 1) * page_size
    page_docs = normalized_docs[start:start + page_size]

    # enrich page docs
    enriched = []
    for nd in page_docs:
        activity_key = nd.get("_activity")
        sessions_coll = ACTIVITY_MAP.get(activity_key, {}).get("sessions")
        nd = await _enrich_from_session(db, nd, sessions_coll)
        enriched.append(nd)

    items = []
    for d in enriched:
        try:
            items.append(_to_result_item_from_normalized(d))
        except Exception as e:
            logger.exception("Failed converting normalized doc to ResultItem; doc id=%s activity=%s", d.get('_raw',{}).get('_id'), d.get('_activity'))
            raise HTTPException(status_code=500, detail={
                "message": "Serialization to ResultItem failed — see server logs",
                "doc_id": str(d.get('_raw',{}).get('_id')),
                "activity": d.get("_activity"),
                "raw_preview": str(d.get("_raw"))[:2000],
                "error": repr(e)
            })
    return PaginatedResults(total=total, page=page, page_size=page_size, items=items)


@router.get("/summary", response_model=OverallSummary)
async def get_overall_summary(db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Overall summary across all users: totals + per-user aggregates.
    Aggregates across all activities.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    # aggregate totals across each choices collection and sum them
    total_attempts = 0
    total_correct = 0
    total_similar = 0
    total_other = 0
    total_users_set = set()
    per_user_map: Dict[str, Dict[str, int]] = {}

    for activity_key, mapping in ACTIVITY_MAP.items():
        coll = db[mapping["choices"]]
        # totals pipeline
        pipeline = [
            {"$group": {
                "_id": None,
                "attempts": {"$sum": 1},
                "correct": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "correct"]}, 1, 0]}},
                "similar": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "similar"]}, 1, 0]}},
                "other": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "other"]}, 1, 0]}},
                "users": {"$addToSet": "$user_id"}
            }},
            {"$project": {"attempts": 1, "correct": 1, "similar": 1, "other": 1, "users": 1}}
        ]
        rows = await coll.aggregate(pipeline).to_list(length=1)
        if rows:
            r = rows[0]
            total_attempts += int(r.get("attempts", 0))
            total_correct += int(r.get("correct", 0))
            total_similar += int(r.get("similar", 0))
            total_other += int(r.get("other", 0))
            for u in r.get("users", []):
                if u is not None:
                    total_users_set.add(str(u))

        # per-user aggregates
        per_user_pipeline = [
            {"$group": {
                "_id": "$user_id",
                "attempts": {"$sum": 1},
                "correct": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "correct"]}, 1, 0]}},
                "similar": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "similar"]}, 1, 0]}},
                "other": {"$sum": {"$cond": [{"$eq": ["$chosen_option", "other"]}, 1, 0]}}
            }}
        ]
        rows = await coll.aggregate(per_user_pipeline).to_list(length=None)
        for r in rows:
            uid = str(r["_id"])
            entry = per_user_map.setdefault(uid, {"attempts": 0, "correct": 0, "similar": 0, "other": 0})
            entry["attempts"] += int(r.get("attempts", 0))
            entry["correct"] += int(r.get("correct", 0))
            entry["similar"] += int(r.get("similar", 0))
            entry["other"] += int(r.get("other", 0))

    acc = (total_correct / total_attempts) if total_attempts else None

    per_user_list = []
    for uid, v in per_user_map.items():
        a = v["attempts"]; c = v["correct"]; s = v["similar"]; o = v["other"]
        per_user_list.append(PerUserAggregate(user_id=uid, attempts=a, correct=c, similar=s, other=o, accuracy=(c / a) if a else None))

    return OverallSummary(
        total_users=len(total_users_set),
        total_attempts=total_attempts,
        total_correct=total_correct,
        total_similar=total_similar,
        total_other=total_other,
        accuracy=acc,
        per_user=per_user_list
    )


@router.get("/session/{session_id}/result", response_model=SessionSummaryItem)
async def get_session_result(session_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Single-session summary (per-session aggregate). Aggregates across all activities.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    # run same aggregation for each choices coll and merge
    combined = {"first_ts": None, "last_ts": None, "attempts": 0, "correct": 0, "similar": 0, "other": 0}
    any_found = False

    for mapping in ACTIVITY_MAP.values():
        coll = db[mapping["choices"]]
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
        if rows:
            any_found = True
            r = rows[0]
            ft = r.get("first_ts"); lt = r.get("last_ts")
            if ft and (combined["first_ts"] is None or ft < combined["first_ts"]): combined["first_ts"] = ft
            if lt and (combined["last_ts"] is None or lt > combined["last_ts"]): combined["last_ts"] = lt
            combined["attempts"] += int(r.get("attempts", 0))
            combined["correct"] += int(r.get("correct", 0))
            combined["similar"] += int(r.get("similar", 0))
            combined["other"] += int(r.get("other", 0))

    if not any_found:
        raise HTTPException(status_code=404, detail="Session not found or no choices recorded")

    attempts = combined["attempts"]
    correct = combined["correct"]
    similar = combined["similar"]
    other = combined["other"]
    acc = (correct / attempts) if attempts else None

    return SessionSummaryItem(
        session_id=session_id,
        user_id=None,
        first_timestamp=combined["first_ts"],
        last_timestamp=combined["last_ts"],
        attempts=attempts,
        correct=correct,
        similar=similar,
        other=other,
        accuracy=acc
    )


# ---------------- session -> user endpoint ----------------

@router.get("/session/{session_id}/user")
async def get_user_for_session(session_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Return the user_id for a given session_id.
    Searches all configured session collections and returns the first match.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    user_id = await resolve_user_id_from_session(db, session_id)
    if not user_id:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"session_id": session_id, "user_id": user_id}


# ---------------- DEBUG endpoint (temporary) ----------------

def _find_non_serializable(obj: Any, path: str = "") -> List[Tuple[str, str, str]]:
    """
    Returns list of tuples (path, type_name, repr_snippet) of values that are not "safe".
    Safe: str,int,float,bool,None,datetime,date,dict,list
    """
    safe_primitive_types = (str, int, float, bool, type(None), datetime, date)
    bad = []
    if isinstance(obj, safe_primitive_types):
        return bad
    if isinstance(obj, dict):
        for k, v in obj.items():
            bad += _find_non_serializable(v, f"{path}/{k}" if path else str(k))
        return bad
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            bad += _find_non_serializable(v, f"{path}[{i}]")
        return bad
    # known bson types
    if isinstance(obj, (ObjectId, Decimal128, DBRef, Binary, re.Pattern)):
        bad.append((path, type(obj).__name__, repr(obj)[:200]))
        return bad
    # functions/classes/modules etc.
    if isinstance(obj, (types.FunctionType, types.ModuleType, type)):
        bad.append((path, type(obj).__name__, repr(obj)[:200]))
        return bad
    # objects with __dict__
    if hasattr(obj, "__dict__"):
        try:
            attrs = vars(obj)
            for k, v in attrs.items():
                bad += _find_non_serializable(v, f"{path}.{k}" if path else k)
            return bad
        except Exception:
            bad.append((path, type(obj).__name__, repr(obj)[:200]))
            return bad
    # fallback: unknown type
    bad.append((path, type(obj).__name__, repr(obj)[:200]))
    return bad


@router.get("/debug/users/{user_id}/results-raw")
async def debug_user_results_raw(user_id: str, activity: Optional[str] = Query("all"), db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    DEBUG: returns raw normalized documents (not pydantic-converted) and lists of suspicious fields/types.
    Use this to find documents that still contain non-serializable types.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="DB not available")

    coll_specs = _collections_for_activity(activity)
    q = {"user_id": user_id}

    docs = []
    for spec in coll_specs:
        cursor = db[spec["choices"]].find(q).limit(200)
        async for d in cursor:
            normalized = _normalize_choice_doc(d, spec["activity"], spec["choices"])
            # attach raw unsanitized for detection
            normalized["_raw_unsanitized"] = d
            docs.append(normalized)

    report = []
    for nd in docs:
        raw_uns = nd.get("_raw_unsanitized")
        bads_before = _find_non_serializable(raw_uns)
        sanitized = _sanitize_bson(raw_uns)
        bads_after = _find_non_serializable(sanitized)
        report.append({
            "id": str(nd.get("_raw", {}).get("_id") or nd.get("_id") or ""),
            "activity": nd.get("_activity"),
            "source_collection": nd.get("_source_collection"),
            "bad_before_sanitize": bads_before,
            "bad_after_sanitize": bads_after,
            "sanitized_preview": sanitized if isinstance(sanitized, (dict, list)) and len(str(sanitized)) < 2000 else str(sanitized)[:2000]
        })

    return {"count": len(report), "report": report}
