# app/services/vowel_service.py
import random
from typing import Optional, Dict, Any, List
from ..core.db import db
from ..core.models import now_ts, make_session_id

# --- helpers to query words collection ---

async def _get_all_vowels() -> List[str]:
    vowels = await db.words.distinct("main_vowel_name")
    vowels = [v for v in vowels if v]
    vowels.sort()
    return vowels

async def _pick_vowel_sequence(default_vowel: str, max_tests: int = 5) -> List[str]:
    vowels = await _get_all_vowels()
    others = [v for v in vowels if v != default_vowel]
    random.shuffle(others)
    seq = [default_vowel] + others[: max(0, max_tests - 1)]
    # dedupe while preserving order (in case default missing)
    seen = set()
    out = []
    for v in seq:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out

async def _find_default_doc():
    doc = await db.words.find_one({"section": "ක්‍රියාකාරකම-01", "index": "01"})
    if doc:
        return doc
    return await db.words.find_one({})

async def _pick_target_for_vowel(vowel: str) -> Optional[Dict]:
    if not vowel:
        return None
    cands = await db.words.find({"main_vowel_name": vowel}).to_list(length=1000)
    if not cands:
        return None
    return random.choice(cands)

async def _find_same_index_pair(target_doc: Dict) -> Optional[Dict]:
    if not target_doc:
        return None
    q = {"section": target_doc.get("section"), "index": target_doc.get("index"), "_id": {"$ne": target_doc["_id"]}}
    return await db.words.find_one(q)

# --- session helper and audit ---

def _audit_event(session: Dict, ev_type: str, payload: Dict) -> Dict:
    ev = {"ts": now_ts(), "type": ev_type, "payload": payload}
    session.setdefault("events", []).append(ev)
    return ev

def _present_word_payload(doc: Dict) -> Dict:
    return {
        "_id": doc["_id"],
        "section": doc.get("section"),
        "index": doc.get("index"),
        "sinhala_word": doc.get("sinhala_word"),
        "singlish": doc.get("singlish"),
        "main_vowel_name": doc.get("main_vowel_name"),
        "audio_path": doc.get("audio_path"),
    }

# --- public service functions ---

async def start_session(user_id: Optional[str] = None, max_tests: int = 5) -> Dict:
    default_doc = await _find_default_doc()
    default_vowel = default_doc["main_vowel_name"] if default_doc else None
    vowel_sequence = await _pick_vowel_sequence(default_vowel or "", max_tests)
    session_id = make_session_id()
    session = {
        "session_id": session_id,
        "user_id": user_id,
        "started_at": now_ts(),
        "vowel_sequence": vowel_sequence,
        "test_index": 0,
        "primary_doc_id": None,
        "primary_role": None,
        "original_primary_doc_id": None,
        "visible_options": {},
        "events": [],
        "results": {}
    }

    # prepare and present first primary (if avail)
    if not vowel_sequence:
        await db.sessions.insert_one(session)
        return {"session": session, "first_word": None}

    first_vowel = vowel_sequence[0]
    target = await _pick_target_for_vowel(first_vowel)
    if not target:
        session["results"][first_vowel] = "unknown"
        await db.sessions.insert_one(session)
        return {"session": session, "first_word": None}

    similar = await _find_same_index_pair(target)
    if not similar:
        sim_cand = await db.words.find_one({"section": target.get("section"), "main_vowel_name": {"$ne": first_vowel}})
        similar = sim_cand

    session["primary_doc_id"] = target["_id"]
    session["primary_role"] = "primary"
    session["original_primary_doc_id"] = target["_id"]
    session["visible_options"] = {"correct": target["_id"], "similar": (similar["_id"] if similar else None), "other": None}

    _audit_event(session, "present_primary", {
        "vowel": first_vowel,
        "target_doc_id": target["_id"],
        "target_word": target.get("sinhala_word"),
        "similar_doc_id": (similar["_id"] if similar else None),
        "audio_path": target.get("audio_path")
    })

    await db.sessions.insert_one(session)
    return {"session": session, "first_word": _present_word_payload(target)}

