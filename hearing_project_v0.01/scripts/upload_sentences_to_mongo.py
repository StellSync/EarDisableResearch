#!/usr/bin/env python3
# upload_sentences_to_mongo.py
# -*- coding: utf-8 -*-
"""
Upload sentence manifest JSON into MongoDB (safe upsert).

Usage examples:
  python upload_sentences_to_mongo.py --file sentence_audio_manifest.json
  python upload_sentences_to_mongo.py --data-dir hearing_project_v0.01 --file sentence_audio_manifest.json
  python upload_sentences_to_mongo.py /full/path/to/sentence_audio_manifest.json --collection sentences --reset

Environment variables:
  MONGO_URI (default included below)
  DB_NAME   (default: hearingdb)
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

# ---------- Defaults (override with env vars) ----------
DEFAULT_MONGO = os.getenv(
    "MONGO_URI",
    "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority",
)
DB_NAME = os.getenv("DB_NAME", "hearingdb")

# Default expected filename (you can change when calling)
DEFAULT_FILENAME = "sentence_audio_manifest.json"

# Required keys for each manifest item (one entry per index)
DEFAULT_REQUIRED_KEYS = [
    "section",
    "index",
    "sentences",
    "sentences_translit",
    "highlighted_words",
    "highlighted_translit",
    "audio_paths",
]

# ---------------------------------------------------------------------
# Utility helpers (file resolution similar to your sample)
# ---------------------------------------------------------------------
def find_file_recursively(base_dir: Path, filename: str) -> Optional[Path]:
    for p in base_dir.rglob(filename):
        if p.is_file():
            return p
    return None

def find_project_root_ancestor(start: Path, project_folder_name: str = "hearing_project_v0.01") -> Optional[Path]:
    p = start.resolve()
    for parent in [p] + list(p.parents):
        if parent.name == project_folder_name:
            return parent
    return None

def resolve_path(file: str = None, data_dir: str = None, json_positional: str = None) -> str:
    # 1: direct positional path
    if json_positional:
        p = Path(json_positional).expanduser().resolve()
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"JSON file not found at explicit positional path: {p}")

    # If file looks like a path with separators
    if file and (os.path.isabs(file) or any(sep in file for sep in (os.sep, "/"))):
        p = Path(file).expanduser().resolve()
        if p.exists():
            return str(p)
        else:
            raise FileNotFoundError(f"Explicit file path not found: {p}")

    filename = file or DEFAULT_FILENAME

    # If data_dir provided
    if data_dir:
        data_path = Path(data_dir).expanduser().resolve()
        if not data_path.exists():
            raise FileNotFoundError(f"Provided data-dir does not exist: {data_path}")
        candidate = data_path / filename
        if candidate.exists():
            return str(candidate)
        found = find_file_recursively(data_path, filename)
        if found:
            return str(found)

    # Try script-relative folder: <script_dir>/data/<filename>
    try:
        script_dir = Path(__file__).resolve().parent
    except Exception:
        script_dir = Path.cwd()
    script_data_candidate = script_dir / "data" / filename
    if script_data_candidate.exists():
        return str(script_data_candidate)

    # Try finding hearing_project_v0.01 ancestor and scripts/data
    cwd = Path.cwd()
    project_root = find_project_root_ancestor(cwd, "hearing_project_v0.01")
    if not project_root:
        project_root = find_project_root_ancestor(script_dir, "hearing_project_v0.01")
    if project_root:
        candidate = project_root / "scripts" / "data" / filename
        if candidate.exists():
            return str(candidate)
        scripts_data_dir = project_root / "scripts" / "data"
        if scripts_data_dir.exists():
            found = find_file_recursively(scripts_data_dir, filename)
            if found:
                return str(found)

    # final fallback: try Path(filename) relative to cwd
    final_candidate = Path(filename).expanduser().resolve()
    if final_candidate.exists():
        return str(final_candidate)

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

# ---------------------------------------------------------------------
# JSON loader + validation
# ---------------------------------------------------------------------
def load_json(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array (list) at the top level.")
    return data

def validate_record_schema(rec: Dict[str, Any], required_keys: List[str]) -> List[str]:
    """Return list of missing keys or schema problems (empty list if valid)."""
    missing = [k for k in required_keys if k not in rec or rec.get(k) in (None, "")]
    problems = list(missing)
    # extra checks: sentences must be list of strings; audio_paths must be list with length >= sentences
    if "sentences" in rec:
        if not isinstance(rec["sentences"], list) or not all(isinstance(x, str) for x in rec["sentences"]):
            problems.append("sentences:not_list_of_strings")
    if "audio_paths" in rec:
        if not isinstance(rec["audio_paths"], list):
            problems.append("audio_paths:not_list")
        else:
            # require same number or at least one audio per sentence (>=)
            if "sentences" in rec and isinstance(rec["sentences"], list):
                if len(rec["audio_paths"]) < len(rec["sentences"]):
                    problems.append("audio_paths:len_less_than_sentences")
    return problems

# ---------------------------------------------------------------------
# Mongo helpers
# ---------------------------------------------------------------------
def connect(uri: str) -> MongoClient:
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    return client

def ensure_indexes(coll):
    # Unique constraint on (section, index) so each index is unique per section
    coll.create_index([("section", ASCENDING), ("index", ASCENDING)], unique=True, name="uniq_section_index")

def build_ops(items: List[Dict[str, Any]], required_keys=None):
    ops = []
    now = datetime.now(timezone.utc)
    skipped = []
    for i, it in enumerate(items):
        problems = validate_record_schema(it, required_keys or [])
        if problems:
            skipped.append({"pos": i, "problems": problems, "record": it})
            continue
        filt = {"section": it.get("section"), "index": it.get("index")}
        to_set = dict(it)
        to_set["updated_at"] = now
        to_set_on_insert = {"created_at": now}
        ops.append(UpdateOne(filt, {"$set": to_set, "$setOnInsert": to_set_on_insert}, upsert=True))
    return ops, skipped

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Upload sentence manifest JSON into MongoDB (auto-search)")
    ap.add_argument("--file", help="Filename inside data-dir or path to JSON (default filename if omitted)",
                    default=DEFAULT_FILENAME)
    ap.add_argument("--data-dir", help="Directory where the file may reside (optional)")
    ap.add_argument("--collection", default="sentences", help='MongoDB collection name (default: "sentences")')
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
        print(f"\n Skipped {len(skipped)} records due to schema problems (showing up to 5):")
        for s in skipped[:5]:
            print(f" - pos {s['pos']} problems {s['problems']} -> index: {s['record'].get('index')} section: {s['record'].get('section')}")

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

    matched = getattr(result, "matched_count", 0)
    modified = getattr(result, "modified_count", 0)
    upserted = len(getattr(result, "upserted_ids", {})) if getattr(result, "upserted_ids", None) else 0

    print(f"\n Done. Matched: {matched}, Modified: {modified}, Upserted: {upserted}")
    print(f'Database: "{DB_NAME}", Collection: "{args.collection}"')

if __name__ == "__main__":
    main()
