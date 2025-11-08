# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# import routers
from .routes.test_routes import router as test_router

app = FastAPI(title="Hearing Project Backend")

# enable CORS for local frontend/dev (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change to your frontend origin(s) for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include API routers
app.include_router(test_router)

@app.get("/")
async def root():
    return {"ok": True, "message": "Hearing project backend running"}
