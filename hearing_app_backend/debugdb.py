# debug_db.py
import importlib
import app.core as core

print("app.core.__file__:", core.__file__)
print("settings present:", hasattr(core, "settings"))
print("db object type:", type(core.db))
print("db.client present:", getattr(core.db, "client", None))
print("db.words present:", getattr(core.db, "words", None))
