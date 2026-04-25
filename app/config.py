from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "nexus_metrotwin.db"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

SESSION_COOKIE = "nexus_metrotwin_session"
SESSION_SECRET = os.getenv(
    "NEXUS_SESSION_SECRET",
    "nexus-metrotwin-demo-secret-change-me",
)
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12
PASSWORD_HASH_ROUNDS = 210_000

