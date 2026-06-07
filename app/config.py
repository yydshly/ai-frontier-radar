"""Configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def get_int(key: str, default: int) -> int:
    val = get_env(key)
    return int(val) if val else default


# App
APP_ENV = get_env("APP_ENV", "development")
DATABASE_URL = get_env("DATABASE_URL", "sqlite:///./data/ai_frontier_radar.db")

# LLM
LLM_BASE_URL = get_env("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = get_env("LLM_API_KEY", "replace-me")
LLM_MODEL = get_env("LLM_MODEL", "gpt-4o-mini")

# HTTP
HTTP_TIMEOUT_SECONDS = get_int("HTTP_TIMEOUT_SECONDS", 20)
FETCH_RETRY_COUNT = get_int("FETCH_RETRY_COUNT", 2)
MAX_SOURCE_CHARS = get_int("MAX_SOURCE_CHARS", 60000)
MAX_LLM_INPUT_CHARS = get_int("MAX_LLM_INPUT_CHARS", 30000)
