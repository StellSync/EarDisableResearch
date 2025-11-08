# scripts/update_singlish_from_translit.py
"""
One-time updater to fill/update `singlish` for existing docs in MongoDB.

Strategy:
 1) Try to load swara_translit_improved.json and build mapping (same heuristics as loader).
 2) If mapping exists, update docs by matching sinhala_word -> roman.
 3) Otherwise, fallback: extract roman token from audio_path filename pattern (index_unicode_roman.mp3).
"""
import json
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import re

load_dotenv()
MONGO = os.getenv("MONGO_URI", "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority")
DB = os.getenv("DB_NAME", "hearingdb")
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
TRANSLIT_PATH = DATA_DIR / "swara_translit_improved.json"

# basic ascii translit fallback
from unidecode import unidecode
import re
def ascii_translit(s: str) -> str:
    return re.sub(r"[^\w\-_.]", "", unidecode(s or "")) or "word"

def try_load_translit_map(translit_path: Path, orig_rows=None):
    # reuse simplified heuristics from load_data.py
    if not translit_path.exists():
        return {}
    raw = json.loads(translit_path.read_text(encoding="utf-8"))
    # direct mapping
    if isinstance(raw, dict):
        direct = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str) and any(ord(ch) > 127 for ch in k) and all(ord(ch) < 128 for ch in v):
                direct[k.strip()] = v.strip()
        if direct:
            return direct
    # fallback: collect ascii strings and map by order to orig_rows if given
    tokens = []
    def collect_ascii(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                collect_ascii(v)
        elif isinstance(obj, list):
            for v in obj:
                collect_ascii(v)
        elif isinstance(obj, str):
            if any(c.isalpha() for c in obj) and all(ord(c) < 128 for c in obj):
                tokens.append(obj.strip())
    collect_ascii(raw)
    mapping = {}
    if orig_rows and tokens:
        n = min(len(orig_rows), len(tokens))
        for i in range(n):
            mapping[orig_rows[i]["sinhala_word"].strip()] = tokens[i].strip()
    return mapping

def main():
    client = MongoClient(MONGO)
    db = client[DB]
    coll = db.docs
    # load existing docs
    docs = list(coll.find({}))
    print("Found docs:", len(docs))
    # try to load orig rows to help mapping ordering
    orig_rows = []
    orig_path = Path(os.getenv("DATA_DIR","./data")) / "swara_words_vowels_firstletter.json"
    if orig_path.exists():
        try:
            orig_rows = json.loads(orig_path.read_text(encoding="utf-8"))
            # if dict wrapper, try common keys
            if isinstance(orig_rows, dict):
                for k in ("rows","data","items","docs","words"):
                    if k in orig_rows and isinstance(orig_rows[k], list):
                        orig_rows = orig_rows[k]
                        break
        except Exception:
            orig_rows = []
    translit_map = try_load_translit_map(TRANSLIT_PATH, orig_rows)
    print("Loaded translit_map entries:", len(translit_map))

    updates = 0
    for d in docs:
        sinh = d.get("sinhala_word")
        if not sinh:
            continue
        new_s = None
        # prefer translit map
        if sinh in translit_map:
            new_s = translit_map[sinh]
        # else try to extract from audio_path filename
        if not new_s:
            ap = d.get("audio_path") or d.get("audioPath") or d.get("audio")
            if ap:
                name = Path(ap).name
                # expected patterns: idx_unicode_roman.mp3 or idx_unicode_roman-other.mp3
                m = re.match(r"^\d+_[^_]+_([^\.]+)\.mp3$", name)
                if m:
                    new_s = m.group(1)
        # fallback ascii translit
        if not new_s:
            new_s = ascii_translit(sinh)
        if new_s and new_s != d.get("singlish"):
            coll.update_one({"_id": d["_id"]}, {"$set": {"singlish": new_s}})
            updates += 1
            print("Updated", d["_id"], sinh, "->", new_s)
    print("Total updated docs:", updates)

if __name__ == "__main__":
    main()
