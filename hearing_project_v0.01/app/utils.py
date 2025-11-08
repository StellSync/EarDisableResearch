# app/utils.py
import os
from pathlib import Path
import re
from unidecode import unidecode
from typing import Tuple, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

# AUDIO_ROOT environment will be handled in main; helper below resolves relative to project.
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]

def _filesystem_root_for_audio(audio_root_setting: str) -> Path:
    ar = Path(audio_root_setting)
    if ar.is_absolute():
        return ar
    return (_project_root() / ar)

def ascii_translit(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^\w\-_.]", "", unidecode(s or "")) or "word"

def safe_unicode_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[\\/:\*\?\"<>\|]", "_", s)
    s = re.sub(r"\s+", "_", s)
    return s[:60]

def expected_filenames(section: str, idx: str, sinhala_word: str):
    idx = str(idx).zfill(2)
    uni = safe_unicode_filename(sinhala_word or "")
    ascii_name = ascii_translit(sinhala_word or "")
    return [f"{idx}_{uni}_{ascii_name}.mp3", f"{idx}_{uni}.mp3"]

def find_audio_file(audio_root_setting: str, section: str, index: str, sinhala_word: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (audio_path_relative, audio_url) OR (None, None).
    audio_path_relative is stored in DB (preserves AUDIO_ROOT relative setting if provided relative).
    audio_url is like "/audio/<section>/<filename.mp3>" used by clients.
    """
    fs_root = _filesystem_root_for_audio(audio_root_setting)
    section_dir = fs_root / section
    if not section_dir.exists():
        return None, None

    for fname in expected_filenames(section, index, sinhala_word):
        fs_path = section_dir / fname
        if fs_path.exists():
            rel_db_path = str(Path(audio_root_setting) / section / fname).replace("\\", "/")
            audio_url = f"/audio/{section}/{fname}"
            return rel_db_path, audio_url

    # fallback to first mp3 in folder
    files = list(section_dir.glob("*.mp3"))
    if files:
        chosen = files[0]
        rel_db_path = str(Path(audio_root_setting) / section / chosen.name).replace("\\", "/")
        audio_url = f"/audio/{section}/{chosen.name}"
        return rel_db_path, audio_url

    return None, None

def mongo_to_jsonable(obj: Dict[str,Any]) -> Dict[str,Any]:
    """
    Convert common Mongo types to JSON-serializable: ObjectId -> str, datetime -> isoformat, etc.
    Only shallow conversion needed for our doc/session shapes.
    """
    if obj is None:
        return None
    out = {}
    for k, v in obj.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, dict):
            out[k] = mongo_to_jsonable(v)
        elif isinstance(v, list):
            newlist = []
            for item in v:
                if isinstance(item, dict):
                    newlist.append(mongo_to_jsonable(item))
                elif isinstance(item, ObjectId):
                    newlist.append(str(item))
                else:
                    newlist.append(item)
            out[k] = newlist
        else:
            # datetime isoformat is handled at creation layer; keep as-is if string
            out[k] = v
    # ensure _id is string if present
    if "_id" in out and not isinstance(out["_id"], str):
        out["_id"] = str(out["_id"])
    return out
