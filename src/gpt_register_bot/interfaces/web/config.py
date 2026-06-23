from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
UI_DIR = PACKAGE_ROOT / "ui"
STATIC_DIR = UI_DIR / "static"
TEMPLATE_DIR = UI_DIR / "templates"
