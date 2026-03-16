"""
Провайдер новой версии IMAP
Использует сервер outlook.live.com и конечную точку Token login.microsoftonline.com/consumers
"""

import email
import imaplib
import logging
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import List, Optional

from ..base import ProviderType, EmailMessage
from ..account import OutlookAccount
from ..token_manager import TokenManager
from .base import OutlookProvider, ProviderConfig
from .imap_old import IMAPOldProvider


logger = logging.getLogger(__name__)


class IMAPNewProvider(OutlookProvider):
    """
    Провайдер новой версии IMAP
    Использует outlook.live.com:993 и конечную точку Token login.microsoftonline.com/consumers
    Требуется scope IMAP.AccessAsUser.All
    """

    # Конфигурация IMAP-сервера
    IMAP_HOST = "outlook.live.com"
    IMAP_PORT = 993

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.IMAP_NEW

    def __init__(
        self,
        account: OutlookAccount,
        config: Optional[ProviderConfig] = None,
    ):
        super().__init__(account, config)

        # IMAP-подключение
        self._conn: Optional[imaplib.IMAP4_SSL] = None

        # Менеджер токенов
        self._token_manager: Optional[TokenManager] = None

        # Примечание: новая версия IMAP обязательно требует OAuth2
        if not account.has_oauth():
            logger.warning(
                f"[{self.account.email}] Провайдер новой версии IMAP требует конфигурацию OAuth2 "
                f"(client_id + refresh_token)"
            )

    def connect(self) -> bool:
        """
        Подключиться к IMAP-серверу

        Returns:
            Успешно ли подключение
        """
        if self._connected and self._conn:
            try:
                self._conn.noop()
                return True
            except Exception:
                self.disconnect()

        # Новая версия IMAP обязательно требует OAuth2, без OAuth тихо пропускаем, не записываем неудачу
        if not self.account.has_oauth():
            logger.debug(f"[{self.account.email}] Пропуск IMAP_NEW (нет OAuth)")
            return False

        try:
            logger.debug(f"[{self.account.email}] Подключение к IMAP ({self.IMAP_HOST})...")

            # Создать подключение
            self._conn = imaplib.IMAP4_SSL(
                self.IMAP_HOST,
                self.IMAP_PORT,
                timeout=self.config.timeout,
            )

            # Аутентификация XOAUTH2
            if self._authenticate_xoauth2():
                self._connected = True
                self.record_success()
                logger.info(f"[{self.account.email}] Подключение новой версии IMAP успешно (XOAUTH2)")
                return True

            return False

        except Exception as e:
            self.disconnect()
            self.record_failure(str(e))
            logger.error(f"[{self.account.email}] Подключение новой версии IMAP не удалось: {e}")
            return False

    def _authenticate_xoauth2(self) -> bool:
        """
        Аутентификация с помощью XOAUTH2

        Returns:
            Успешна ли аутентификация
        """
        if not self._token_manager:
            self._token_manager = TokenManager(
                self.account,
                ProviderType.IMAP_NEW,
                self.config.proxy_url,
                self.config.timeout,
            )

        # Получить Access Token
        token = self._token_manager.get_access_token()
        if not token:
            logger.error(f"[{self.account.email}] Не удалось получить IMAP Token")
            return False

        try:
            # Построить строку аутентификации XOAUTH2
            auth_string = f"user={self.account.email}\x01auth=Bearer {token}\x01\x01"
            self._conn.authenticate("XOAUTH2", lambda _: auth_string.encode("utf-8"))
            return True
        except Exception as e:
            logger.error(f"[{self.account.email}] Исключение XOAUTH2 аутентификации: {e}")
            # Очистить кэшированный Token
            self._token_manager.clear_cache()
            return False

    def disconnect(self):
        """Отключить IMAP-подключение"""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

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
            # Выбрать входящие
            self._conn.select("INBOX", readonly=True)

            # Поиск писем
            flag = "UNSEEN" if only_unseen else "ALL"
            status, data = self._conn.search(None, flag)

            if status != "OK" or not data or not data[0]:
                return []

            # Получить ID последних писем
            ids = data[0].split()
            recent_ids = ids[-count:][::-1]

            emails = []
            for msg_id in recent_ids:
                try:
                    email_msg = self._fetch_email(msg_id)
                    if email_msg:
                        emails.append(email_msg)
                except Exception as e:
                    logger.warning(f"[{self.account.email}] Не удалось разобрать письмо (ID: {msg_id}): {e}")

            return emails

        except Exception as e:
            self.record_failure(str(e))
            logger.error(f"[{self.account.email}] Не удалось получить письма: {e}")
            return []

    def _fetch_email(self, msg_id: bytes) -> Optional[EmailMessage]:
        """Получить и разобрать одно письмо"""
        status, data = self._conn.fetch(msg_id, "(RFC822)")
        if status != "OK" or not data or not data[0]:
            return None

        raw = b""
        for part in data:
            if isinstance(part, tuple) and len(part) > 1:
                raw = part[1]
                break

        if not raw:
            return None

        return self._parse_email(raw)

    @staticmethod
    def _parse_email(raw: bytes) -> EmailMessage:
        """Разобрать необработанное письмо"""
        # Использует метод разбора провайдера старой версии
        return IMAPOldProvider._parse_email(raw)

    def test_connection(self) -> bool:
        """Тестировать IMAP-подключение"""
        try:
            with self:
                self._conn.select("INBOX", readonly=True)
                self._conn.search(None, "ALL")
            return True
        except Exception as e:
            logger.warning(f"[{self.account.email}] Тест подключения новой версии IMAP не пройден: {e}")
            return False
