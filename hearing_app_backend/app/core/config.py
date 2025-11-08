# app/core/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        self.MONGO_URI = os.getenv(
            "MONGO_URI",
            "mongodb+srv://HearingUser:hearing1234@hearingcluster.z3ya4it.mongodb.net/?retryWrites=true&w=majority&appName=hearingCluster"
        )
        self.DB_NAME = os.getenv("DB_NAME", "farm_auditory")
        self.DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        self.APP_NAME = os.getenv("APP_NAME", "hearing_app_backend")

settings = Settings()
