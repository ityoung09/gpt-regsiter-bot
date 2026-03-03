from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PACKAGE_ROOT.parent.parent
PROJECT_ROOT = SRC_ROOT.parent
SOURCE_SCRIPT_PATH = PROJECT_ROOT / "source.py"

UI_DIR = PACKAGE_ROOT / "ui"
STATIC_DIR = UI_DIR / "static"
TEMPLATE_DIR = UI_DIR / "templates"

MAX_LOG_LINES = 2500
MAX_LOG_TAIL = 600
