from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

async def increment_verification_counts(db: AsyncIOMotorDatabase, user_id: str, word_id: str, selected_key: str):
    """Increment verification-related counters for the word."""
    # Update the word verification counts
    update_doc = {
        "$inc": {
            f"verification_stats.{selected_key}_count": 1,
            "verification_stats.total_verifications": 1
        }
    }
    await db["consonant_words"].update_one({"_id": word_id}, update_doc)
    
    # Update user's overall verification stats
    update_doc = {
        "$inc": {
            f"verification_stats.{selected_key}_count": 1,
            "verification_stats.total_verifications": 1
        }
    }
    await db["users"].update_one({"user_id": user_id}, update_doc, upsert=True)

async def update_verification_status_and_counts(db: AsyncIOMotorDatabase, user_id: str, word_id: str):
    """Update verification status and completion counts for a word."""
    # Get current verification stats
    word = await db["consonant_words"].find_one({"_id": word_id})
    if not word:
        return
    
    stats = word.get("verification_stats", {})
    total = stats.get("total_verifications", 0)
    
    # Update verification status if enough verifications
    if total >= 3:  # Threshold for verification completion
        await db["consonant_words"].update_one(
            {"_id": word_id},
            {"$set": {"verification_completed": True}}
        )
        
    # Update user completion counts
    await db["users"].update_one(
        {"user_id": user_id},
        {
            "$inc": {"verifications_completed": 1},
            "$set": {"last_verification_timestamp": datetime.utcnow()}
        },
        upsert=True
    )