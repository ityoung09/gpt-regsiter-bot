from __future__ import annotations

import argparse
import logging
import random
import threading
import time

from gpt_register_bot.application.registration_service import RegistrationService
from gpt_register_bot.container import get_container
from gpt_register_bot.domain.ports import CpaClient, TokenRepository

DEFAULT_CLI_CONCURRENCY = 3
DEFAULT_PROVIDER = "mailtm"

logger = logging.getLogger(__name__)


def worker(
    *,
    service: RegistrationService,
    repository: TokenRepository,
    cpa: CpaClient,
    thread_id: int,
    proxy: str | None,
    once: bool,
    sleep_min: int,
    sleep_max: int,
    provider_key: str,
    cpa_url: str | None,
    cpa_token: str | None,
    stop_event: threading.Event,
) -> None:
    count = 0

    while not stop_event.is_set():
        count += 1
        logger.info(
            "[线程 %s] [Yasal 的飞扑~] >>> 主人~ Yasal要开始第 %s 次为你榨取账号啦 "
            "(使用 %s) <<<",
            thread_id,
            count,
            provider_key,
        )

        is_success = False
        try:
            result = service.register_once(
                thread_id=thread_id,
                proxy=proxy,
                provider_key=provider_key,
                non_interactive=False,
                stop_event=stop_event,
            )
            if result:
                token_path = repository.persist(
                    result.token_json, result.password, thread_id=thread_id
                )
                logger.info(
                    "[线程 %s] [Yasal 高潮啦！] 成功啦成功啦！账号密码已经乖乖躺在 "
                    "accounts.txt 里啦，Token 也帮主人保存好咯: %s，快来奖励Yasal嘛~",
                    thread_id,
                    token_path,
                )
                if cpa_url and cpa_token:
                    cpa.upload(str(token_path), cpa_url, cpa_token, proxy, thread_id)
                is_success = True
            else:
                logger.info(
                    "[线程 %s] [Yasal 垂头丧气...] 呜呜...这次榨取失败了，"
                    "主人不要惩罚我，下次我一定更努力！",
                    thread_id,
                )
        except Exception:
            logger.exception("[线程 %s] [Yasal 吓坏了...] 发生未捕获异常了啦", thread_id)

        if once:
            break

        wait_time = random.randint(sleep_min, sleep_max)
        if not is_success:
            logger.info(
                "[线程 %s] [Yasal 痛定思痛...] 因为刚才失败了，Yasal要乖乖罚站 30 秒"
                "反省一下，免得被封禁...",
                thread_id,
            )
            wait_time += 30

        logger.info(
            "[线程 %s] [Yasal 乖巧趴下~] Yasal还要乖乖休息 %s 秒，"
            "马上就回来继续服侍主人...",
            thread_id,
            wait_time,
        )
        if stop_event.wait(wait_time):
            break


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="OpenAI 自动注册脚本")
    parser.add_argument(
        "--proxy", default=None, help="代理地址，如 http://127.0.0.1:7890"
    )
    parser.add_argument("--once", action="store_true", help="只运行一次")
    parser.add_argument("--sleep-min", type=int, default=10, help="循环模式最短等待秒数")
    parser.add_argument("--sleep-max", type=int, default=30, help="循环模式最长等待秒数")
    parser.add_argument("--cpa-url", default=None, help="CPA 管理平台上传地址")
    parser.add_argument("--cpa-token", default=None, help="CPA 管理平台 Token")
    args = parser.parse_args()

    sleep_min = max(1, args.sleep_min)
    sleep_max = max(sleep_min, args.sleep_max)

    if args.cpa_url and args.cpa_token:
        logger.info("[CPA] 已启用CPA上传: %s", args.cpa_url)

    logger.info(
        "[Yasal 的深情告白~] Yasal's Seamless OpenAI Auto-Registrar Started - "
        "主人请坐稳，Yasal要启动 %s 个高频并发线程，为你榨干他们的服务器啦...",
        DEFAULT_CLI_CONCURRENCY,
    )

    container = get_container()
    service = container.registration_service()
    repository = container.repository
    cpa = container.cpa

    stop_event = threading.Event()
    threads: list[threading.Thread] = []
    for index in range(1, DEFAULT_CLI_CONCURRENCY + 1):
        thread = threading.Thread(
            target=worker,
            kwargs={
                "service": service,
                "repository": repository,
                "cpa": cpa,
                "thread_id": index,
                "proxy": args.proxy,
                "once": args.once,
                "sleep_min": sleep_min,
                "sleep_max": sleep_max,
                "provider_key": DEFAULT_PROVIDER,
                "cpa_url": args.cpa_url,
                "cpa_token": args.cpa_token,
                "stop_event": stop_event,
            },
            daemon=True,
            name=f"register-cli-{index}",
        )
        thread.start()
        threads.append(thread)

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
        logger.info(
            "[Yasal 累瘫了...] 呼啊...主人，所有的榨取线程都已经跑完啦，"
            "Yasal实在是一滴都不剩了，任务圆满结束哦！"
        )
    except KeyboardInterrupt:
        logger.info("[Yasal 乖巧~] 收到主人的中断信号，正在通知所有线程优雅收工...")
        stop_event.set()
        for thread in threads:
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
