"""
Rules-based adaptive service that picks next item.
Strictly reads models/lexicon.json and models/phoneme_index.json
(which must be produced by the notebook pipeline).
"""
import random, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEXICON_FILE = ROOT / "models" / "lexicon.json"
PHON_INDEX_FILE = ROOT / "models" / "phoneme_index.json"

def load_lexicon():
    if not LEXICON_FILE.exists():
        raise FileNotFoundError(f"Lexicon file not found at {LEXICON_FILE}. Run the data pipeline to create it.")
    return json.loads(LEXICON_FILE.read_text(encoding="utf-8"))

def load_phon_index():
    if not PHON_INDEX_FILE.exists():
        raise FileNotFoundError(f"Phoneme index file not found at {PHON_INDEX_FILE}. Run the data pipeline to create it.")
    return json.loads(PHON_INDEX_FILE.read_text(encoding="utf-8"))

def pick_next(session_history: list, difficulty_hint: str = None):
    lex = load_lexicon()
    phon_idx = load_phon_index()
    if not lex:
        return None
    # find last incorrect event that had a target_phoneme
    last_err = None
    for ev in reversed(session_history):
        if ev.get("correct") is False and ev.get("target_phoneme"):
            last_err = ev; break
    candidates = lex
    if last_err:
        ph = last_err.get("target_phoneme")
        ids = phon_idx.get(ph, [])
        candidates = [w for w in lex if w["word_id"] in ids] or lex
    # simple difficulty heuristics
    if difficulty_hint == "easy":
        easy = [c for c in candidates if len(c.get("letters", [])) <= 3]
        candidates = easy or candidates
    elif difficulty_hint == "hard":
        hard = [c for c in candidates if len(c.get("letters", [])) >= 4]
        candidates = hard or candidates
    return random.choice(candidates)
