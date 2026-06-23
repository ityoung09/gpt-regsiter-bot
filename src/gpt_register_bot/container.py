from __future__ import annotations

from functools import lru_cache

from gpt_register_bot.application.job_manager import JobManager
from gpt_register_bot.application.registration_service import RegistrationService
from gpt_register_bot.config.settings import Settings, get_settings
from gpt_register_bot.domain.ports import HttpClient, MailProvider, TokenRepository
from gpt_register_bot.infrastructure.cpa import CpaUploader
from gpt_register_bot.infrastructure.http_client import CurlHttpClient, detect_local_proxy
from gpt_register_bot.infrastructure.mail import build_mail_provider
from gpt_register_bot.infrastructure.oauth import OAuthClient
from gpt_register_bot.infrastructure.persistence import FileTokenRepository


class Container:
    """Composition root: wires concrete adapters into application services."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http: HttpClient = CurlHttpClient()
        self.oauth = OAuthClient()
        self.cpa = CpaUploader()
        self.repository: TokenRepository = FileTokenRepository(settings.output_dir)
        self._job_manager: JobManager | None = None

    def mail_provider(self, provider_key: str) -> MailProvider | None:
        return build_mail_provider(provider_key, self.http)

    def registration_service(self) -> RegistrationService:
        return RegistrationService(
            http=self.http,
            provider_factory=self.mail_provider,
            oauth=self.oauth,
            repository=self.repository,
            cpa=self.cpa,
            proxy_detector=detect_local_proxy,
        )

    def job_manager(self) -> JobManager:
        if self._job_manager is None:
            self._job_manager = JobManager(self.settings, self.registration_service)
        return self._job_manager


@lru_cache
def get_container() -> Container:
    return Container(get_settings())
