# scripts/load_data.py
"""
Improved loader:
 - respects relative AUDIO_ROOT (keeps DB audio_path relative)
 - resolves actual filesystem location relative to project root
 - logs every audio lookup to logs/audio_path_log.txt
 - prefers existing singlish, uses translit map if available, else falls back to unidecode
"""
import os
import json
import csv
import argparse
from pathlib import Path
from pymongo import MongoClient, ReplaceOne
from unidecode import unidecode
import re
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DEFAULT_MONGO = os.getenv(
    "MONGO_URI",
    "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority",
)
DB_NAME = os.getenv("DB_NAME", "hearingdb")
AUDIO_ROOT = os.getenv("AUDIO_ROOT", "./swara_audio_cloud")
DATA_DIR = os.getenv("DATA_DIR", "./data")
TRANSLIT_FILE = Path(DATA_DIR) / "swara_translit_improved.json"

# logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "audio_path_log.txt"

def log_audio_event(message: str):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")

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

def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]

def _filesystem_root_for_audio(audio_root_setting: str) -> Path:
    ar = Path(audio_root_setting)
    if ar.is_absolute():
        return ar
    return (_project_root() / ar)

def find_audio_path_for_doc(audio_root_setting: str, section: str, index: str, sinhala_word: str):
    """
    Returns (audio_path_relative_str_or_None, audio_url_or_None)
    audio_path_relative_str_or_None: string like "swara_audio_cloud/ක්‍රියාකාරකම-01/01_word_rom.mp3"
    audio_url_or_None: "/audio/section/filename.mp3"
    """
    fs_root = _filesystem_root_for_audio(audio_root_setting)
    section_dir = fs_root / section

    if not section_dir.exists():
        log_audio_event(f"❌ Section folder not found for section '{section}': {section_dir}")
        return None, None

    for fname in expected_filenames(section, index, sinhala_word):
        fs_path = section_dir / fname
        if fs_path.exists():
            rel_db_path = str(Path(audio_root_setting) / section / fname).replace("\\", "/")
            url = f"/audio/{section}/{fname}"
            log_audio_event(f"✅ Found audio for '{sinhala_word}' -> {rel_db_path}")
            return rel_db_path, url

    files = list(section_dir.glob("*.mp3"))
    if files:
        chosen = files[0]
        rel_db_path = str(Path(audio_root_setting) / section / chosen.name).replace("\\", "/")
        url = f"/audio/{section}/{chosen.name}"
        log_audio_event(f"⚠️ Fallback audio used for '{sinhala_word}' -> {rel_db_path}")
        return rel_db_path, url

    log_audio_event(f"❌ Missing audio for '{sinhala_word}' in folder {section_dir}")
    return None, None

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
        if isinstance(data, dict):
            for k in ("rows", "data", "items", "docs", "words"):
                if k in data and isinstance(data[k], list):
                    return data[k]
            for v in data.values():
                if isinstance(v, list):
                    return v
            return []
        return data

def load_csv(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)
    return rows

def normalize_row(r: dict):
    if not isinstance(r, dict):
        return None
    section = r.get("section") or r.get("section_name") or r.get("Section") or r.get("section_si") or "unknown"
    idx = r.get("index") or r.get("idx") or r.get("Index") or r.get("index_str") or ""
    sinhala = r.get("sinhala_word") or r.get("word") or r.get("Word") or r.get("Sinhala") or ""
    main_vowel = r.get("main_vowel_name") or r.get("vowel") or r.get("Vowel") or r.get("main_vowel") or ""
    main_vowel_char = r.get("main_vowel_char") or r.get("vowel_char") or r.get("main_vowel_char") or ""
    return {
        "section": section,
        "index": str(idx).zfill(2),
        "sinhala_word": sinhala,
        "main_vowel_name": main_vowel,
        "main_vowel_char": main_vowel_char,
        "existing_singlish": r.get("singlish") or r.get("singlish_translit") or r.get("translit") or r.get("transliteration"),
    }

def try_load_translit_map(translit_path: Path, orig_rows: list):
    if not translit_path.exists():
        return {}
    try:
        raw = json.loads(translit_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if isinstance(raw, dict):
        direct = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str):
                if any(ord(ch) > 127 for ch in k) and all(ord(ch) < 128 for ch in v):
                    direct[k.strip()] = v.strip()
        if direct:
            return direct

    grouped = {}
    for r in orig_rows:
        sec = r.get("section", "unknown")
        grouped.setdefault(sec, []).append(r)

    section_romans = {}
    def gather_strings(obj, sec_hint=None):
        res = []
        if isinstance(obj, dict):
            s = obj.get("section") or obj.get("section_name")
            if isinstance(s, str):
                sec_hint = s
            for v in obj.values():
                res += gather_strings(v, sec_hint)
        elif isinstance(obj, list):
            for item in obj:
                res += gather_strings(item, sec_hint)
        elif isinstance(obj, str):
            if any(c.isalpha() for c in obj) and all(ord(c) < 128 for c in obj):
                key = sec_hint or "global"
                section_romans.setdefault(key, []).append(obj.strip())
        return res

    gather_strings(raw)

    translit_map = {}
    for sec, romans in section_romans.items():
        orig_list = grouped.get(sec, [])
        n = min(len(orig_list), len(romans))
        for i in range(n):
            sinh = orig_list[i].get("sinhala_word","").strip()
            roman = romans[i].strip()
            if sinh:
                translit_map[sinh] = roman

    if not translit_map:
        global_romans = section_romans.get("global", [])
        if not global_romans:
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
            global_romans = tokens
        orig_all = [r for r in orig_rows if r.get("sinhala_word")]
        n = min(len(orig_all), len(global_romans))
        for i in range(n):
            translit_map[orig_all[i]["sinhala_word"].strip()] = global_romans[i].strip()

    return translit_map

