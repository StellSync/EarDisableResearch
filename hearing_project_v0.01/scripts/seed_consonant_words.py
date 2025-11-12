#!/usr/bin/env python3
# scripts/seed_consonant_words.py
# -*- coding: utf-8 -*-
"""
Seed consonant words into MongoDB (robust path resolution).

Usage:
  python seed_consonant_words.py
  python seed_consonant_words.py --file hearing_project_v0.01/scripts/data/wiyanjana_words_consonants_firstletter.json
"""

from __future__ import annotations
import os
import json
import argparse
import asyncio
from pathlib import Path
from typing import Optional
from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient

# ---------- defaults ----------
DEFAULT_MONGO = os.getenv(
    "MONGO_URI",
    "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority",
)
DB_NAME = os.getenv("DB_NAME", "hearingdb")
COLLECTION_NAME = "consonant_words"

# Use forward-slash default (avoid backslash escape issues)
DEFAULT_INPUT = "hearing_project_v0.01/scripts/data/wiyanjana_words_consonants_firstletter.json"

# Optional base URL to serve audio files (set in env for local dev or production CDN)
AUDIO_BASE_URL = os.getenv("AUDIO_BASE_URL", "").rstrip("/")

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def to_posix_path(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        return Path(str(s)).as_posix()
    except Exception:
        return str(s).replace("\\", "/")

def make_audio_url(posix_path: Optional[str]) -> Optional[str]:
    if not posix_path:
        return None
    if not AUDIO_BASE_URL:
        return None
    p = posix_path.lstrip("./").lstrip("/")
    return f"{AUDIO_BASE_URL}/{p}"

def find_file_try_paths(provided: str) -> Optional[Path]:
    """
    Try to resolve the provided path smartly:
      - if provided exists as given -> return it
      - try relative to script parent (project root guesses)
      - search recursively under likely directories (project root and cwd) for basename
    """
    p = Path(provided).expanduser()
    if p.exists():
        return p.resolve()

    # If path is relative, try relative to script dir and its parent
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / provided,
        script_dir.parent / provided,             # one level up
        script_dir.parent.parent / provided,     # two levels up
        Path.cwd() / provided
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()

    # As a last resort, search recursively for the basename under project root or cwd
    name = Path(provided).name
    search_roots = [script_dir.parent, Path.cwd()]
    for root in search_roots:
        if not root.exists():
            continue
        for found in root.rglob(name):
            if found.is_file():
                return found.resolve()

    return None

# ---------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------
async def seed_consonant_words(json_path: Path, drop_before: bool = True):
    client = AsyncIOMotorClient(DEFAULT_MONGO)
    db = client[DB_NAME]
    coll = db[COLLECTION_NAME]

    if not json_path.exists():
        raise FileNotFoundError(f"Input JSON file not found: {json_path}")

    # load JSON
    with json_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, list):
        raise ValueError("Expected top-level JSON array (list) in input file.")

    print(f"Loaded {len(data)} records from {json_path}")

    if drop_before:
        await coll.drop()
        print(f"Dropped existing collection '{COLLECTION_NAME}'")

    # build documents
    docs = []
    for i, item in enumerate(data):
        try:
            section = item.get("section")
            index = item.get("index")
            sinhala_word = item.get("sinhala_word")
            singlish_word = item.get("singlish_word") or item.get("singlish") or item.get("singlish_word")
            changing_char = item.get("changing_consonant_character") or (item.get("changing_consonant") or {}).get("character")
            changing_name = item.get("changing_consonant_name") or (item.get("changing_consonant") or {}).get("name")

            raw_audio = item.get("audio_path") or ""
            posix_audio = to_posix_path(raw_audio)
            audio_url = make_audio_url(posix_audio)

            doc = {
                "section": section,
                "index": index,
                "sinhala_word": sinhala_word,
                "singlish": singlish_word,
                "changing_consonant": {
                    "character": changing_char,
                    "name": changing_name
                },
                "audio_path": posix_audio,
                "audio_url": audio_url
            }
            docs.append(doc)
        except Exception as e:
            print(f"Skipping record {i} due to error: {e}")

    if not docs:
        print("No documents to insert after processing. Exiting.")
        client.close()
        return

    # create useful indexes
    await coll.create_index([("section", 1), ("index", 1)])
    await coll.create_index([("changing_consonant.character", 1)])
    await coll.create_index([("changing_consonant.name", 1)])

    # insert many
    try:
        res = await coll.insert_many(docs)
        print(f"Inserted {len(res.inserted_ids)} documents into '{COLLECTION_NAME}'")
    except Exception as e:
        print("Insert failed:", e)
        # attempt upserts per-document as fallback
        for doc in docs:
            filt = {"section": doc["section"], "index": doc["index"], "sinhala_word": doc["sinhala_word"]}
            try:
                await coll.update_one(filt, {"$set": doc}, upsert=True)
            except Exception as e2:
                print("Upsert failed for", filt, e2)
        print("Fallback upserts attempted.")

    # print one sample document
    sample = await coll.find_one({}, projection={"_id": 0})
    if sample:
        print("Sample inserted document (no _id shown):")
        print(json.dumps(sample, ensure_ascii=False, indent=2))

    client.close()

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Seed consonant words into MongoDB")
    ap.add_argument("--file", "-f", help="Input JSON file (default: %(default)s)", default=DEFAULT_INPUT)
    ap.add_argument("--no-drop", action="store_true", help="Don't drop collection before inserting")
    args = ap.parse_args()

    resolved = find_file_try_paths(args.file)
    if not resolved:
        raise FileNotFoundError(f"Input JSON not found. Tried: {args.file} and common project locations. "
                                "Pass --file with the correct path.")
    json_path = resolved

    # run async
    asyncio.run(seed_consonant_words(json_path=json_path, drop_before=not args.no_drop))

if __name__ == "__main__":
    main()
