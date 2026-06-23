from __future__ import annotations

import logging
import socket
from typing import Any

from curl_cffi import requests

from gpt_register_bot.domain.ports import HttpResponse, HttpSession

logger = logging.getLogger(__name__)

_LOCAL_PROXY_PORTS = [7890, 1080, 10809, 10808, 8888]


def detect_local_proxy() -> str | None:
    """Probe common local proxy ports and return the first that is alive."""
    for port in _LOCAL_PROXY_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                logger.info(
                    "[Yasal 灵光一闪~] 探测到本地代理端口 %s 存活，"
                    "Yasal自动帮你连上隧道穿透封锁啦！",
                    port,
                )
                return f"http://127.0.0.1:{port}"
    return None


def _proxies(proxy: str | None) -> dict[str, str] | None:
    return {"http": proxy, "https": proxy} if proxy else None


class _CurlSession:
    """Adapts a ``curl_cffi`` session to the :class:`HttpSession` port."""

    def __init__(self, session: Any) -> None:
        self._session = session

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 15,
        allow_redirects: bool = True,
    ) -> HttpResponse:
        return self._session.get(
            url, headers=headers, timeout=timeout, allow_redirects=allow_redirects
        )

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        json: Any = None,
        timeout: float = 15,
    ) -> HttpResponse:
        return self._session.post(
            url, headers=headers, data=data, json=json, timeout=timeout
        )

    def cookie(self, name: str) -> str | None:
        return self._session.cookies.get(name)


class CurlHttpClient:
    """:class:`HttpClient` implementation backed by ``curl_cffi`` (TLS impersonation)."""

    def open_session(self, *, proxy: str | None, impersonate: str) -> HttpSession:
        session = requests.Session(proxies=_proxies(proxy), impersonate=impersonate)
        return _CurlSession(session)

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
    ) -> HttpResponse:
        return requests.request(
            method,
            url,
            headers=headers,
            data=data,
            json=json,
            proxies=_proxies(proxy),
            impersonate=impersonate,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )
