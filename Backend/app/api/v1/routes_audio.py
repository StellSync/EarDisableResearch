from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])
AUDIO_ROOT = Path(r"c:/Users/94772/Desktop/Adaptive Audio-Based Therapeutic System for Post-Linguistic Hearing Loss Enhancing Emergency and Noisy-Environment Speech Comprehension-Test1/EarDisableResearch/Models/Data/audio/words_norm")

@router.get("/word/{word_id}")
def get_word_audio(word_id: str):
    p = AUDIO_ROOT / f"{word_id}.wav"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(str(p), media_type="audio/wav", filename=f"{word_id}.wav")
