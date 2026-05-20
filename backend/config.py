"""
Central configuration.

All paths are resolved relative to the repository root so the system works
regardless of where it is checked out (Windows D:\raid tool\, Linux sandbox,
or any other location).
"""
from __future__ import annotations
import os
from pathlib import Path

# Repository root = parent of the `backend/` package
ROOT_DIR: Path = Path(__file__).resolve().parent.parent

# Sub-folders
MASTER_DATA_DIR: Path = ROOT_DIR / "master_data"
TEMPLATES_DIR:   Path = ROOT_DIR / "templates"
DOCS_DIR:        Path = ROOT_DIR / "docs"
BACKUP_DIR:      Path = ROOT_DIR / "backup"
LOGS_DIR:        Path = ROOT_DIR / "logs"
SCHEMA_FILE:     Path = ROOT_DIR / "backend" / "models" / "schema.sql"

# Database file path (override via env var RAID_DB_PATH if needed)
DB_PATH: Path = Path(os.environ.get("RAID_DB_PATH", ROOT_DIR / "raid_database.db"))

# Server config
HOST: str = os.environ.get("RAID_HOST", "0.0.0.0")
PORT: int = int(os.environ.get("RAID_PORT", "5000"))
DEBUG: bool = os.environ.get("RAID_DEBUG", "0") == "1"

# Business defaults
DEFAULT_MULTIPLIER_FIRST_OFFENSE: float = 2.0
DEFAULT_MULTIPLIER_REPEAT_OFFENSE: float = 6.0
REPEAT_OFFENSE_THRESHOLD: int = 2          # >= this many prior cases = repeat
DEFAULT_DAYS_SECTION_135: int = 365
ADMIN_FEE_SECTION_3: float = 25.0

# Legal timeline (days from raid date)
TIMELINE_PROVISIONAL_PAYMENT: int = 7
TIMELINE_APPEAL_WINDOW: int = 15
TIMELINE_SECTION_3_DISPATCH: int = 45
TIMELINE_SECTION_5_DISPATCH: int = 90

# Slab boundaries (default; rate_master can override)
DEFAULT_SLAB_BOUNDARIES = [(0, 100), (101, 200), (201, None)]

# Ensure runtime folders exist
for _dir in (MASTER_DATA_DIR, TEMPLATES_DIR, DOCS_DIR, BACKUP_DIR, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
