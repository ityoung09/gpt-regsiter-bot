from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any, Mapping, Protocol

from gpt_register_bot.domain.models import OAuthStart, TempMailbox


class HttpResponse(Protocol):
    """Minimal response contract shared by all HTTP adapters."""

    status_code: int
    text: str
    headers: Mapping[str, str]

    def json(self) -> Any: ...


class HttpSession(Protocol):
    """A cookie-retaining HTTP session bound to one proxy/fingerprint."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 15,
        allow_redirects: bool = True,
    ) -> HttpResponse: ...

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        json: Any = None,
        timeout: float = 15,
    ) -> HttpResponse: ...

    def cookie(self, name: str) -> str | None: ...


class HttpClient(Protocol):
    """Factory for sessions plus a one-off, cookie-less request."""

    def open_session(self, *, proxy: str | None, impersonate: str) -> HttpSession: ...

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        json: Any = None,
        proxy: str | None = None,
        impersonate: str | None = None,
        timeout: float = 15,
        allow_redirects: bool = True,
    ) -> HttpResponse: ...


class MailProvider(Protocol):
    """Strategy for a temporary-mailbox provider (e.g. Mail.tm)."""

    key: str

    def create_mailbox(
        self, *, proxy: str | None, thread_id: int, stop_event: Event | None
    ) -> TempMailbox | None: ...

    def poll_code(
        self,
        mailbox: TempMailbox,
        *,
        proxy: str | None,
        thread_id: int,
        stop_event: Event | None,
    ) -> str: ...


class OAuthProvider(Protocol):
    """Drives the PKCE authorization-code flow."""

    def start(self) -> OAuthStart: ...

    def exchange(
        self, *, callback_url: str, code_verifier: str, expected_state: str
    ) -> str: ...


class CpaClient(Protocol):
    """Uploads a token file to the CPA management platform."""

    def upload(
        self,
        filepath: str,
        cpa_url: str,
        cpa_token: str,
        proxy: str | None,
        thread_id: int,
    ) -> None: ...


class TokenRepository(Protocol):
    """Persists registration artifacts and returns the token file path."""

    def persist(self, token_json: str, password: str, *, thread_id: int) -> Path: ...