def upsert_docs(mongo_uri, db_name, docs, translit_map):
    client = MongoClient(mongo_uri)
    db = client[db_name]
    coll = db.docs
    ops = []
    audio_found = 0
    audio_missing = 0
    for d in docs:
        if not d or not d.get("sinhala_word"):
            continue
        query = {"section": d["section"], "index": d["index"], "sinhala_word": d["sinhala_word"]}
        path, part = find_audio_path_for_doc(AUDIO_ROOT, d["section"], d["index"], d["sinhala_word"])
        if path:
            audio_found += 1
        else:
            audio_missing += 1

        if d.get("existing_singlish"):
            singlish_val = str(d["existing_singlish"]).strip()
        elif translit_map and translit_map.get(d["sinhala_word"]):
            singlish_val = translit_map.get(d["sinhala_word"])
        else:
            singlish_val = ascii_translit(d["sinhala_word"])

        doc = {
            "section": d["section"],
            "index": d["index"],
            "sinhala_word": d["sinhala_word"],
            "singlish": singlish_val,
            "main_vowel_name": d["main_vowel_name"],
            "main_vowel_char": d.get("main_vowel_char", ""),
            # store relative path (preserve format with forward slashes)
            "audio_path": path,
            "audio_url": part if part else None,
            "presented": False,
            "user_events": []
        }
        ops.append(ReplaceOne(query, {**query, **doc}, upsert=True))

    print(f"Prepared {len(ops)} upsert operations (audio found: {audio_found}, missing: {audio_missing})")
    if not ops:
        print("No operations to write (no valid rows).")
        return {"upserted_count": 0, "modified_count": 0}
    res = coll.bulk_write(ops)
    inserted = getattr(res, "inserted_count", 0)
    modified = getattr(res, "modified_count", 0)
    upserted = getattr(res, "upserted_count", 0)
    matched = getattr(res, "matched_count", 0)
    print("Bulk write result:", {"inserted": inserted, "upserted": upserted, "modified": modified, "matched": matched})
    return {"upserted_count": upserted, "modified_count": modified, "inserted_count": inserted}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default=DEFAULT_MONGO)
    ap.add_argument("--db", default=DB_NAME)
    ap.add_argument("--data-dir", default=DATA_DIR)
    ap.add_argument("--file", default="swara_words_vowels_firstletter.json")
    args = ap.parse_args()

    print("Using MONGO URI:", args.mongo)
    print("DB_NAME:", args.db)
    print("AUDIO_ROOT (env):", AUDIO_ROOT)
    print("AUDIO_ROOT (filesystem check):", _filesystem_root_for_audio(AUDIO_ROOT))
    print("DATA_DIR:", args.data_dir)
    data_dir = Path(args.data_dir)
    fpath = data_dir / args.file
    if not fpath.exists():
        print("File not found:", fpath)
        return

    if fpath.suffix.lower() in (".json",):
        rows = load_json(fpath)
    elif fpath.suffix.lower() in (".csv",):
        rows = load_csv(fpath)
    else:
        print("Unsupported file type:", fpath.suffix)
        return

    if not isinstance(rows, list):
        print("Loaded JSON is not a list. Detected type:", type(rows))
        if isinstance(rows, dict):
            for k in ("rows", "data", "items", "docs", "words"):
                if k in rows and isinstance(rows[k], list):
                    rows = rows[k]
                    break

    print("Total raw rows loaded:", len(rows))
    sample = rows[:5]
    print("Sample raw rows (first 3):")
    for i, r in enumerate(sample[:3], start=1):
        if isinstance(r, dict):
            print(f" {i}. {{ " + ", ".join(f"{k}: {r.get(k)}" for k in list(r.keys())[:6]) + " }}")
        else:
            print(f" {i}. {r}")

    norm = []
    for r in rows:
        nr = normalize_row(r)
        if nr and nr.get("sinhala_word"):
            norm.append(nr)
    print("Normalized rows count (valid rows with sinhala_word):", len(norm))
    if len(norm) == 0:
        print("No valid normalized rows found. Please check your JSON keys and sample above.")
        return

    translit_map = try_load_translit_map(TRANSLIT_FILE, norm)
    print("Translit map size:", len(translit_map))
    if len(translit_map) > 0:
        i = 0
        print("Sample translit mappings (first 10):")
        for k, v in translit_map.items():
            print(" ", k, "->", v)
            i += 1
            if i >= 10:
                break

    result = upsert_docs(args.mongo, args.db, norm, translit_map)
    print("Inserted/updated ops:", result.get("upserted_count", 0) + result.get("modified_count", 0))
    print("Done.")

if __name__ == "__main__":
    main()
