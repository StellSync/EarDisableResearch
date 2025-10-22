from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])
AUDIO_ROOT = Path.cwd() / "Data" / "audio" / "words_norm"

@router.get("/{type}/{id}")
def stream_audio(type: str, id: str):
    p = AUDIO_ROOT / f"{id}.wav"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Audio not found for id={id}. Expected at {p}")
    return FileResponse(str(p), media_type="audio/wav", filename=f"{id}.wav")
