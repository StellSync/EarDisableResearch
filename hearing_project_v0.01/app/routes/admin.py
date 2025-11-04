from fastapi import APIRouter, Depends, HTTPException, status
from .. import crud, db
from ..schemas import RowIn
from typing import List
import os
from dotenv import load_dotenv
load_dotenv()

router = APIRouter(prefix="/api/admin", tags=["admin"])

API_KEY = os.getenv("API_KEY", "changeme")

def require_api_key(key: str):
    if key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

@router.post("/load_rows")
async def load_rows(rows: List[RowIn], api_key: str):
    require_api_key(api_key)
    docs = [r.dict() for r in rows]
    n = await crud.insert_rows(docs)
    return {"inserted": n}

@router.get("/docs")
async def get_docs(api_key: str):
    require_api_key(api_key)
    docs = await crud.get_all_docs()
    return docs
