from __future__ import annotations

import logging
import random
import re
import secrets
import threading
import time
from typing import Any

from gpt_register_bot.domain.models import TempMailbox
from gpt_register_bot.domain.ports import HttpClient, MailProvider

logger = logging.getLogger(__name__)

MAILTM_BASE = "https://api.mail.tm"
_IMPERSONATE = "chrome"
_CODE_REGEX = r"(?<!\d)(\d{6})(?!\d)"


def _interruptible_sleep(seconds: float, stop_event: threading.Event | None) -> bool:
    """Sleep up to ``seconds``, returning True if a stop was requested."""
    if stop_event is not None:
        return stop_event.wait(seconds)
    time.sleep(seconds)
    return False


def _headers(*, token: str = "", use_json: bool = False) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if use_json:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class MailTmProvider:
    """Mail.tm (Hydra API) temporary-mailbox provider."""

    key = "mailtm"

    def __init__(self, http: HttpClient, *, api_base: str = MAILTM_BASE) -> None:
        self._http = http
        self._api_base = api_base

    def _domains(self, proxy: str | None) -> list[str]:
        resp = self._http.request(
            "GET",
            f"{self._api_base}/domains",
            headers=_headers(),
            proxy=proxy,
            impersonate=_IMPERSONATE,
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"获取域名失败，状态码: {resp.status_code}")

        data = resp.json()
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("hydra:member") or data.get("items") or []
        else:
            items = []

        domains: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "").strip()
            is_active = item.get("isActive", True)
            is_private = item.get("isPrivate", False)
            if domain and is_active and not is_private:
                domains.append(domain)
        return domains

    def create_mailbox(
        self, *, proxy: str | None, thread_id: int, stop_event: threading.Event | None
    ) -> TempMailbox | None:
        try:
            domains = self._domains(proxy)
            if not domains:
                logger.warning("[线程 %s] [Warn] Mail.tm 没有可用域名", thread_id)
                return None

            for _ in range(5):
                if stop_event is not None and stop_event.is_set():
                    logger.info("[线程 %s] [*] 收到停止信号，停止创建临时邮箱", thread_id)
                    return None
                local = f"oc{secrets.token_hex(5)}"
                domain = random.choice(domains)
                email = f"{local}@{domain}"
                password = secrets.token_urlsafe(18)

                create_resp = self._http.request(
                    "POST",
                    f"{self._api_base}/accounts",
                    headers=_headers(use_json=True),
                    json={"address": email, "password": password},
                    proxy=proxy,
                    impersonate=_IMPERSONATE,
                    timeout=15,
                )
                if create_resp.status_code not in (200, 201):
                    continue

                token_resp = self._http.request(
                    "POST",
                    f"{self._api_base}/token",
                    headers=_headers(use_json=True),
                    json={"address": email, "password": password},
                    proxy=proxy,
                    impersonate=_IMPERSONATE,
                    timeout=15,
                )
                if token_resp.status_code == 200:
                    token = str(token_resp.json().get("token") or "").strip()
                    if token:
                        logger.info(
                            "[线程 %s] [Yasal 的飞吻~] 主人~我已经成功帮你把这个线程绑定到"
                            "临时邮箱啦: mailtm，准备开始为你榨取账号咯~",
                            thread_id,
                        )
                        return TempMailbox(
                            email=email,
                            provider=self.key,
                            token=token,
                            api_base=self._api_base,
                            password=password,
                        )

            logger.warning(
                "[线程 %s] [Warn] Mail.tm 邮箱创建成功但获取 Token 失败", thread_id
            )
            return None
        except Exception as exc:
            logger.warning("[线程 %s] [Warn] 请求 Mail.tm API 出错: %s", thread_id, exc)
            return None

    def poll_code(
        self,
        mailbox: TempMailbox,
        *,
        proxy: str | None,
        thread_id: int,
        stop_event: threading.Event | None,
    ) -> str:
        if not mailbox.token:
            logger.warning(
                "[线程 %s] [Yasal 慌乱...] 诶？mailtm 的 token 怎么是空的呀，"
                "Yasal没法读取邮件了呜呜呜...",
                thread_id,
            )
            return ""

        url_list = f"{mailbox.api_base}/messages"
        seen_ids: set[str] = set()

        logger.info("[线程 %s] [*] 正在等待邮箱 %s 的验证码...", thread_id, mailbox.email)

        for attempt in range(40):
            if stop_event is not None and stop_event.is_set():
                logger.info("[线程 %s] [*] 收到停止信号，停止等待验证码", thread_id)
                return ""
            logger.debug("[线程 %s] [*] 第 %s 次轮询验证码...", thread_id, attempt + 1)
            try:
                resp = self._http.request(
                    "GET",
                    url_list,
                    headers=_headers(token=mailbox.token),
                    proxy=proxy,
                    impersonate=_IMPERSONATE,
                    timeout=15,
                )
                if resp.status_code != 200:
                    if _interruptible_sleep(3, stop_event):
                        return ""
                    continue

                code = self._scan_messages(
                    resp.json(), mailbox, proxy, thread_id, seen_ids
                )
                if code:
                    return code
            except Exception:
                pass
            if _interruptible_sleep(3, stop_event):
                return ""

        logger.warning(
            "[线程 %s] [Yasal 嘟嘴...] 讨厌，等了半天都没有收到验证码，"
            "一定是网络在欺负Yasal...",
            thread_id,
        )
        return ""

    def _scan_messages(
        self,
        data: Any,
        mailbox: TempMailbox,
        proxy: str | None,
        thread_id: int,
        seen_ids: set[str],
    ) -> str:
        if isinstance(data, list):
            messages = data
        elif isinstance(data, dict):
            messages = data.get("hydra:member") or data.get("messages") or []
        else:
            messages = []

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            msg_id = str(msg.get("id") or "").strip()
            if not msg_id or msg_id in seen_ids:
                continue

            read_resp = self._http.request(
                "GET",
                f"{mailbox.api_base}/messages/{msg_id}",
                headers=_headers(token=mailbox.token),
                proxy=proxy,
                impersonate=_IMPERSONATE,
                timeout=15,
            )
            if read_resp.status_code != 200:
                continue
            seen_ids.add(msg_id)

            mail_data = read_resp.json()
            sender = str(((mail_data.get("from") or {}).get("address") or "")).lower()
            subject = str(mail_data.get("subject") or "")
            intro = str(mail_data.get("intro") or "")
            text = str(mail_data.get("text") or "")
            html = mail_data.get("html") or ""
            if isinstance(html, list):
                html = "\n".join(str(x) for x in html)
            content = "\n".join([subject, intro, text, str(html)])

            if "openai" not in sender and "openai" not in content.lower():
                continue

            match = re.search(_CODE_REGEX, content)
            if match:
                logger.info(
                    "[线程 %s] [Yasal 尖叫~] 啊啊啊抓到啦！验证码是这个: %s！快夸我快夸我~",
                    thread_id,
                    match.group(1),
                )
                return match.group(1)
        return ""


# --- Strategy registry -------------------------------------------------------

_REGISTRY: dict[str, type[MailProvider]] = {MailTmProvider.key: MailTmProvider}


def build_mail_provider(provider_key: str, http: HttpClient) -> MailProvider | None:
    """Resolve a :class:`MailProvider` by key, or None if unknown."""
    provider_cls = _REGISTRY.get(provider_key)
    if provider_cls is None:
        return None
    return provider_cls(http)


def available_providers() -> list[str]:
    return sorted(_REGISTRY)
