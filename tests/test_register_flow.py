"""Mock integration tests for the RegistrationService HTTP flow.

The new layered design injects an :class:`HttpClient` and an OAuth client, so
these tests drive ``RegistrationService.register_once`` end-to-end against fakes
— no monkeypatching of module globals. The real :class:`MailTmProvider` runs
over the fake HTTP client, so mailbox creation and OTP polling are exercised for
real; only OAuth token exchange (network/urllib) is faked.
"""

from __future__ import annotations

import base64
import json
import threading
from typing import Any, Callable

import pytest

from gpt_register_bot.application.registration_service import RegistrationService
from gpt_register_bot.domain.models import OAuthStart
from gpt_register_bot.infrastructure.mail import MailTmProvider


def _auth_cookie() -> str:
    payload = json.dumps({"workspaces": [{"id": "ws_1"}]}).encode("utf-8")
    segment = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{segment}.signature"


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        text: str = "",
        json_data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._json = {} if json_data is None else json_data
        self.headers = headers or {}

    def json(self) -> Any:
        return self._json


def _default_router(url: str) -> FakeResponse:
    if "cdn-cgi/trace" in url:
        return FakeResponse(text="fl=abc\nip=1.2.3.4\nloc=US\n")
    if url.endswith("/domains"):
        return FakeResponse(
            json_data=[{"domain": "mail.tm", "isActive": True, "isPrivate": False}]
        )
    if url.endswith("/accounts"):
        return FakeResponse(status_code=201)
    if url.endswith("/token"):
        return FakeResponse(json_data={"token": "mt-token"})
    if "sentinel.openai.com" in url:
        return FakeResponse(json_data={"token": "sentinel-token"})
    if "oauth/authorize" in url:
        return FakeResponse()
    if "authorize/continue" in url:
        return FakeResponse()
    if "send-otp" in url:
        return FakeResponse()
    if url.endswith("/messages"):
        return FakeResponse(json_data=[{"id": "m1"}])
    if "/messages/" in url:
        return FakeResponse(
            json_data={
                "from": {"address": "noreply@openai.com"},
                "subject": "Your OpenAI code",
                "text": "Your verification code is 123456",
            }
        )
    if "email-otp/validate" in url:
        return FakeResponse()
    if "workspace/select" in url:
        return FakeResponse(json_data={"continue_url": "https://auth.openai.com/continue"})
    if "create_account" in url:
        return FakeResponse()
    if url.startswith("https://auth.openai.com/continue"):
        return FakeResponse(
            status_code=302,
            headers={"Location": "http://localhost:1455/auth/callback?code=abc&state=xyz"},
        )
    return FakeResponse()


class FakeSession:
    def __init__(self, router: Callable[[str], FakeResponse], calls: list[str]) -> None:
        self._router = router
        self._calls = calls
        self._cookies = {
            "oai-did": "device-xyz",
            "oai-client-auth-session": _auth_cookie(),
        }

    def get(self, url: str, **_: Any) -> FakeResponse:
        self._calls.append(url)
        return self._router(url)

    def post(self, url: str, **_: Any) -> FakeResponse:
        self._calls.append(url)
        return self._router(url)

    def cookie(self, name: str) -> str | None:
        return self._cookies.get(name)


class FakeHttpClient:
    """HttpClient port stand-in; records every requested URL in ``calls``."""

    def __init__(self, router: Callable[[str], FakeResponse]) -> None:
        self._router = router
        self.calls: list[str] = []

    def open_session(self, *, proxy: str | None, impersonate: str) -> FakeSession:
        return FakeSession(self._router, self.calls)

    def request(self, method: str, url: str, **_: Any) -> FakeResponse:
        self.calls.append(url)
        return self._router(url)


class FakeOAuth:
    """OAuth client stand-in: fixed start state, canned token exchange."""

    def __init__(self) -> None:
        self.exchange_kwargs: dict[str, Any] = {}

    def start(self) -> OAuthStart:
        return OAuthStart(
            auth_url="https://auth.openai.com/oauth/authorize?client_id=x",
            state="xyz",
            code_verifier="verifier-123",
            redirect_uri="http://localhost:1455/auth/callback",
        )

    def exchange(self, **kwargs: Any) -> str:
        self.exchange_kwargs = kwargs
        return '{"access_token":"AT","email":"oc@mail.tm"}'


def _make_service(http: FakeHttpClient, oauth: FakeOAuth) -> RegistrationService:
    return RegistrationService(
        http=http,
        provider_factory=lambda key: MailTmProvider(http) if key == "mailtm" else None,
        oauth=oauth,
        repository=object(),  # unused by register_once
        cpa=object(),  # unused by register_once
    )


def test_register_once_happy_path() -> None:
    http = FakeHttpClient(_default_router)
    oauth = FakeOAuth()
    service = _make_service(http, oauth)

    result = service.register_once(
        thread_id=1, proxy="", provider_key="mailtm", non_interactive=True
    )

    assert result is not None
    assert json.loads(result.token_json)["access_token"] == "AT"
    assert result.password  # generated by MailTmProvider

    # The full flow ran: mailbox creation, sentinel, account creation.
    assert any("/domains" in url for url in http.calls)
    assert any("sentinel.openai.com" in url for url in http.calls)
    assert any("create_account" in url for url in http.calls)

    # The redirect-following call site forwarded the right OAuth material.
    assert "code=abc" in oauth.exchange_kwargs["callback_url"]
    assert "state=xyz" in oauth.exchange_kwargs["callback_url"]
    assert oauth.exchange_kwargs["code_verifier"] == "verifier-123"
    assert oauth.exchange_kwargs["expected_state"] == "xyz"


def test_register_once_unknown_provider() -> None:
    http = FakeHttpClient(_default_router)
    service = _make_service(http, FakeOAuth())

    result = service.register_once(
        thread_id=1, proxy="", provider_key="nope", non_interactive=True
    )

    assert result is None
    assert http.calls == []  # bailed before any HTTP


def test_register_once_aborts_when_sentinel_blocks() -> None:
    def router(url: str) -> FakeResponse:
        if "sentinel.openai.com" in url:
            return FakeResponse(status_code=403, text="blocked")
        return _default_router(url)

    http = FakeHttpClient(router)
    service = _make_service(http, FakeOAuth())

    result = service.register_once(
        thread_id=1, proxy="", provider_key="mailtm", non_interactive=True
    )

    assert result is None
    assert any("sentinel.openai.com" in url for url in http.calls)
    assert not any("authorize/continue" in url for url in http.calls)
    assert not any("create_account" in url for url in http.calls)


def test_register_once_stops_early_when_stop_event_set() -> None:
    http = FakeHttpClient(_default_router)
    service = _make_service(http, FakeOAuth())
    stop_event = threading.Event()
    stop_event.set()

    result = service.register_once(
        thread_id=1,
        proxy="",
        provider_key="mailtm",
        non_interactive=True,
        stop_event=stop_event,
    )

    assert result is None
    # Stop is honored before mailbox creation; only the IP trace probe ran.
    assert not any("/domains" in url for url in http.calls)
    assert not any("sentinel.openai.com" in url for url in http.calls)


def test_mailtm_provider_stops_before_creating_account() -> None:
    http = FakeHttpClient(_default_router)
    provider = MailTmProvider(http)
    stop_event = threading.Event()
    stop_event.set()

    mailbox = provider.create_mailbox(proxy=None, thread_id=1, stop_event=stop_event)

    assert mailbox is None
    assert not any("/accounts" in url for url in http.calls)
