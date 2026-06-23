from __future__ import annotations

import json
import time
from pathlib import Path


class FileTokenRepository:
    """Persists registration artifacts to disk (token JSON + accounts.txt)."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    @staticmethod
    def safe_filename(value: str) -> str:
        safe = value.replace("@", "_")
        for char in ("\\", "/", ":", "*", "?", '"', "<", ">", "|"):
            safe = safe.replace(char, "_")
        return safe

    def persist(self, token_json: str, password: str, *, thread_id: int) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)

        try:
            token_payload = json.loads(token_json)
        except json.JSONDecodeError:
            token_payload = {}

        raw_email = str(token_payload.get("email") or f"unknown_{thread_id}")
        refresh_token = str(token_payload.get("refresh_token") or "")
        fname_email = self.safe_filename(raw_email)

        token_path = self._output_dir / f"token_{fname_email}_{int(time.time())}.json"
        token_path.write_text(token_json, encoding="utf-8")

        accounts_file = self._output_dir / "accounts.txt"
        with accounts_file.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{raw_email}----{password}----{refresh_token}\n")

        return token_path
