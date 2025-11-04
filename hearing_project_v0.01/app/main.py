# app/main.py
import os
from fastapi import FastAPI
from . import db as db_module
from .routes import session
from .utils import _filesystem_root_for_audio
from pathlib import Path

AUDIO_ROOT = os.getenv("AUDIO_ROOT", "./swara_audio_cloud")

app = FastAPI(title="Hearing Project API")

app.include_router(session.router)

@app.on_event("startup")
async def startup_event():
    db_module.init_client()
    fs_audio = _filesystem_root_for_audio(AUDIO_ROOT)
    print(f"Startup: MongoDB client initialized, audio mounted at: {fs_audio}")
    from fastapi.staticfiles import StaticFiles
    # ensure folder exists so mount works
    Path(fs_audio).mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=str(fs_audio)), name="audio")
    print(f"Mounted /audio -> {fs_audio}")

@app.on_event("shutdown")
async def shutdown_event():
    db_module.close_client()
