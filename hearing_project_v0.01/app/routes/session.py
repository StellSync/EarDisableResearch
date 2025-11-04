# app/routes/session.py
from fastapi import APIRouter, HTTPException
from .. import crud, db
from ..schemas import SessionStartResp, UserChoice
from ..utils import find_audio_file, mongo_to_jsonable, _filesystem_root_for_audio
import os
import random
from typing import Optional, Dict, Any

router = APIRouter(prefix="/api/session", tags=["session"])

AUDIO_ROOT = os.getenv("AUDIO_ROOT", "./swara_audio_cloud")
PREFER_GENERATION = os.getenv("PREFER_GENERATION", "true").lower() in ("1","true","yes")
MAX_VOWEL_TESTS = int(os.getenv("MAX_VOWEL_TESTS", "5"))

def make_audio_url(section: str, filename_part: str):
    return f"/audio/{filename_part}"

async def _fetch_min_doc_by_id(doc_id: Optional[str]) -> Optional[Dict[str,Any]]:
    if not doc_id:
        return None
    doc = await crud.get_doc_by_id(doc_id)
    if not doc:
        return None
    j = mongo_to_jsonable(doc)
    return {
        "_id": j.get("_id"),
        "sinhala_word": j.get("sinhala_word"),
        "singlish": j.get("singlish"),
        "audio_url": j.get("audio_url"),
        "audio_path": j.get("audio_path")
    }

@router.post("/start", response_model=SessionStartResp)
async def start_session():
    default_doc = await db.db.docs.find_one({"section": "ක්‍රියාකාරකම-01", "index": "01"})
    if not default_doc:
        default_doc = await db.db.docs.find_one({})
    if not default_doc:
        raise HTTPException(status_code=404, detail="No docs loaded")
    default_vowel = default_doc["main_vowel_name"]
    all_vowels = await db.db.docs.distinct("main_vowel_name")
    others = [v for v in all_vowels if v != default_vowel]
    random.shuffle(others)
    seq = [default_vowel] + others[:max(0, MAX_VOWEL_TESTS-1)]
    session = await crud.create_session(seq, MAX_VOWEL_TESTS)
    return {"session_id": session["_id"], "vowel_sequence": session["vowel_sequence"], "started_at": session["started_at"]}

async def _prepare_doc_for_response(doc):
    if not doc:
        return None
    if not doc.get("audio_url"):
        path, url = find_audio_file(AUDIO_ROOT, doc["section"], doc["index"], doc["sinhala_word"])
        if path:
            audio_url = url
            # update DB (doc["_id"] may be string or ObjectId; use update by _id as-is)
            try:
                await db.db.docs.update_one({"_id": doc["_id"]}, {"$set": {"audio_path": path, "audio_url": audio_url}})
            except Exception:
                # try string/ObjectId fallback handled in crud.mark_presented etc - ignore here
                pass
            doc["audio_path"] = path
            doc["audio_url"] = audio_url
    return mongo_to_jsonable(doc)

