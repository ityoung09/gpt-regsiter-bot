from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import threading
import time
import traceback
from pathlib import Path
from threading import Event
from types import ModuleType
from typing import Callable

from gpt_register_bot.web.config import PROJECT_ROOT


class SourceRuntimeError(RuntimeError):
    """Raised when source runtime cannot be loaded or executed."""


class _LogForwarder(io.TextIOBase):
    """
    Forward stdout/stderr to LogBuffer line by line.

    Running source.py in-process avoids Windows code-page mismatch and prevents
    Chinese logs from becoming garbled.
    """

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buffer = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buffer += s.replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self._emit(line)
        return len(s)

    def flush(self) -> None:
        if self._buffer:
            self._emit(self._buffer)
            self._buffer = ""


class SourceRuntimeService:
    """Single-run adapter for source.py business logic."""

    def __init__(self, source_path: Path, log: Callable[[str], None]) -> None:
        self._source_path = source_path
        self._log = log
        self._module: ModuleType | None = None
        self._module_lock = threading.RLock()

    def ensure_ready(self) -> None:
        self._ensure_module_loaded()

    def _ensure_module_loaded(self) -> ModuleType:
        with self._module_lock:
            if self._module is not None:
                return self._module

            if not self._source_path.exists():
                raise SourceRuntimeError(f"source script not found: {self._source_path}")

            try:
                spec = importlib.util.spec_from_file_location(
                    "gpt_register_bot_source_runtime", str(self._source_path)
                )
                if spec is None or spec.loader is None:
                    raise SourceRuntimeError("cannot build module spec for source.py")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._module = module
                return module
            except Exception as exc:  # pragma: no cover - runtime environment dependent
                raise SourceRuntimeError(f"load source.py failed: {exc}") from exc

    def _invoke_with_redirect(self, func: Callable[..., object], *args: object) -> object:
        stream = _LogForwarder(self._log)
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            try:
                return func(*args)
            finally:
                stream.flush()

    @staticmethod
    def _safe_filename(value: str) -> str:
        safe = value.replace("@", "_")
        for ch in ('\\', "/", ":", "*", "?", '"', "<", ">", "|"):
            safe = safe.replace(ch, "_")
        return safe

    def _persist_outputs(self, token_json: str, password: str, thread_id: int) -> Path:
        output_dir = PROJECT_ROOT / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            token_payload = json.loads(token_json)
        except Exception:
            token_payload = {}

        raw_email = str(token_payload.get("email") or f"unknown_{thread_id}")
        refresh_token = str(token_payload.get("refresh_token") or "")
        fname_email = self._safe_filename(raw_email)

        token_path = output_dir / f"token_{fname_email}_{int(time.time())}.json"
        token_path.write_text(token_json, encoding="utf-8")

        accounts_file = output_dir / "accounts.txt"
        with accounts_file.open("a", encoding="utf-8", newline="\n") as fp:
            fp.write(f"{raw_email}----{password}----{refresh_token}\n")

        return token_path

    def run_once(
        self,
        *,
        thread_id: int,
        run_no: int,
        total_runs: int,
        cpa_url: str | None,
        cpa_token: str | None,
        stop_event: Event,
    ) -> bool:
        if stop_event.is_set():
            self._log(f"[task] run {run_no}/{total_runs} skipped: stop requested")
            return False

        module = self._ensure_module_loaded()
        # Never block web worker on interactive input().
        setattr(module.builtins, "yasal_bypass_ip_choice", True)

        self._log(f"[task] run {run_no}/{total_runs} start (provider=mailtm)")

        try:
            result = self._invoke_with_redirect(module.run, None, "mailtm", thread_id)
        except Exception as exc:  # pragma: no cover - external API dependent
            self._log(f"[error] run {run_no}/{total_runs} crashed: {exc}")
            self._log(traceback.format_exc().rstrip("\n"))
            return False

        if not result:
            self._log(f"[warn] run {run_no}/{total_runs} failed")
            return False

        token_json, password = result
        token_path = self._persist_outputs(token_json, password, thread_id)
        self._log(f"[task] run {run_no}/{total_runs} saved: {token_path}")

        if cpa_url and cpa_token and not stop_event.is_set():
            try:
                self._invoke_with_redirect(
                    module._upload_to_cpa,  # noqa: SLF001 - legacy source API
                    str(token_path),
                    cpa_url,
                    cpa_token,
                    None,
                    thread_id,
                )
            except Exception as exc:  # pragma: no cover - external API dependent
                self._log(f"[warn] run {run_no}/{total_runs} CPA upload failed: {exc}")
        elif cpa_url or cpa_token:
            self._log("[warn] cpa_url and cpa_token must be provided together, skip upload")

        return True
