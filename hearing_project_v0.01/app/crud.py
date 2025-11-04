# app/crud.py
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from . import db as db_module
try:
    from bson import ObjectId
except Exception:
    ObjectId = None

def now_ts() -> str:
    return datetime.utcnow().isoformat()

async def insert_rows(rows: List[Dict[str,Any]]) -> int:
    if not rows:
        return 0
    docs = []
    for r in rows:
        docs.append({
            "_id": str(uuid.uuid4()),   # ensure string UUID ids for new docs
            "section": r.get("section","unknown"),
            "index": str(r.get("index","")).zfill(2),
            "sinhala_word": r.get("sinhala_word",""),
            "singlish": r.get("singlish",""),
            "main_vowel_name": r.get("main_vowel_name",""),
            "main_vowel_char": r.get("main_vowel_char",""),
            "audio_path": r.get("audio_path"),
            "audio_url": r.get("audio_url"),
            "presented": False,
            "user_events": []
        })
    res = await db_module.db.docs.insert_many(docs)
    return len(res.inserted_ids)

async def upsert_doc_by_keys(section: str, index: str, sinhala_word: str, payload: Dict[str,Any]) -> None:
    query = {"section": section, "index": index, "sinhala_word": sinhala_word}
    await db_module.db.docs.update_one(query, {"$set": payload}, upsert=True)

async def get_all_docs() -> List[Dict[str,Any]]:
    cursor = db_module.db.docs.find({})
    return [d async for d in cursor]

async def get_doc_by_id(doc_id: str) -> Optional[Dict[str,Any]]:
    if not doc_id:
        return None
    # try string id first
    doc = await db_module.db.docs.find_one({"_id": doc_id})
    if doc:
        return doc
    # fallback to ObjectId
    if ObjectId is not None:
        try:
            oid = ObjectId(doc_id)
            doc = await db_module.db.docs.find_one({"_id": oid})
            return doc
        except Exception:
            return None
    return None

async def pick_random_for_vowel(vowel: str, exclude_presented: bool=False) -> Optional[Dict[str,Any]]:
    q: Dict[str,Any] = {"main_vowel_name": vowel}
    if exclude_presented:
        q["presented"] = False
    cursor = db_module.db.docs.find(q)
    docs = [d async for d in cursor]
    if not docs:
        return None
    import random
    return random.choice(docs)

async def find_same_index_pair(doc: Dict[str,Any]) -> Optional[Dict[str,Any]]:
    if not doc:
        return None
    return await db_module.db.docs.find_one({
        "section": doc.get("section"),
        "index": doc.get("index"),
        "_id": {"$ne": doc.get("_id")}
    })

async def mark_presented(doc_id: str) -> None:
    if not doc_id:
        return
    # try string update
    try:
        res = await db_module.db.docs.update_one({"_id": doc_id}, {"$set": {"presented": True}})
        if getattr(res, "matched_count", 0):
            return
    except Exception:
        pass
    # try ObjectId fallback
    if ObjectId is not None:
        try:
            oid = ObjectId(doc_id)
            await db_module.db.docs.update_one({"_id": oid}, {"$set": {"presented": True}})
        except Exception:
            pass

async def create_session(vowel_sequence: List[str], max_vowels: int) -> Dict[str,Any]:
    session = {
        "_id": str(uuid.uuid4()),
        "started_at": now_ts(),
        "vowel_sequence": vowel_sequence[:max_vowels],
        "test_index": 0,
        "primary_doc": None,
        "primary_role": None,
        "original_primary_doc_id": None,
        "visible_options": {},
        "events": [],
        "results": {},
        # store first choices per vowel to avoid scanning events for the first-choice
        "first_choices": {}
    }
    await db_module.db.sessions.insert_one(session)
    return session

async def get_session(session_id: str) -> Optional[Dict[str,Any]]:
    if not session_id:
        return None
    s = await db_module.db.sessions.find_one({"_id": session_id})
    return s

async def update_session(session_id: str, patch: Dict[str,Any]) -> Optional[Dict[str,Any]]:
    await db_module.db.sessions.update_one({"_id": session_id}, {"$set": patch})
    return await get_session(session_id)

async def push_event(session_id: str, ev: Dict[str,Any]) -> None:
    """
    Push event to session.events and attach to docs.user_events if it references a doc.
    Simple dedupe: if the last event has identical type+payload, skip push.
    """
    if ev is None:
        return
    ev["ts"] = now_ts()
    payload = ev.get("payload", {}) or {}

    # normalize doc id-like fields to string if possible
    doc_keys = ("doc_id", "presented_doc_id", "target_doc_id", "confirm_doc_id", "chosen_doc_id")
    for k in doc_keys:
        if k in payload and payload[k] is not None:
            try:
                payload[k] = str(payload[k])
            except Exception:
                pass
    ev["payload"] = payload

    # dedupe: fetch the last event and compare
    existing = await db_module.db.sessions.find_one({"_id": session_id}, {"events": {"$slice": -1}})
    last_event = None
    if existing and existing.get("events"):
        last_event = existing["events"][-1]
    if last_event and last_event.get("type") == ev.get("type") and last_event.get("payload") == ev.get("payload"):
        # skip pushing duplicate event
        return

    # push event into session
    await db_module.db.sessions.update_one({"_id": session_id}, {"$push": {"events": ev}})

    # if event references a doc id, attach event to doc.user_events
    doc_id = payload.get("doc_id") or payload.get("presented_doc_id") or payload.get("target_doc_id") or payload.get("confirm_doc_id") or payload.get("chosen_doc_id")
    if not doc_id:
        return

    try:
        res = await db_module.db.docs.update_one({"_id": doc_id}, {"$push": {"user_events": ev}})
        if getattr(res, "matched_count", 0):
            return
    except Exception:
        pass

    if ObjectId is not None:
        try:
            oid = ObjectId(doc_id)
            await db_module.db.docs.update_one({"_id": oid}, {"$push": {"user_events": ev}})
        except Exception:
            pass
