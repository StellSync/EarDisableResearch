from fastapi import APIRouter, Depends
from ...auth.token import verify_token
from pathlib import Path

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

@router.get("/validate-data")
def validate_data(user=Depends(verify_token)):
    base = Path.cwd()
    files = {
        "corpus_transliterated": base / "Data" / "processed" / "corpus_transliterated.json",
        "lexicon": base / "models" / "lexicon.json",
        "phoneme_index": base / "models" / "phoneme_index.json",
        "audio_dir": base / "Data" / "audio" / "words_norm"
    }
    checks = {}
    for k,p in files.items():
        checks[k] = {"path": str(p), "exists": p.exists(), "size_bytes": p.stat().st_size if p.exists() and p.is_file() else None}
    return checks
