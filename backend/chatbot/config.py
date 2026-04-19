"""
chatbot/config.py
Load all LLM settings from the backend .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the backend/.env, regardless of the current working directory
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {key}\n"
            f"Please set it in backend/.env and restart the server."
        )
    return value

# Exported settings
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
OPENAI_BASE_URL: str | None = os.getenv("OPENAI_BASE_URL", "").strip() or None
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))
CODE_MAX_TOKENS: int = int(os.getenv("CODE_MAX_TOKENS", "16384"))

# Azure-specific (only used when OPENAI_BASE_URL points to an Azure endpoint)
AZURE_API_VERSION: str = os.getenv("AZURE_API_VERSION", "2024-02-01").strip()
AZURE_DEPLOYMENT: str = os.getenv("AZURE_DEPLOYMENT", OPENAI_MODEL).strip()

# Detect Azure if the base URL contains "openai.azure.com"
IS_AZURE: bool = bool(OPENAI_BASE_URL and "openai.azure.com" in OPENAI_BASE_URL)

# Retry settings
RETRY_MAX_ATTEMPTS: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "4"))
RETRY_MIN_WAIT: int = int(os.getenv("RETRY_MIN_WAIT", "1"))  # seconds
RETRY_MAX_WAIT: int = int(os.getenv("RETRY_MAX_WAIT", "30"))

# Session settings
SESSION_TTL_MINUTES: int = int(os.getenv("SESSION_TTL_MINUTES", "60"))