@router.get("/next/{session_id}")
async def get_next(session_id: str):
    session = await crud.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    seq = session["vowel_sequence"]
    idx = session["test_index"]
    if idx >= len(seq):
        return {"done": True, "results": session.get("results", {})}

    # No active primary -> present primary
    if not session.get("primary_doc"):
        vowel = seq[idx]
        target = await crud.pick_random_for_vowel(vowel, exclude_presented=True)
        if not target:
            target = await crud.pick_random_for_vowel(vowel, exclude_presented=False)
        if not target:
            session["results"][vowel] = "unknown"
            session["test_index"] = idx + 1
            await crud.update_session(session_id, {"results": session["results"], "test_index": session["test_index"]})
            return {"done": False, "info": f"No words for vowel {vowel}"}

        similar = await crud.find_same_index_pair(target)
        if similar is None:
            sim_cursor = db.db.docs.find({"section": target["section"], "main_vowel_name": {"$ne": vowel}, "_id": {"$ne": target["_id"]}}).limit(50)
            sim_candidates = [d async for d in sim_cursor]
            similar = random.choice(sim_candidates) if sim_candidates else None

        await crud.mark_presented(str(target.get("_id")) if target.get("_id") else None)

        visible_ids = {
            "correct": str(target["_id"]) if target and target.get("_id") else None,
            "similar": str(similar["_id"]) if similar and similar.get("_id") else None,
            "other": None
        }
        orig_primary_id = str(target["_id"]) if target and target.get("_id") else None

        # Save a JSON-serializable primary_doc copy into session
        primary_doc_json = mongo_to_jsonable(target)
        patch = {
            "primary_doc": primary_doc_json,
            "primary_role": "primary",
            "original_primary_doc_id": orig_primary_id,
            "visible_options": visible_ids
        }
        await crud.push_event(session_id, {"type": "present_primary", "payload": {"vowel": vowel, "target_doc_id": orig_primary_id, "target_word": target["sinhala_word"]}})
        await crud.update_session(session_id, patch)

        tdoc = await _prepare_doc_for_response(target)
        sdoc = await _prepare_doc_for_response(similar) if similar else None

        visible_resp = {
            "correct": {"_id": tdoc.get("_id"), "sinhala_word": tdoc.get("sinhala_word"), "singlish": tdoc.get("singlish"), "audio_url": tdoc.get("audio_url")} if tdoc else None,
            "similar": {"_id": sdoc.get("_id"), "sinhala_word": sdoc.get("sinhala_word"), "singlish": sdoc.get("singlish"), "audio_url": sdoc.get("audio_url")} if sdoc else None,
            "other": None
        }
        return {"present": {"role": "primary", "vowel": vowel, "primary_doc": tdoc, "visible_options": visible_resp}}

    # active primary exists -> return current presentation
    else:
        role = session["primary_role"]
        primary_doc = session.get("primary_doc")
        visible_ids = session.get("visible_options", {}) or {}
        correct_id = visible_ids.get("correct")
        similar_id = visible_ids.get("similar")
        correct_doc = await _fetch_min_doc_by_id(correct_id) if correct_id else None
        similar_doc = await _fetch_min_doc_by_id(similar_id) if similar_id else None
        visible_resp = {"correct": correct_doc, "similar": similar_doc, "other": None}
        return {"present": {"role": role, "vowel": session["vowel_sequence"][idx], "primary_doc": primary_doc, "visible_options": visible_resp}}

