"""
Реализация почтового сервиса AxiomLauncher
"""

import re
import time
import logging
from typing import Optional, Dict, Any, List

from curl_cffi import requests as cffi_requests

from .base import BaseEmailService, EmailServiceError, EmailServiceType
from ..core.http_client import HTTPClient, RequestConfig
from ..config.constants import OTP_CODE_PATTERN, AXIOMLAUNCHER_API_ENDPOINTS

logger = logging.getLogger(__name__)


class AxiomLauncherEmailService(BaseEmailService):
    """
    Почтовый сервис AxiomLauncher
    На основе AxiomLauncher Cloudflare Worker REST API
    """

    def __init__(self, config: Dict[str, Any] = None, name: str = None):
        super().__init__(EmailServiceType.AXIOMLAUNCHER, name)

        from ..config.settings import get_settings
        settings = get_settings()

        default_config = {
            "base_url": settings.axiomlauncher_api_url,
            "api_token": settings.axiomlauncher_api_token.get_secret_value()
            if hasattr(settings.axiomlauncher_api_token, "get_secret_value")
            else str(settings.axiomlauncher_api_token),
            "default_domain": settings.axiomlauncher_default_domain,
            "email_prefix": settings.axiomlauncher_email_prefix,
            "timeout": 30,
            "max_retries": 3,
            "proxy_url": None,
        }

        self.config = {**default_config, **(config or {})}

        http_config = RequestConfig(
            timeout=self.config["timeout"],
            max_retries=self.config["max_retries"],
        )
        self.http_client = HTTPClient(
            proxy_url=self.config.get("proxy_url"),
            config=http_config,
        )

        # mailbox_id cache keyed by email address
        self._mailbox_cache: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config['api_token']}",
        }

    def _url(self, endpoint_key: str) -> str:
        return f"{self.config['base_url']}{AXIOMLAUNCHER_API_ENDPOINTS[endpoint_key]}"

    def _resolve_domain_id(self) -> str:
        """Return a domain_id from settings or pick the first active domain."""
        if self.config.get("default_domain"):
            return self.config["default_domain"]

        response = self.http_client.get(
            self._url("domains"),
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise EmailServiceError(
                f"Не удалось получить список доменов, код: {response.status_code}"
            )

        data = response.json()
        domains = data.get("domains", [])
        for d in domains:
            if d.get("is_active"):
                return str(d["id"])

        if domains:
            return str(domains[0]["id"])

        raise EmailServiceError("Нет доступных доменов AxiomLauncher")

    # ------------------------------------------------------------------
    # abstract interface
    # ------------------------------------------------------------------

    def create_email(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            domain_id = self._resolve_domain_id()

            response = self.http_client.post(
                self._url("mailboxes"),
                headers=self._headers(),
                json={
                    "domain_id": domain_id,
                    "type": self.config.get("email_prefix", "user_"),
                },
            )

            if response.status_code not in (200, 201):
                self.update_status(
                    False,
                    EmailServiceError(
                        f"Создание ящика не удалось, код: {response.status_code}"
                    ),
                )
                raise EmailServiceError(
                    f"Создание ящика AxiomLauncher не удалось, код: {response.status_code}"
                )

            data = response.json()
            email_obj = data.get("email", {})
            creds = data.get("mailbox_credentials", {})

            full_address = email_obj.get("full_address", creds.get("email", ""))
            mailbox_id = str(email_obj.get("id", ""))
            password = creds.get("password", "")

            if not full_address or not mailbox_id:
                self.update_status(
                    False, EmailServiceError("Возвращённые данные неполные")
                )
                raise EmailServiceError("Данные AxiomLauncher неполные")

            email_info = {
                "email": full_address,
                "mailbox_id": mailbox_id,
                "service_id": mailbox_id,
                "password": password,
                "domain_id": domain_id,
                "created_at": time.time(),
            }
            self._mailbox_cache[full_address] = email_info

            logger.info(f"Успешно создан ящик AxiomLauncher: {full_address}")
            self.update_status(True)
            return email_info

        except Exception as e:
            self.update_status(False, e)
            if isinstance(e, EmailServiceError):
                raise
            raise EmailServiceError(f"Не удалось создать ящик AxiomLauncher: {e}")

    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = 120,
        pattern: str = OTP_CODE_PATTERN,
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        mailbox_id = email_id
        if not mailbox_id:
            cached = self._mailbox_cache.get(email)
            if cached:
                mailbox_id = cached.get("mailbox_id")
        if not mailbox_id:
            logger.warning(f"Не найден mailbox_id для {email}")
            return None

        logger.info(f"Ожидание кода подтверждения для {email} ...")
        interval = 3
        start_time = time.time()
        seen_ids: set = set()

        while time.time() - start_time < timeout:
            try:
                response = self.http_client.get(
                    self._url("messages"),
                    params={"mailbox_id": mailbox_id},
                    headers=self._headers(),
                )

                if response.status_code != 200:
                    time.sleep(interval)
                    continue

                data = response.json()
                items = data.get("items", [])

                for msg in items:
                    if not isinstance(msg, dict):
                        continue

                    msg_id = msg.get("id")
                    if msg_id and msg_id in seen_ids:
                        continue
                    if msg_id:
                        seen_ids.add(msg_id)

                    sender = str(msg.get("from", msg.get("sender", ""))).lower()
                    subject = str(msg.get("subject", ""))
                    body = str(msg.get("body", msg.get("text", "")))
                    html = str(msg.get("html", ""))

                    # Check for OpenAI sender
                    combined = f"{sender} {subject} {body} {html}".lower()
                    if "openai" not in combined and "noreply" not in sender:
                        continue

                    # Try subject first, then body / html
                    for text in (subject, body, html):
                        match = re.search(pattern, text)
                        if match:
                            code = match.group(1)
                            logger.info(f"Найден код подтверждения: {code}")
                            self.update_status(True)
                            return code

            except Exception as e:
                logger.debug(f"Ошибка при проверке писем AxiomLauncher: {e}")

            time.sleep(interval)

        logger.warning(f"Таймаут ожидания кода подтверждения: {email}")
        return None

    def list_emails(self, **kwargs) -> List[Dict[str, Any]]:
        try:
            response = self.http_client.get(
                self._url("mailboxes"),
                headers=self._headers(),
            )
            if response.status_code != 200:
                raise EmailServiceError(
                    f"Не удалось получить список ящиков, код: {response.status_code}"
                )
            data = response.json()
            if isinstance(data, list):
                return data
            return data.get("items", data.get("mailboxes", []))
        except Exception as e:
            self.update_status(False, e)
            if isinstance(e, EmailServiceError):
                raise
            raise EmailServiceError(f"Не удалось получить список ящиков AxiomLauncher: {e}")

    def delete_email(self, email_id: str) -> bool:
        """Delete a mailbox. *email_id* may be a mailbox_id or an email address."""
        mailbox_id = email_id
        # If the caller passed an email address, resolve to mailbox_id
        cached = self._mailbox_cache.get(email_id)
        if cached:
            mailbox_id = cached.get("mailbox_id", email_id)

        try:
            response = self.http_client.request(
                "DELETE",
                self._url("mailboxes"),
                headers=self._headers(),
                json={"mailbox_id": mailbox_id},
            )
            success = response.status_code in (200, 204)
            if success:
                # Clean cache
                to_remove = [
                    k
                    for k, v in self._mailbox_cache.items()
                    if v.get("mailbox_id") == mailbox_id or k == email_id
                ]
                for k in to_remove:
                    del self._mailbox_cache[k]
                logger.info(f"Удалён ящик AxiomLauncher: {mailbox_id}")
            self.update_status(success)
            return success
        except Exception as e:
            self.update_status(False, e)
            if isinstance(e, EmailServiceError):
                raise
            raise EmailServiceError(f"Не удалось удалить ящик AxiomLauncher: {e}")

    def check_health(self) -> bool:
        try:
            response = self.http_client.get(
                self._url("domains"),
                headers=self._headers(),
                timeout=10,
            )
            healthy = response.status_code == 200
            self.update_status(healthy)
            return healthy
        except Exception as e:
            logger.warning(f"Проверка здоровья AxiomLauncher не пройдена: {e}")
            self.update_status(False, e)
            return False
