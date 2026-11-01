"""
Central configuration for DemoToSkill backend.
Loads settings from environment variables and .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent

load_dotenv(ROOT_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
GEMMA_REPAIR_MODEL = os.getenv("GEMMA_REPAIR_MODEL", "gemma-4-31b-it")

MAX_CONCURRENT_GEMMA_CALLS = int(os.getenv("MAX_CONCURRENT_GEMMA_CALLS", "3"))

IMAGE_RESIZE_MAX_WIDTH = int(os.getenv("IMAGE_RESIZE_MAX_WIDTH", "1024"))
IMAGE_JPEG_QUALITY = int(os.getenv("IMAGE_JPEG_QUALITY", "70"))

NETWORK_IDLE_TIMEOUT_MS = int(os.getenv("NETWORK_IDLE_TIMEOUT_MS", "1500"))
POST_ACTION_SETTLE_MS = int(os.getenv("POST_ACTION_SETTLE_MS", "300"))

BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "5173"))
DEMO_APP_PORT = int(os.getenv("DEMO_APP_PORT", "8080"))

DATA_DIR = ROOT_DIR / "data"
SHOTS_DIR = DATA_DIR / "shots"
SPECS_DIR = ROOT_DIR / "specs"
DB_PATH = DATA_DIR / "demotoskill.db"
PROMPTS_DIR = APP_DIR / "prompts"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SHOTS_DIR.mkdir(parents=True, exist_ok=True)
SPECS_DIR.mkdir(parents=True, exist_ok=True)

