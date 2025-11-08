# scripts/seed_words.py
import asyncio
import uuid
import os
import sys
import pathlib

# Ensure package root is on sys.path so `from app.core...` works when running
# this script directly (e.g. `python scripts/seed_words.py`).
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import db

SAMPLE_WORDS = [
    {"section":"ක්‍රියාකාරකම-01", "index":"01", "sinhala_word":"පස්", "singlish":"ps", "main_vowel_name":"a", "audio_path":"swara_audio_cloud/ක්‍රියාකාරකම-01/01_පස්_ps.mp3"},
    {"section":"ක්‍රියාකාරකම-01", "index":"01", "sinhala_word":"පුස්", "singlish":"pus", "main_vowel_name":"u", "audio_path":"swara_audio_cloud/ක්‍රියාකාරකම-01/01_පුස්_pus.mp3"},
    {"section":"ක්‍රියාකාරකම-01", "index":"08", "sinhala_word":"කේජු", "singlish":"keeju", "main_vowel_name":"ee", "audio_path":"swara_audio_cloud/ක්‍රියාකාරකම-01/08_කේජු_keeju.mp3"},
    {"section":"ක්‍රියාකාරකම-02", "index":"09", "sinhala_word":"ගුල", "singlish":"gul", "main_vowel_name":"u", "audio_path":"swara_audio_cloud/ක්‍රියාකාරකම-02/09_ගුල_gul.mp3"},
    {"section":"ක්‍රියාකාරකම-01", "index":"10", "sinhala_word":"බිදිති", "singlish":"biditi", "main_vowel_name":"i", "audio_path":"swara_audio_cloud/ක්‍රියාකාරකම-01/10_බිදිති_biditi.mp3"},
    {"section":"ක්‍රියාකාරකම-01", "index":"11", "sinhala_word":"කෝල්", "singlish":"kool", "main_vowel_name":"oo", "audio_path":"swara_audio_cloud/ක්‍රියාකාරකම-01/11_කෝල්_kool.mp3"},
    {"section":"ක්‍රියාකාරකම-01", "index":"13", "sinhala_word":"බීම", "singlish":"biim", "main_vowel_name":"ii", "audio_path":"swara_audio_cloud/ක්‍රියාකාරකම-01/13_බීම_biim.mp3"},
]

async def seed():
    docs = []
    for w in SAMPLE_WORDS:
        docs.append({**w, "_id": str(uuid.uuid4())})
    # remove existing dev docs (CAREFUL in prod)
    await db.words.delete_many({})
    await db.words.insert_many(docs)
    print("Inserted", len(docs), "sample words.")

if __name__ == "__main__":
    asyncio.run(seed())
