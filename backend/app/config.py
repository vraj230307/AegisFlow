import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    PROJECT_NAME: str = "AegisFlow - Autonomous Self-Healing Pipeline"
    VERSION: str = "4.0.0"
    TRACK: str = "HACK-O-OCTO 4.0 - PS01"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEFAULT_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    CORS_ORIGINS: list[str] = ["*"]

settings = Settings()
