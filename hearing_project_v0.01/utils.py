# app/utils.py
import re
import os
from pathlib import Path
from unidecode import unidecode
from datetime import datetime
from typing import Any

# ---------------- filename/translit helpers ----------------
def ascii_translit(s: str) -> str:
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

# ---------------- audio file finding (same semantics as loader) ----------------
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]

def _filesystem_root_for_audio(audio_root_setting: str) -> Path:
    ar = Path(audio_root_setting)
    if ar.is_absolute():
        return ar
    return (_project_root() / ar)

def find_audio_file(audio_root_setting: str, section: str, index: str, sinhala_word: str):
    """
    Try to locate audio file on filesystem.
    Returns: (db_relative_path_or_None, filename_part_or_None)
      - db_relative_path is like "swara_audio_cloud/ක්‍රියාකාරකම-01/01_word_rom.mp3"
      - filename_part is "section/filename.mp3" (used to build URL path portion)
    """
    fs_root = _filesystem_root_for_audio(audio_root_setting)
    section_dir = fs_root / section
    if not section_dir.exists():
        return None, None

    for fname in expected_filenames(section, index, sinhala_word):
        p = section_dir / fname
        if p.exists():
            # preserve relative DB path using original AUDIO_ROOT value (forward slashes)
            rel_db_path = f"{audio_root_setting}/{section}/{fname}".replace("\\", "/")
            return rel_db_path, f"{section}/{fname}"
    files = list(section_dir.glob("*.mp3"))
    if files:
        chosen = files[0]
        rel_db_path = f"{audio_root_setting}/{section}/{chosen.name}".replace("\\", "/")
        return rel_db_path, f"{section}/{chosen.name}"
    return None, None

# ---------------- json conversion for Mongo types ----------------
def mongo_to_jsonable(obj: Any):
    """
    Convert common non-JSON types returned from Mongo into JSON-friendly ones.
    Handles ObjectId (via str), datetime (isoformat), nested dicts/lists.
    """
    # simple types
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj

    # datetime -> iso
    if isinstance(obj, datetime):
        return obj.isoformat()

    # ObjectId or other types convertible via str()
    # Avoid converting mapping-like objects by accidentally iterating over them.
    try:
        from bson import ObjectId
        if isinstance(obj, ObjectId):
            return str(obj)
    except Exception:
        # bson not available on import, ignore
        pass

    # dict -> convert items
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k] = mongo_to_jsonable(v)
        return out

    # list/tuple -> convert each element
    if isinstance(obj, (list, tuple)):
        return [mongo_to_jsonable(x) for x in obj]

    # fallback: try to use __dict__ if present
    if hasattr(obj, "__dict__"):
        return mongo_to_jsonable(vars(obj))

    # final fallback: string representation
    return str(obj)
