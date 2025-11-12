# app/main.py
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# local package imports (explicit)
from . import db as db_module
from .routes import WiyanjanaSession
from .routes import swara_session as session_module
from .routes import sentence_session
# import the doctor/activity routes module directly (matches your file path)
from .routes import activityResults_Session as activity_results_module

from .utils import _filesystem_root_for_audio

AUDIO_ROOT = os.getenv("AUDIO_ROOT", "./swara_audio_cloud")

app = FastAPI(title="Hearing Project API")

# Allow cross-origin requests for development. Restrict origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(WiyanjanaSession.router)
app.include_router(session_module.router, prefix="/sessions", tags=["sessions"])
app.include_router(sentence_session.router, prefix="/sentence_sessions", tags=["sentence_sessions"])

# Register the doctor/activity results router (from app/routes/activityResults_Session.py)
app.include_router(activity_results_module.router, prefix="/doctor", tags=["doctor"])


@app.on_event("startup")
async def startup_event():
    # initialize DB / clients
    try:
        db_module.init_client()
    except Exception as e:
        # keep startup from crashing silently — re-raise after printing
        print("Warning: db_module.init_client() raised an exception:", repr(e))
        raise

    fs_audio = _filesystem_root_for_audio(AUDIO_ROOT)
    print(f"Startup: MongoDB client initialized, audio mounted at: {fs_audio}")

    from fastapi.staticfiles import StaticFiles
    # ensure folder exists so mount works
    Path(fs_audio).mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=str(fs_audio)), name="audio")
    print(f"Mounted /audio -> {fs_audio}")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        db_module.close_client()
    except Exception as e:
        print("Warning: db_module.close_client() raised an exception:", repr(e))
