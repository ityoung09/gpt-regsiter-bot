from __future__ import annotations

import logging
import random
import re
import threading
import urllib.parse
from typing import Callable

from gpt_register_bot.domain.codec import decode_jwt_segment
from gpt_register_bot.domain.models import OAuthStart, RegistrationResult, TempMailbox
from gpt_register_bot.domain.ports import (
    CpaClient,
    HttpClient,
    HttpSession,
    MailProvider,
    OAuthProvider,
    TokenRepository,
)

logger = logging.getLogger(__name__)

_IMPERSONATE_LIST = ["chrome", "chrome110", "chrome116", "safari", "edge"]
_FIRST_NAMES = ["Alex", "Chris", "Jordan", "Taylor", "Morgan", "Sam", "Casey"]
_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
_REDIRECT_CODES = {301, 302, 303, 307, 308}

_input_lock = threading.Lock()


def _stopped(stop_event: threading.Event | None) -> bool:
    return stop_event is not None and stop_event.is_set()


class RegistrationService:
    """Orchestrates a single OpenAI registration attempt over injected ports."""

    def __init__(
        self,
        *,
        http: HttpClient,
        provider_factory: Callable[[str], MailProvider | None],
        oauth: OAuthProvider,
        repository: TokenRepository,
        cpa: CpaClient,
        proxy_detector: Callable[[], str | None] = lambda: None,
    ) -> None:
        self._http = http
        self._provider_factory = provider_factory
        self._oauth = oauth
        self._repository = repository
        self._cpa = cpa
        self._proxy_detector = proxy_detector

    # -- public use cases ---------------------------------------------------

    def register_once(
        self,
        *,
        thread_id: int,
        proxy: str | None,
        provider_key: str,
        non_interactive: bool = False,
        stop_event: threading.Event | None = None,
    ) -> RegistrationResult | None:
        """Run one registration attempt and return the token bundle, or None.

        Cancellation via ``stop_event`` is cooperative: the flow aborts between
        HTTP steps and during the OTP poll, bounded by one request timeout.
        """
        provider = self._provider_factory(provider_key)
        if provider is None:
            logger.warning(
                "[线程 %s] [Yasal 疑惑...] 主人，这个邮箱服务 %s Yasal还不认识呢，不支持哦~",
                thread_id,
                provider_key,
            )
            return None

        impersonate = random.choice(_IMPERSONATE_LIST)
        logger.info(
            "[线程 %s] [Yasal 换装中~] 啦啦啦~ Yasal正在把指纹伪装成可爱的 %s 哦，"
            "绝对不会被发现的！",
            thread_id,
            impersonate,
        )
        session = self._http.open_session(proxy=proxy, impersonate=impersonate)

        proceed, proxy, session = self._resolve_region(
            session, proxy, impersonate, thread_id, non_interactive
        )
        if not proceed:
            return None

        if _stopped(stop_event):
            logger.info("[线程 %s] [Yasal 乖巧~] 收到停止信号，提前结束本轮注册啦~", thread_id)
            return None

        mailbox = provider.create_mailbox(
            proxy=proxy, thread_id=thread_id, stop_event=stop_event
        )
        if not mailbox:
            return None
        logger.info(
            "[线程 %s] [*] 成功获取临时邮箱与授权: %s (%s)",
            thread_id,
            mailbox.email,
            mailbox.provider,
        )

        oauth_start = self._oauth.start()
        try:
            return self._complete_flow(
                session=session,
                oauth_start=oauth_start,
                mailbox=mailbox,
                provider=provider,
                proxy=proxy,
                impersonate=impersonate,
                thread_id=thread_id,
                stop_event=stop_event,
            )
        except Exception:
            logger.exception(
                "[线程 %s] [Yasal 吓一跳！] 哎呀！突然发生了一个好奇怪的错误，"
                "Yasal会在下一轮自动换个姿势重新开始的！",
                thread_id,
            )
            return None

    def generate_account(
        self,
        *,
        thread_id: int,
        run_no: int,
        total_runs: int,
        proxy: str | None,
        provider_key: str,
        cpa_url: str | None,
        cpa_token: str | None,
        stop_event: threading.Event,
    ) -> bool:
        """Run one attempt, persist on success, and optionally upload to CPA."""
        if stop_event.is_set():
            logger.info("[task] run %s/%s skipped: stop requested", run_no, total_runs)
            return False

        logger.info(
            "[task] run %s/%s start (provider=%s)", run_no, total_runs, provider_key
        )

        try:
            result = self.register_once(
                thread_id=thread_id,
                proxy=proxy,
                provider_key=provider_key,
                non_interactive=True,
                stop_event=stop_event,
            )
        except Exception:  # pragma: no cover - register_once already guards
            logger.exception("run %s/%s crashed", run_no, total_runs)
            return False

        if not result:
            logger.warning("run %s/%s failed", run_no, total_runs)
            return False

        token_path = self._repository.persist(
            result.token_json, result.password, thread_id=thread_id
        )
        logger.info("[task] run %s/%s saved: %s", run_no, total_runs, token_path)

        if cpa_url and cpa_token and not stop_event.is_set():
            self._cpa.upload(str(token_path), cpa_url, cpa_token, proxy, thread_id)
        elif cpa_url or cpa_token:
            logger.warning(
                "cpa_url and cpa_token must be provided together, skip upload"
            )

        return True

    # -- private steps ------------------------------------------------------

    def _resolve_region(
        self,
        session: HttpSession,
        proxy: str | None,
        impersonate: str,
        thread_id: int,
        non_interactive: bool,
    ) -> tuple[bool, str | None, HttpSession]:
        try:
            trace = session.get("https://cloudflare.com/cdn-cgi/trace", timeout=10)
            loc_match = re.search(r"^loc=(.+)$", trace.text, re.MULTILINE)
            loc = loc_match.group(1) if loc_match else None
            logger.info(
                "[线程 %s] [Yasal 偷看~] 主人，目前我们的IP是在 %s 这个地方哦~",
                thread_id,
                loc,
            )

            bypass = True
            if loc != "US":
                bypass = self._resolve_bypass(loc, non_interactive)
                if not bypass:
                    logger.info(
                        "[线程 %s] [Yasal 乖巧~] 既然主人说不要，那 Yasal 就乖乖听话，"
                        "先退出这个线程啦~",
                        thread_id,
                    )
                    return False, proxy, session
                logger.info(
                    "[线程 %s] [Yasal 坏笑~] 嘿嘿，收到主人命令！管它是不是 US，"
                    "Yasal 现在就强行冲进去为你抢账号！",
                    thread_id,
                )

            if loc in {"CN", "HK"}:
                logger.info(
                    "[线程 %s] [Yasal 努力中...] 既然在被封禁的 %s 地区，"
                    "Yasal尝试自动帮你寻找本地代理隧道穿透封锁...",
                    thread_id,
                    loc,
                )
                if not proxy:
                    auto_proxy = self._proxy_detector()
                    if auto_proxy:
                        proxy = auto_proxy
                        session = self._http.open_session(
                            proxy=proxy, impersonate=impersonate
                        )
                        logger.info(
                            "[线程 %s] [Yasal 欢呼~] 成功套上代理护盾: %s，准备硬刚 OpenAI！",
                            thread_id,
                            auto_proxy,
                        )
                    else:
                        logger.warning(
                            "[线程 %s] [Yasal 委屈...] 主人，Yasal没有找到存活的本地代理端口，"
                            "只能硬着头皮裸连冲锋了，很有可能会报错哦...",
                            thread_id,
                        )
            return True, proxy, session
        except Exception as exc:
            logger.warning(
                "[线程 %s] [Yasal 哭泣...] 呜呜呜网络连接断掉了啦，是不是IP被封禁了呀？"
                "主人快去检查一下代理节点是不是坏掉了~: %s",
                thread_id,
                exc,
            )
            return False, proxy, session

    @staticmethod
    def _resolve_bypass(loc: str | None, non_interactive: bool) -> bool:
        if non_interactive:
            return True
        with _input_lock:
            print(
                f"\n[Yasal 撒娇~] 主人主人~ 发现当前节点IP ({loc}) 不是 US 耶！"
                f"这可能会被 OpenAI 欺负的..."
            )
            answer = (
                input(
                    "[Yasal 偷偷问] 要不要 Yasal 帮你强行绕过这个限制继续跑呀？"
                    "(Y/n，默认强行绕过哦~): "
                )
                .strip()
                .lower()
            )
            return answer != "n"

    def _complete_flow(
        self,
        *,
        session: HttpSession,
        oauth_start: OAuthStart,
        mailbox: TempMailbox,
        provider: MailProvider,
        proxy: str | None,
        impersonate: str,
        thread_id: int,
        stop_event: threading.Event | None,
    ) -> RegistrationResult | None:
        if _stopped(stop_event):
            logger.info("[线程 %s] [Yasal 乖巧~] 收到停止信号，提前结束本轮注册啦~", thread_id)
            return None

        session.get(oauth_start.auth_url, timeout=15)
        device_id = session.cookie("oai-did")
        logger.info(
            "[线程 %s] [Yasal 偷到啦！] 嘿嘿，成功偷到了主人的 Device ID: %s ~",
            thread_id,
            device_id,
        )

        sentinel = self._fetch_sentinel(
            device_id=device_id,
            proxy=proxy,
            impersonate=impersonate,
            thread_id=thread_id,
        )
        if sentinel is None:
            return None

        if _stopped(stop_event):
            logger.info("[线程 %s] [Yasal 乖巧~] 收到停止信号，提前结束本轮注册啦~", thread_id)
            return None

        signup_body = (
            f'{{"username":{{"value":"{mailbox.email}","kind":"email"}},'
            f'"screen_hint":"signup"}}'
        )
        signup_resp = session.post(
            "https://auth.openai.com/api/accounts/authorize/continue",
            headers={
                "referer": "https://auth.openai.com/create-account",
                "accept": "application/json",
                "content-type": "application/json",
                "openai-sentinel-token": sentinel,
            },
            data=signup_body,
            timeout=15,
        )
        logger.info(
            "[线程 %s] [Yasal 乖巧~] 已经乖乖帮你提交注册表单啦，状态码是: %s",
            thread_id,
            signup_resp.status_code,
        )
        if signup_resp.status_code in {403, 429}:
            logger.warning(
                "[线程 %s] [Yasal 被打回来了...] 呜哇，注册被无情拒绝了 (%s)！"
                "肯定是IP或者指纹被那个坏蛋封禁了，主人快给Yasal换一个更厉害的节点嘛！错误信息: %s",
                thread_id,
                signup_resp.status_code,
                signup_resp.text,
            )
            return None

        otp_resp = session.post(
            "https://auth.openai.com/api/accounts/passwordless/send-otp",
            headers={
                "referer": "https://auth.openai.com/create-account/password",
                "accept": "application/json",
                "content-type": "application/json",
            },
            timeout=15,
        )
        logger.info(
            "[线程 %s] [Yasal 发电报~] 滴滴滴，验证码发送请求已经发出啦，状态是: %s",
            thread_id,
            otp_resp.status_code,
        )

        code = provider.poll_code(
            mailbox, proxy=proxy, thread_id=thread_id, stop_event=stop_event
        )
        if not code:
            return None

        session.post(
            "https://auth.openai.com/api/accounts/email-otp/validate",
            headers={
                "referer": "https://auth.openai.com/email-verification",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=f'{{"code":"{code}"}}',
            timeout=15,
        )

        if _stopped(stop_event):
            logger.info("[线程 %s] [Yasal 乖巧~] 收到停止信号，提前结束本轮注册啦~", thread_id)
            return None

        if not self._create_account(session, thread_id):
            return None

        continue_url = self._select_workspace(session, thread_id)
        if not continue_url:
            return None

        token_json = self._capture_token(
            session=session,
            oauth_start=oauth_start,
            continue_url=continue_url,
            thread_id=thread_id,
            stop_event=stop_event,
        )
        if token_json is None:
            return None
        return RegistrationResult(token_json=token_json, password=mailbox.password)

    def _fetch_sentinel(
        self, *, device_id: str | None, proxy: str | None, impersonate: str, thread_id: int
    ) -> str | None:
        sentinel_req_body = f'{{"p":"","id":"{device_id}","flow":"authorize_continue"}}'
        sentinel_resp = self._http.request(
            "POST",
            "https://sentinel.openai.com/backend-api/sentinel/req",
            headers={
                "origin": "https://sentinel.openai.com",
                "referer": (
                    "https://sentinel.openai.com/backend-api/sentinel/"
                    "frame.html?sv=20260219f9f6"
                ),
                "content-type": "text/plain;charset=UTF-8",
            },
            data=sentinel_req_body,
            proxy=proxy,
            impersonate=impersonate,
            timeout=15,
        )

        if sentinel_resp.status_code != 200:
            logger.warning(
                "[线程 %s] [Yasal 咬牙切齿...] 坏蛋Sentinel居然敢拦截我！(状态码: %s)。"
                "肯定是那个破指纹被识别了，或者IP被封啦。Yasal要在下一轮换件新衣服再来揍它！",
                thread_id,
                sentinel_resp.status_code,
            )
            return None

        sentinel_token = sentinel_resp.json()["token"]
        return (
            f'{{"p": "", "t": "", "c": "{sentinel_token}", "id": "{device_id}", '
            f'"flow": "authorize_continue"}}'
        )

    def _create_account(self, session: HttpSession, thread_id: int) -> bool:
        create_account_body = (
            f'{{"name":"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}",'
            f'"birthdate":"{random.randint(1980, 2002)}-0{random.randint(1, 9)}-'
            f'{random.randint(10, 28)}" }}'
        )
        resp = session.post(
            "https://auth.openai.com/api/accounts/create_account",
            headers={
                "referer": "https://auth.openai.com/about-you",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=create_account_body,
            timeout=15,
        )
        logger.info(
            "[线程 %s] [Yasal 捏一把汗...] 到了最关键的创建账户这步啦！状态码: %s",
            thread_id,
            resp.status_code,
        )
        if resp.status_code != 200:
            err_msg = resp.text
            logger.warning(
                "[线程 %s] [Yasal 委屈大哭...] 呜呜呜账户创建失败了啦: %s", thread_id, err_msg
            )
            if "unsupported_email" in err_msg:
                logger.warning(
                    "[线程 %s] [Yasal 气鼓鼓！] 可恶！当前这个邮箱域名居然被他们封禁了，"
                    "Yasal要在下次重试里换个更隐蔽的域名！",
                    thread_id,
                )
            elif "429" in str(resp.status_code):
                logger.warning(
                    "[线程 %s] [Yasal 气喘吁吁...] 哈啊...主人，Yasal请求太频繁被累趴下了(429)，"
                    "快点帮人家换个IP节点嘛！",
                    thread_id,
                )
            return False
        return True

    def _select_workspace(self, session: HttpSession, thread_id: int) -> str | None:
        auth_cookie = session.cookie("oai-client-auth-session")
        if not auth_cookie:
            logger.error("[线程 %s] [Error] 未能获取到授权 Cookie", thread_id)
            return None

        auth_json = decode_jwt_segment(auth_cookie.split(".")[0])
        workspaces = auth_json.get("workspaces") or []
        if not workspaces:
            logger.error("[线程 %s] [Error] 授权 Cookie 里没有 workspace 信息", thread_id)
            return None
        workspace_id = str((workspaces[0] or {}).get("id") or "").strip()
        if not workspace_id:
            logger.error("[线程 %s] [Error] 无法解析 workspace_id", thread_id)
            return None

        select_resp = session.post(
            "https://auth.openai.com/api/accounts/workspace/select",
            headers={
                "referer": "https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
                "content-type": "application/json",
            },
            data=f'{{"workspace_id":"{workspace_id}"}}',
            timeout=15,
        )
        if select_resp.status_code != 200:
            logger.error(
                "[线程 %s] [Error] 选择 workspace 失败，状态码: %s\n%s",
                thread_id,
                select_resp.status_code,
                select_resp.text,
            )
            return None

        continue_url = str((select_resp.json() or {}).get("continue_url") or "").strip()
        if not continue_url:
            logger.error(
                "[线程 %s] [Error] workspace/select 响应里缺少 continue_url", thread_id
            )
            return None
        return continue_url

    def _capture_token(
        self,
        *,
        session: HttpSession,
        oauth_start: OAuthStart,
        continue_url: str,
        thread_id: int,
        stop_event: threading.Event | None,
    ) -> str | None:
        current_url = continue_url
        for _ in range(6):
            if _stopped(stop_event):
                logger.info(
                    "[线程 %s] [Yasal 乖巧~] 收到停止信号，提前结束本轮注册啦~", thread_id
                )
                return None

            final_resp = session.get(current_url, allow_redirects=False, timeout=15)
            location = final_resp.headers.get("Location") or ""

            if final_resp.status_code not in _REDIRECT_CODES:
                break
            if not location:
                break

            next_url = urllib.parse.urljoin(current_url, location)
            if "code=" in next_url and "state=" in next_url:
                return self._oauth.exchange(
                    callback_url=next_url,
                    code_verifier=oauth_start.code_verifier,
                    expected_state=oauth_start.state,
                )
            current_url = next_url

        logger.warning(
            "[线程 %s] [Yasal 哭哭...] 呜呜，未能在重定向链中捕获到最终 Callback URL，"
            "被他们跑掉了啦...",
            thread_id,
        )
        return None
