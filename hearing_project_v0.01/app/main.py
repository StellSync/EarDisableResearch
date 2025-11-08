# app/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import db as db_module
from .routes import  WiyanjanaSession
from .routes import swara_session as session_module
from .utils import _filesystem_root_for_audio
from pathlib import Path
from .routes import sentence_session


AUDIO_ROOT = os.getenv("AUDIO_ROOT", "./swara_audio_cloud")

app = FastAPI(title="Hearing Project API")

# Allow cross-origin requests for all APIs (suitable for development).
# If you want to restrict origins in production, replace ["*"] with a list of allowed origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.include_router(session.router)
app.include_router(WiyanjanaSession.router)
app.include_router(session_module.router, prefix="/sessions", tags=["sessions"])
app.include_router(sentence_session.router, prefix="/sentence_sessions", tags=["sentence_sessions"])

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
