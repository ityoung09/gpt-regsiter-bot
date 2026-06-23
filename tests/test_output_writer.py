from __future__ import annotations

import json
from pathlib import Path

from gpt_register_bot.infrastructure.persistence import FileTokenRepository


def test_file_token_repository_persist(tmp_path: Path) -> None:
    repository = FileTokenRepository(tmp_path)
    token_json = json.dumps({"email": "test@mail.tm", "refresh_token": "rt-1"})
    path = repository.persist(token_json, "secret-pass", thread_id=1)

    assert path.exists()
    assert path.read_text(encoding="utf-8") == token_json

    accounts = (tmp_path / "accounts.txt").read_text(encoding="utf-8")
    assert accounts == "test@mail.tm----secret-pass----rt-1\n"
