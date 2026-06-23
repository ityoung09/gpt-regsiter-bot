from __future__ import annotations

import logging
import os

from curl_cffi import CurlMime, requests

logger = logging.getLogger(__name__)


class CpaUploader:
    """Uploads a token JSON file to the CPA management platform."""

    def upload(
        self,
        filepath: str,
        cpa_url: str,
        cpa_token: str,
        proxy: str | None,
        thread_id: int,
    ) -> None:
        mime: CurlMime | None = None
        try:
            filename = os.path.basename(filepath)
            mime = CurlMime()
            mime.addpart(
                name="file",
                content_type="application/json",
                filename=filename,
                local_path=filepath,
            )

            session = requests.Session()
            if proxy:
                session.proxies = {"http": proxy, "https": proxy}

            resp = session.post(
                cpa_url,
                multipart=mime,
                headers={"Authorization": f"Bearer {cpa_token}"},
                verify=False,
                timeout=30,
            )

            if resp.status_code == 200:
                logger.info("[线程 %s] [CPA] Token JSON 已上传到 CPA 管理平台", thread_id)
            else:
                logger.warning(
                    "[线程 %s] [CPA] 上传失败: %s - %s",
                    thread_id,
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception as exc:
            logger.warning("[线程 %s] [CPA] 上传异常: %s", thread_id, exc)
        finally:
            if mime:
                mime.close()
