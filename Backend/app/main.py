from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys, logging

# ---------- Robust Startup checks: ensure notebook pipeline outputs exist ----------
# Compute project root relative to this file (backend/app/main.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Candidate locations (cover different capitalizations/layouts you may have)
MODEL_CANDIDATES = [
    PROJECT_ROOT / "models",
    PROJECT_ROOT / "Models",
    PROJECT_ROOT / "models" / "data",    # in case models placed under models/data
]
DATA_CANDIDATES = [
    PROJECT_ROOT / "Data",
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "Models" / "data",
    PROJECT_ROOT / "models" / "data",
]

def first_existing(cands):
    for p in cands:
        if p.exists():
            return p
    # if none exist return the first candidate (so error messages are consistent)
    return cands[0]

MODELS_DIR = first_existing(MODEL_CANDIDATES)
DATA_DIR = first_existing(DATA_CANDIDATES)
PROCESSED_DIR = DATA_DIR / "processed"
AUDIO_DIR = DATA_DIR / "audio" / "words_norm"

REQUIRED_FILES = {
    "corpus_transliterated": PROCESSED_DIR / "corpus_transliterated.json",
    "lexicon": MODELS_DIR / "lexicon.json",
    "phoneme_index": MODELS_DIR / "phoneme_index.json",
}

missing = [name for name, p in REQUIRED_FILES.items() if not p.exists()]
if missing:
    logging.error("Required data artifacts missing: %s", missing)
    print("ERROR: Backend startup aborted. Missing pipeline artifacts:", missing)
    for k, p in REQUIRED_FILES.items():
        print("  -", k, "->", p)
    # Exit so the server doesn't start with missing research artifacts
    sys.exit(1)

if not AUDIO_DIR.exists():
    print("WARNING: Audio directory not found at", AUDIO_DIR, "- audio endpoints will 404 until audio files are added.")

# ---------- Import routers (after checks) ----------
from .api.v1 import sessions, activity, audio, responses, users, lexicon, admin

# ---------- FastAPI app init ----------
app = FastAPI(title="FARM Auditory Training API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# register routers
app.include_router(sessions.router)
app.include_router(activity.router)
app.include_router(audio.router)
app.include_router(responses.router)
app.include_router(users.router)
app.include_router(lexicon.router)
app.include_router(admin.router)

# ---------- Add OpenAPI security so Swagger shows "Authorize" ----------
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version="1.0.0",
        description="FARM Auditory Training API",
        routes=app.routes,
    )
    # define an apiKey header named "Authorization"
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})["APIKeyHeader"] = {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
        "description": "Provide token as: Token <your_token_here>"
    }
    # apply globally
    openapi_schema["security"] = [{"APIKeyHeader": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ---------- Health endpoint ----------
@app.get("/health")
def health():
    return {"status": "ok"}