async def submit_answer(session_id: str, word_id: str, choice: str) -> Dict:
    session = await db.sessions.find_one({"session_id": session_id})
    if not session:
        return {"error": "session not found"}

    role = session.get("primary_role")
    test_idx = session.get("test_index", 0)
    vowel_sequence = session.get("vowel_sequence", [])
    vowel = vowel_sequence[test_idx] if test_idx < len(vowel_sequence) else None

    payload = {
        "vowel": vowel,
        "role": role,
        "choice": choice,
        "presented_doc_id": session.get("primary_doc_id"),
        "chosen_doc_id": session.get("visible_options", {}).get(choice)
    }
    ev = _audit_event(session, "user_choice", payload)
    await db.sessions.update_one({"session_id": session_id}, {"$push": {"events": ev}})

    # PRIMARY -> present a confirm candidate
    if role == "primary":
        cand = await db.words.find_one({"main_vowel_name": vowel, "_id": {"$ne": session["original_primary_doc_id"]}})
        if not cand:
            # no confirm candidate -> mark unknown and advance (set result as unknown)
            session["results"][vowel] = "unknown"
            await db.sessions.update_one({"session_id": session_id}, {"$set": {"results": session["results"]}})
            return {"next_action": "present_next", "word": None}

        similar = await _find_same_index_pair(cand)
        if similar and similar["_id"] == session["original_primary_doc_id"]:
            similar = None
        session["primary_doc_id"] = cand["_id"]
        session["primary_role"] = "confirm"
        session["visible_options"] = {"correct": cand["_id"], "similar": (similar["_id"] if similar else None), "other": None}
        ev2 = _audit_event(session, "present_confirm", {"vowel": vowel, "confirm_doc_id": cand["_id"], "confirm_word": cand.get("sinhala_word"), "similar_doc_id": (similar["_id"] if similar else None)})
        await db.sessions.update_one({"session_id": session_id}, {"$set": {"primary_doc_id": session["primary_doc_id"], "primary_role": session["primary_role"], "visible_options": session["visible_options"]}, "$push": {"events": ev2}})
        return {"next_action": "present_confirm", "word": _present_word_payload(cand)}

    # CONFIRM -> finalize vowel result and advance
    else:
        # get last primary user choice for this vowel
        events = session.get("events", [])
        primary_choice_first = None
        for ev in reversed(events):
            if ev["type"] == "user_choice" and ev["payload"].get("role") == "primary" and ev["payload"].get("vowel") == vowel:
                primary_choice_first = ev["payload"].get("choice")
                break

        if primary_choice_first == "correct" or choice == "correct":
            res = "heard"
        elif primary_choice_first == choice and primary_choice_first in ("similar", "other"):
            res = "not_heard"
        else:
            res = "not_heard"

        session["results"][vowel] = res
        _audit_event(session, "vowel_result", {"vowel": vowel, "result": res, "choices": [primary_choice_first, choice]})

        session["test_index"] = session.get("test_index", 0) + 1
        session["primary_doc_id"] = None
        session["primary_role"] = None
        session["original_primary_doc_id"] = None
        session["visible_options"] = {}

        await db.sessions.update_one({"session_id": session_id}, {"$set": {"results": session["results"], "test_index": session["test_index"]}, "$push": {"events": session.get("events", [])}})

        # done?
        if session["test_index"] >= len(session.get("vowel_sequence", [])):
            compact = {
                "meta": {
                    "started_at": session.get("started_at"),
                    "exported_at": now_ts(),
                    "vowel_sequence": session.get("vowel_sequence", []),
                    "test_count": len(session.get("vowel_sequence", []))
                },
                "summary": session.get("results", {}),
                "session_id": session_id,
                "user_id": session.get("user_id"),
                "events": session.get("events", [])
            }
            await db.results.insert_one(compact)
            await db.sessions.update_one({"session_id": session_id}, {"$set": {"finished_at": now_ts(), "final_summary": session.get("results", {})}})
            return {"next_action": "finished", "summary": session.get("results", {}), "session_id": session_id}
        else:
            next_vowel = session["vowel_sequence"][session["test_index"]]
            target = await _pick_target_for_vowel(next_vowel)
            if not target:
                session["results"][next_vowel] = "unknown"
                await db.sessions.update_one({"session_id": session_id}, {"$set": {"results": session["results"], "test_index": session["test_index"]}})
                return {"next_action": "present_primary", "word": None}

            similar = await _find_same_index_pair(target)
            if not similar:
                sim_cand = await db.words.find_one({"section": target.get("section"), "main_vowel_name": {"$ne": next_vowel}})
                similar = sim_cand

            session["primary_doc_id"] = target["_id"]
            session["primary_role"] = "primary"
            session["original_primary_doc_id"] = target["_id"]
            session["visible_options"] = {"correct": target["_id"], "similar": (similar["_id"] if similar else None), "other": None}

            _audit_event(session, "present_primary", {"vowel": next_vowel, "target_doc_id": target["_id"], "target_word": target.get("sinhala_word"), "similar_doc_id": (similar["_id"] if similar else None), "audio_path": target.get("audio_path")})
            await db.sessions.update_one({"session_id": session_id}, {"$set": {"primary_doc_id": session["primary_doc_id"], "primary_role": session["primary_role"], "original_primary_doc_id": session["original_primary_doc_id"], "visible_options": session["visible_options"], "test_index": session["test_index"]}, "$push": {"events": session.get("events", [])}})
            return {"next_action": "present_primary", "word": _present_word_payload(target)}
