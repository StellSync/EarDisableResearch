from fastapi import APIRouter, Query
import json
from pathlib import Path

router = APIRouter(prefix="/api/v1/lexicon", tags=["lexicon"])
PHON_INDEX = Path.cwd() / "models" / "phoneme_index.json"
LEXICON_FILE = Path.cwd() / "models" / "lexicon.json"

@router.get("/search")
def search_by_phoneme(phoneme: str = Query(...), n: int = 10):
    if not PHON_INDEX.exists() or not LEXICON_FILE.exists():
        return {"results": []}
    idx = json.loads(PHON_INDEX.read_text(encoding="utf-8"))
    lex = json.loads(LEXICON_FILE.read_text(encoding="utf-8"))
    ids = idx.get(phoneme, [])[:n]
    results = [x for x in lex if x["word_id"] in ids]
    return {"results": results}