@router.post("/choice")
async def submit_choice(choice: UserChoice):
    session = await crud.get_session(choice.session_id)
    if not session:
        raise HTTPException(404, "session not found")

    # record event (push_event will normalize payload and dedupe)
    await crud.push_event(choice.session_id, {"type": "user_choice", "payload": choice.dict()})

    # if role == "primary" -> we present a confirm candidate
    if choice.role == "primary":
        v = choice.vowel
        # pick confirm candidate (same vowel)
        cand = await crud.pick_random_for_vowel(v, exclude_presented=True)
        if not cand:
            cand = await crud.pick_random_for_vowel(v, exclude_presented=False)
        if not cand:
            # mark unknown & advance
            session["results"][v] = "unknown"
            session["test_index"] += 1
            await crud.update_session(session["_id"], {"results": session["results"], "test_index": session["test_index"], "primary_doc": None, "primary_role": None, "visible_options": {}})
            await crud.push_event(session["_id"], {"type": "no_confirm_candidate", "payload": {"vowel": v}})
            return {"status": "no_confirm_candidate", "next_index": session["test_index"]}

        sim = await crud.find_same_index_pair(cand)
        if not sim:
            sim_cands = [d async for d in db.db.docs.find({"section": cand["section"], "main_vowel_name": {"$ne": v}, "_id": {"$ne": cand["_id"]}}).limit(50)]
            sim = random.choice(sim_cands) if sim_cands else None

        await crud.mark_presented(str(cand.get("_id")) if cand.get("_id") else None)

        # save cand as JSON-safe doc in session and visible ids
        primary_doc_json = mongo_to_jsonable(cand)
        visible_ids = {
            "correct": str(cand["_id"]) if cand and cand.get("_id") else None,
            "similar": str(sim["_id"]) if sim and sim.get("_id") else None,
            "other": None
        }

        # preserve original_primary_doc_id from session (do not overwrite)
        orig_primary = session.get("original_primary_doc_id")
        if not orig_primary:
            orig_primary = session.get("primary_doc", {}).get("_id")

        # store first-choice recorded for this vowel (so finalize can find it deterministically)
        first_choices = session.get("first_choices", {}) or {}
        # the incoming payload contains the user's first choice; it was normalized by push_event,
        # but we also keep it in session to avoid scanning events
        first_choices[v] = choice.choice

        await crud.update_session(session["_id"], {"primary_doc": primary_doc_json, "primary_role": "confirm", "visible_options": visible_ids, "original_primary_doc_id": orig_primary, "first_choices": first_choices})
        await crud.push_event(session["_id"], {"type": "present_confirm", "payload": {"vowel": v, "confirm_doc_id": str(cand["_id"]) if cand and cand.get("_id") else None, "confirm_word": cand["sinhala_word"]}})

        cand_json = await _prepare_doc_for_response(cand)
        sim_json = await _prepare_doc_for_response(sim) if sim else None

        visible_resp = {
            "correct": {"_id": cand_json.get("_id"), "sinhala_word": cand_json.get("sinhala_word"), "singlish": cand_json.get("singlish"), "audio_url": cand_json.get("audio_url")} if cand_json else None,
            "similar": {"_id": sim_json.get("_id"), "sinhala_word": sim_json.get("sinhala_word"), "singlish": sim_json.get("singlish"), "audio_url": sim_json.get("audio_url")} if sim_json else None,
            "other": None
        }

        return {"status": "confirm_presented", "confirm_doc": cand_json, "similar_doc": sim_json, "visible_options": visible_resp}

    else:
        # role == "confirm" -> finalize vowel decision
        v = choice.vowel
        # get stored first choice for vowel if available
        first_choices = session.get("first_choices", {}) or {}
        first_choice = first_choices.get(v)
        # fallback scanning events if necessary (defensive)
        if not first_choice:
            for ev in reversed(session.get("events", []) or []):
                if ev.get("type") == "user_choice" and ev.get("payload", {}).get("role") == "primary" and ev.get("payload", {}).get("vowel") == v:
                    first_choice = ev["payload"].get("choice")
                    break
        second_choice = choice.choice
        res = "heard" if (first_choice == "correct" or second_choice == "correct") else "not_heard"

        # update session
        session["results"][v] = res
        session["test_index"] += 1
        session["primary_doc"] = None
        session["primary_role"] = None
        session["visible_options"] = {}
        # clear first choice for vowel
        fc = session.get("first_choices", {}) or {}
        if v in fc:
            fc.pop(v, None)
        await crud.update_session(session["_id"], {"results": session["results"], "test_index": session["test_index"], "primary_doc": None, "primary_role": None, "visible_options": {}, "first_choices": fc})
        await crud.push_event(session["_id"], {"type": "vowel_result", "payload": {"vowel": v, "result": res, "choices": [first_choice, second_choice]}})
        return {"status": "finalized", "vowel": v, "result": res, "next_index": session["test_index"]}

@router.get("/export/{session_id}")
async def export_session(session_id: str):
    session = await crud.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    presented_cursor = db.db.docs.find({"presented": True})
    presented = [d async for d in presented_cursor]
    summary = {v: session["results"].get(v, "unknown") for v in session["vowel_sequence"]}
    out = {
        "meta": {"started_at": session["started_at"], "exported_at": crud.now_ts(), "vowel_sequence": session["vowel_sequence"], "test_count": len(session["vowel_sequence"])},
        "summary": summary,
        "presented_docs": [mongo_to_jsonable(d) for d in presented],
        "session": mongo_to_jsonable(session)
    }
    return out
