from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TempMailbox:
    """A temporary mailbox bound to one registration attempt."""

    email: str
    provider: str
    token: str = ""
    api_base: str = ""
    password: str = ""


@dataclass(frozen=True)
class OAuthStart:
    """The state needed to complete a PKCE OAuth flow."""

    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str


@dataclass(frozen=True)
class RegistrationResult:
    """Outcome of a successful registration attempt."""

    token_json: str
    password: str
