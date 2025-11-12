# simple token auth for development
import secrets
from fastapi import HTTPException, Header

# In-memory token store (development). For production, store tokens + expiry in DB.
TOKENS = {}  # token -> user_id

def create_token(user_id: str):
    token = secrets.token_hex(16)
    TOKENS[token] = user_id
    return token

def verify_token(authorization: str = Header(None)):
    # Expect header: Authorization: Token <token>
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "token":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = parts[1]
    if token not in TOKENS:
        raise HTTPException(status_code=401, detail="Invalid token")
    return TOKENS[token]
