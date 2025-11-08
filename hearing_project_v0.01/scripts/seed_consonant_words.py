# scripts/seed_consonant_words.py
import os
import json
import asyncio
from pathlib import Path
from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient

# MongoDB connection settings
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority")
DB_NAME = os.getenv("DB_NAME", "hearingdb")
COLLECTION_NAME = "consonant_words"  # New collection for consonant words

# Input JSON file path (relative to this script)
# THIS_DIR = Path(__file__).parent
# ROOT_DIR = THIS_DIR.parent.parent
INPUT_JSON = "hearing_project_v0.01/scripts/data/wiyanjana_words_consonants_firstletter.json"

async def seed_consonant_words():
    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    try:
        # Read the JSON file
        if not INPUT_JSON.exists():
            print(f"Error: Input file not found: {INPUT_JSON}")
            return
            
        with INPUT_JSON.open('r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Drop existing collection
        await collection.drop()
        print(f"Dropped existing {COLLECTION_NAME} collection")
        
        # Prepare documents for insertion
        documents = []
        for item in data:
            doc = {
                "section": item["section"],
                "index": item["index"],
                "sinhala_word": item["sinhala_word"],
                "singlish": item["singlish_word"],
                "changing_consonant": {
                    "character": item["changing_consonant_character"],
                    "name": item["changing_consonant_name"]
                },
                "audio_path": item["audio_path"],
                "audio_url": None  # Will be set by the admin API when audio is uploaded
            }
            documents.append(doc)
            
        # Create indexes for efficient querying
        await collection.create_index([("section", 1), ("index", 1)])
        await collection.create_index([("changing_consonant.character", 1)])
        await collection.create_index([("changing_consonant.name", 1)])
        
        # Insert documents
        result = await collection.insert_many(documents)
        print(f"Successfully inserted {len(result.inserted_ids)} consonant word documents")
        
        # Print sample document
        print("\nSample document structure:")
        sample = await collection.find_one()
        # Use json_util.dumps instead of json.dumps to handle MongoDB types like ObjectId
        print(json_util.dumps(sample, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"Error seeding consonant words: {e}")
    finally:
        # Close MongoDB connection
        client.close()

if __name__ == "__main__":
    # Run the async function
    asyncio.run(seed_consonant_words())