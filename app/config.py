"""Filesystem paths and app-wide constants.

The `data/` directory holds everything local and user-specific: the SQLite
database, the global CV, per-company letters, and (later) the Graph token
cache. It is created on import so the app can boot on a fresh checkout.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "internship_finder.db"

WEB_DIR = BASE_DIR / "app" / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
