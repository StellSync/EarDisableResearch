#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload swara words JSON into MongoDB (auto-search version).

Supports:
    --file <filename.json> --data-dir <dir>
    OR just: python upload_json_to_db.py ./scripts/data/swara_words_vowels_firstletter_with_audio.json

Automatically searches subfolders of --data-dir if file not found directly.
Validates each record has the correct keys.
Creates unique index on (section, index, sinhala_word).
Performs upserts — safe to rerun.

Environment variables (with defaults):
  MONGO_URI (default provided in code)
  DB_NAME   (default: hearingdb)

Default fallback path used if no explicit data-dir is found:
  hearing_project_v0.01/scripts/data/swara_words_vowels_firstletter_with_audio.json
"""
from __future__ import annotations
import os
import json
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys

from pymongo import MongoClient, UpdateOne, ASCENDING
from pymongo.errors import BulkWriteError, ServerSelectionTimeoutError

DEFAULT_MONGO = os.getenv(
    "MONGO_URI",
    "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority",
)
DB_NAME = os.getenv("DB_NAME", "hearingdb")

DEFAULT_REQUIRED_KEYS = [
    "section", "index", "sinhala_word", "singlish_word",
    "main_vowel_char", "main_vowel_name", "audio_path"
]

# Default filename you asked for (single dot .json)
DEFAULT_FILENAME = "swara_words_vowels_firstletter_with_audio.json"

# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------

def find_file_recursively(base_dir: Path, filename: str) -> Optional[Path]:
    """Search for filename recursively under base_dir."""
    for p in base_dir.rglob(filename):
        if p.is_file():
            return p
    return None

def find_project_root_ancestor(start: Path, project_folder_name: str = "hearing_project_v0.01") -> Optional[Path]:
    """Walk up from start looking for a folder named project_folder_name."""
    p = start.resolve()
    for parent in [p] + list(p.parents):
        if parent.name == project_folder_name:
            return parent
    return None

def resolve_path(file: str = None, data_dir: str = None, json_positional: str = None) -> str:
    """Resolve file path, with recursive search and sensible fallbacks.

    Fallback strategy:
      1. If json_positional given -> use it directly.
      2. If file is an absolute or relative path (contains a path separator) and exists -> use it.
      3. If data_dir provided:
          a) check data_dir/file
          b) search recursively under data_dir
      4. Try script-relative folder: <script_dir>/data/<file>
      5. Try to find ancestor folder named 'hearing_project_v0.01' and use its scripts/data/<file>
      6. As last resort, try Path(file) relative to CWD
    """
    # 1. direct positional
    if json_positional:
        p = Path(json_positional).expanduser().resolve()
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"JSON file not found at explicit positional path: {p}")

    # If file looks like a path with separators, treat as path
    if file and (os.path.isabs(file) or any(sep in file for sep in (os.sep, "/"))):
        p = Path(file).expanduser().resolve()
        if p.exists():
            return str(p)
        else:
            raise FileNotFoundError(f"Explicit file path not found: {p}")

    # If file omitted, use default filename
    filename = file or DEFAULT_FILENAME

    # 3. If data_dir provided, check there first
    if data_dir:
        data_path = Path(data_dir).expanduser().resolve()
        # if user gave ".", make it explicit based on cwd
        if not data_path.exists():
            raise FileNotFoundError(f"Provided data-dir does not exist: {data_path}")
        candidate = data_path / filename
        if candidate.exists():
            return str(candidate)
        # try recursive search
        found = find_file_recursively(data_path, filename)
        if found:
            return str(found)
        # If not found, continue to other fallbacks

    # 4. Try script-relative folder: <script_dir>/data/<filename>
    try:
        script_dir = Path(__file__).resolve().parent
    except Exception:
        script_dir = Path.cwd()
    script_data_candidate = script_dir / "data" / filename
    if script_data_candidate.exists():
        return str(script_data_candidate)

    # 5. Try to find ancestor folder named hearing_project_v0.01 and use its scripts/data/
    cwd = Path.cwd()
    project_root = find_project_root_ancestor(cwd, "hearing_project_v0.01")
    if not project_root:
        # also try near the script directory
        project_root = find_project_root_ancestor(script_dir, "hearing_project_v0.01")
    if project_root:
        candidate = project_root / "scripts" / "data" / filename
        if candidate.exists():
            return str(candidate)
        # try recursive search under project_root/scripts/data
        scripts_data_dir = project_root / "scripts" / "data"
        if scripts_data_dir.exists():
            found = find_file_recursively(scripts_data_dir, filename)
            if found:
                return str(found)

    # 6. Finally, try to resolve relative to current working directory (non-recursive)
    final_candidate = Path(filename).expanduser().resolve()
    if final_candidate.exists():
        return str(final_candidate)

    # Nothing found — give an informative error listing attempted places
    attempted = []
    if data_dir:
        attempted.append(str(Path(data_dir) / filename))
    attempted.append(str(script_data_candidate))
    if project_root:
        attempted.append(str(project_root / "scripts" / "data" / filename))
    attempted.append(str(final_candidate))

    raise FileNotFoundError(
        f"File '{filename}' not found. Attempted locations (examples):\n  - {attempted[0]}\n  - {attempted[1]}\n  - {attempted[2] if len(attempted) > 2 else 'n/a'}\n"
    )

def load_json(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array (list) at the top level.")
    return data

def connect(uri: str) -> MongoClient:
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    return client

def ensure_indexes(coll):
    coll.create_index(
        [("section", ASCENDING), ("index", ASCENDING), ("sinhala_word", ASCENDING)],
        unique=True,
        name="uniq_section_index_sinhala",
    )

def build_ops(items: List[Dict[str, Any]], required_keys=None):
    ops = []
    now = datetime.now(timezone.utc)
    skipped = []
    for i, it in enumerate(items):
        missing = [k for k in (required_keys or []) if k not in it or it.get(k) in (None, "")]
        if missing:
            skipped.append({"pos": i, "missing": missing, "record": it})
            continue
        filt = {
            "section": it.get("section"),
            "index": it.get("index"),
            "sinhala_word": it.get("sinhala_word"),
        }
        to_set = dict(it)
        to_set["updated_at"] = now
        to_set_on_insert = {"created_at": now}
        ops.append(
            UpdateOne(
                filt,
                {"$set": to_set, "$setOnInsert": to_set_on_insert},
                upsert=True,
            )
        )
    return ops, skipped

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Upload swara words JSON into MongoDB (auto-search)")
    ap.add_argument("--file", help="Filename inside data-dir, or a path to JSON (default filename if omitted: %(default)s)",
                    default=DEFAULT_FILENAME)
    ap.add_argument("--data-dir", help="Directory where the file resides (optional)")
    ap.add_argument("--collection", default="swara_words", help='MongoDB collection name (default: "swara_words")')
    ap.add_argument("--reset", action="store_true", help='Drop the collection before loading')
    ap.add_argument("--required-keys", nargs="*", default=DEFAULT_REQUIRED_KEYS,
                    help=f"List of required keys (default: {DEFAULT_REQUIRED_KEYS})")
    ap.add_argument("json_path", nargs="?", help="Optional direct path to the JSON file")
    args = ap.parse_args()

    try:
        json_full_path = resolve_path(args.file, args.data_dir, args.json_path)
    except Exception as e:
        ap.error(str(e))

    print(f"\nUsing JSON file: {json_full_path}")
    print(f"Connecting to MongoDB cluster... ({DEFAULT_MONGO})")
    try:
        client = connect(DEFAULT_MONGO)
    except ServerSelectionTimeoutError as e:
        print(" Failed to connect to MongoDB:", e)
        raise SystemExit(1)

    db = client[DB_NAME]
    coll = db[args.collection]

    if args.reset:
        print(f'\nDropping collection "{args.collection}" (if exists)...')
        coll.drop()
        coll = db[args.collection]

    ensure_indexes(coll)

    items = load_json(json_full_path)
    print(f"\nRead {len(items)} records from JSON. Validating and preparing bulk upserts...")

    ops, skipped = build_ops(items, required_keys=args.required_keys)
    if skipped:
        print(f"\n Skipped {len(skipped)} records due to missing keys (showing up to 5):")
        for s in skipped[:5]:
            print(f" - pos {s['pos']} missing {s['missing']} -> sinhala_word: {s['record'].get('sinhala_word')}")

    if not ops:
        print("\nNo valid operations to perform after validation. Exiting.")
        return

    try:
        result = coll.bulk_write(ops, ordered=False)
    except BulkWriteError as bwe:
        result = bwe.details
        print("\n Bulk write errors:")
        print(json.dumps(result, indent=2, default=str))
        raise

    # result may be a BulkWriteResult or an error details dict depending on exception handling
    matched = getattr(result, "matched_count", 0)
    modified = getattr(result, "modified_count", 0)
    upserted = len(getattr(result, "upserted_ids", {})) if getattr(result, "upserted_ids", None) else 0

    print(f"\n Done. Matched: {matched}, Modified: {modified}, Upserted: {upserted}")
    print(f'Database: "{DB_NAME}", Collection: "{args.collection}"')

if __name__ == "__main__":
    main()
