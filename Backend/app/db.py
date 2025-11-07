import os
import json
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

# Load env vars
env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    load_dotenv(env_path)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "farm_auditory")

def get_mongo():
    """Return MongoDB client connected to Atlas or fallback JSON file."""
    if MONGO_URI:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            client.server_info()
            print(" Connected to MongoDB Atlas successfully!")
            return client[DB_NAME]
        except Exception as e:
            print(" MongoDB connection failed:", e)

    # Fallback to JSON-based mock DB if Atlas is unreachable
    path = Path(__file__).parent / "data" / "db_fallback.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({
            "users": [], "sessions": [], "lexicon": [],
            "audio": [], "responses": [], "analytics": []
        }, ensure_ascii=False), encoding="utf-8")

    class JSONDB:
        def __init__(self, p): self.path = p
        def _read(self): return json.loads(self.path.read_text(encoding="utf-8"))
        def _write(self, d): self.path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        def collection(self, name):
            db = self
            class Coll:
                def __init__(self, db, n): self.db = db; self.n = n
                def insert_one(self, doc):
                    d = db._read(); d.setdefault(self.n, []).append(doc); db._write(d)
                def find(self, q=None): return db._read().get(self.n, [])
                def find_one(self, q):
                    for it in db._read().get(self.n, []):
                        if all(it.get(k)==v for k,v in (q or {}).items()): return it
                    return None
            return Coll(db, name)
    print(" Using JSON fallback DB (Mongo unavailable).")
    return JSONDB(path)
