"""
Провайдер Graph API
Использует Microsoft Graph REST API
"""

import json
import logging
from typing import List, Optional
from datetime import datetime

from curl_cffi import requests as _requests

from ..base import ProviderType, EmailMessage
from ..account import OutlookAccount
from ..token_manager import TokenManager
from .base import OutlookProvider, ProviderConfig


logger = logging.getLogger(__name__)


class GraphAPIProvider(OutlookProvider):
    """
    Провайдер Graph API
    Использует Microsoft Graph REST API для получения писем
    Требуется scope graph.microsoft.com/.default
    """

    # Конечная точка Graph API
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    MESSAGES_ENDPOINT = "/me/mailFolders/inbox/messages"

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.GRAPH_API

    def __init__(
        self,
        account: OutlookAccount,
        config: Optional[ProviderConfig] = None,
    ):
        super().__init__(account, config)

        # Менеджер токенов
        self._token_manager: Optional[TokenManager] = None

        # Примечание: Graph API обязательно требует OAuth2
        if not account.has_oauth():
            logger.warning(
                f"[{self.account.email}] Провайдер Graph API требует конфигурацию OAuth2 "
                f"(client_id + refresh_token)"
            )

    def connect(self) -> bool:
        """
        Проверить подключение (получить Token)

        Returns:
            Успешно ли подключение
        """
        if not self.account.has_oauth():
            error = "Graph API требует конфигурацию OAuth2"
            self.record_failure(error)
            logger.error(f"[{self.account.email}] {error}")
            return False

        if not self._token_manager:
            self._token_manager = TokenManager(
                self.account,
                ProviderType.GRAPH_API,
                self.config.proxy_url,
                self.config.timeout,
            )

        # Попытка получить Token
        token = self._token_manager.get_access_token()
        if token:
            self._connected = True
            self.record_success()
            logger.info(f"[{self.account.email}] Подключение Graph API успешно")
            return True

        return False

    def disconnect(self):
        """Отключиться (очистить состояние)"""
        self._connected = False

    def get_recent_emails(
        self,
        count: int = 20,
        only_unseen: bool = True,
    ) -> List[EmailMessage]:
        """
        Получить последние письма

        Args:
            count: Количество для получения
            only_unseen: Только непрочитанные

        Returns:
            Список писем
        """
        if not self._connected:
            if not self.connect():
                return []

        try:
            # Получить Access Token
            token = self._token_manager.get_access_token()
            if not token:
                self.record_failure("Не удалось получить Access Token")
                return []

            # Построить API-запрос
            url = f"{self.GRAPH_API_BASE}{self.MESSAGES_ENDPOINT}"

            params = {
                "$top": count,
                "$select": "id,subject,from,toRecipients,receivedDateTime,isRead,hasAttachments,bodyPreview,body",
                "$orderby": "receivedDateTime desc",
            }

            # Только непрочитанные письма
            if only_unseen:
                params["$filter"] = "isRead eq false"

            # Построить конфигурацию прокси
            proxies = None
            if self.config.proxy_url:
                proxies = {"http": self.config.proxy_url, "https": self.config.proxy_url}

            # Отправить запрос (curl_cffi автоматически URL-кодирует params)
            resp = _requests.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Prefer": "outlook.body-content-type='text'",
                },
                proxies=proxies,
                timeout=self.config.timeout,
                impersonate="chrome110",
            )

            if resp.status_code == 401:
                # Token без прав Graph (client_id не авторизован), очищаем кэш но не записываем неудачу
                # Чтобы избежать отключения провайдера из-за недостаточных прав, что повлияет на другие учётные записи
                if self._token_manager:
                    self._token_manager.clear_cache()
                self._connected = False
                logger.warning(f"[{self.account.email}] Graph API вернул 401, client_id возможно не имеет прав Graph, пропуск")
                return []

            if resp.status_code != 200:
                error_body = resp.text[:200]
                self.record_failure(f"HTTP {resp.status_code}: {error_body}")
                logger.error(f"[{self.account.email}] Запрос Graph API не удался: HTTP {resp.status_code}")
                return []

            data = resp.json()

            # Разбор писем
            messages = data.get("value", [])
            emails = []

            for msg in messages:
                try:
                    email_msg = self._parse_graph_message(msg)
                    if email_msg:
                        emails.append(email_msg)
                except Exception as e:
                    logger.warning(f"[{self.account.email}] Не удалось разобрать письмо Graph API: {e}")

            self.record_success()
            return emails

        except Exception as e:
            self.record_failure(str(e))
            logger.error(f"[{self.account.email}] Graph API не удалось получить письма: {e}")
            return []

    def _parse_graph_message(self, msg: dict) -> Optional[EmailMessage]:
        """
        Разобрать сообщение Graph API

        Args:
            msg: Объект сообщения Graph API

        Returns:
            Объект EmailMessage
        """
        # Разбор отправителя
        from_info = msg.get("from", {})
        sender_info = from_info.get("emailAddress", {})
        sender = sender_info.get("address", "")

        # Разбор получателей
        recipients = []
        for recipient in msg.get("toRecipients", []):
            addr_info = recipient.get("emailAddress", {})
            addr = addr_info.get("address", "")
            if addr:
                recipients.append(addr)

        # Разбор даты
        received_at = None
        received_timestamp = 0
        try:
            date_str = msg.get("receivedDateTime", "")
            if date_str:
                # Формат ISO 8601
                received_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                received_timestamp = int(received_at.timestamp())
        except Exception:
            pass

        # Получить тело
        body_info = msg.get("body", {})
        body = body_info.get("content", "")
        body_preview = msg.get("bodyPreview", "")

        return EmailMessage(
            id=msg.get("id", ""),
            subject=msg.get("subject", ""),
            sender=sender,
            recipients=recipients,
            body=body,
            body_preview=body_preview,
            received_at=received_at,
            received_timestamp=received_timestamp,
            is_read=msg.get("isRead", False),
            has_attachments=msg.get("hasAttachments", False),
        )

    def test_connection(self) -> bool:
        """
        Тестировать подключение Graph API

        Returns:
            Работает ли подключение
        """
        try:
            # Попытка получить одно письмо для проверки подключения
            emails = self.get_recent_emails(count=1, only_unseen=False)
            return True
        except Exception as e:
            logger.warning(f"[{self.account.email}] Тест подключения Graph API не пройден: {e}")
            return False
