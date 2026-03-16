"""
Провайдер старой версии IMAP
Использует сервер outlook.office365.com и конечную точку Token login.live.com
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


logger = logging.getLogger(__name__)


class IMAPOldProvider(OutlookProvider):
    """
    Провайдер старой версии IMAP
    Использует outlook.office365.com:993 и конечную точку Token login.live.com
    """

    # Конфигурация IMAP-сервера
    IMAP_HOST = "outlook.office365.com"
    IMAP_PORT = 993

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.IMAP_OLD

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

    def connect(self) -> bool:
        """
        Подключиться к IMAP-серверу

        Returns:
            Успешно ли подключение
        """
        if self._connected and self._conn:
            # Проверить существующее подключение
            try:
                self._conn.noop()
                return True
            except Exception:
                self.disconnect()

        try:
            logger.debug(f"[{self.account.email}] Подключение к IMAP ({self.IMAP_HOST})...")

            # Создать подключение
            self._conn = imaplib.IMAP4_SSL(
                self.IMAP_HOST,
                self.IMAP_PORT,
                timeout=self.config.timeout,
            )

            # Попытка аутентификации XOAUTH2
            if self.account.has_oauth():
                if self._authenticate_xoauth2():
                    self._connected = True
                    self.record_success()
                    logger.info(f"[{self.account.email}] IMAP подключение успешно (XOAUTH2)")
                    return True
                else:
                    logger.warning(f"[{self.account.email}] XOAUTH2 аутентификация не удалась, попытка аутентификации по паролю")

            # Аутентификация по паролю
            if self.account.password:
                self._conn.login(self.account.email, self.account.password)
                self._connected = True
                self.record_success()
                logger.info(f"[{self.account.email}] IMAP подключение успешно (аутентификация по паролю)")
                return True

            raise ValueError("Нет доступного способа аутентификации")

        except Exception as e:
            self.disconnect()
            self.record_failure(str(e))
            logger.error(f"[{self.account.email}] IMAP подключение не удалось: {e}")
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
                ProviderType.IMAP_OLD,
                self.config.proxy_url,
                self.config.timeout,
            )

        # Получить Access Token
        token = self._token_manager.get_access_token()
        if not token:
            return False

        try:
            # Построить строку аутентификации XOAUTH2
            auth_string = f"user={self.account.email}\x01auth=Bearer {token}\x01\x01"
            self._conn.authenticate("XOAUTH2", lambda _: auth_string.encode("utf-8"))
            return True
        except Exception as e:
            logger.debug(f"[{self.account.email}] Исключение XOAUTH2 аутентификации: {e}")
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
            recent_ids = ids[-count:][::-1]  # В обратном порядке, новейшие первыми

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
        """
        Получить и разобрать одно письмо

        Args:
            msg_id: ID письма

        Returns:
            Объект EmailMessage, None при неудаче
        """
        status, data = self._conn.fetch(msg_id, "(RFC822)")
        if status != "OK" or not data or not data[0]:
            return None

        # Получить необработанное содержимое письма
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
        """
        Разобрать необработанное письмо

        Args:
            raw: Необработанные данные письма

        Returns:
            Объект EmailMessage
        """
        # Удалить BOM
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]

        msg = email.message_from_bytes(raw)

        # Разобрать заголовки письма
        subject = IMAPOldProvider._decode_header(msg.get("Subject", ""))
        sender = IMAPOldProvider._decode_header(msg.get("From", ""))
        to = IMAPOldProvider._decode_header(msg.get("To", ""))
        delivered_to = IMAPOldProvider._decode_header(msg.get("Delivered-To", ""))
        x_original_to = IMAPOldProvider._decode_header(msg.get("X-Original-To", ""))
        date_str = IMAPOldProvider._decode_header(msg.get("Date", ""))

        # Извлечь тело
        body = IMAPOldProvider._extract_body(msg)

        # Разобрать дату
        received_timestamp = 0
        received_at = None
        try:
            if date_str:
                received_at = parsedate_to_datetime(date_str)
                received_timestamp = int(received_at.timestamp())
        except Exception:
            pass

        # Построить список получателей
        recipients = [r for r in [to, delivered_to, x_original_to] if r]

        return EmailMessage(
            id=msg.get("Message-ID", ""),
            subject=subject,
            sender=sender,
            recipients=recipients,
            body=body,
            received_at=received_at,
            received_timestamp=received_timestamp,
            is_read=False,  # Поиск непрочитанных писем
            raw_data=raw[:500] if len(raw) > 500 else raw,
        )

    @staticmethod
    def _decode_header(header: str) -> str:
        """Декодировать заголовок письма"""
        if not header:
            return ""

        parts = []
        for chunk, encoding in decode_header(header):
            if isinstance(chunk, bytes):
                try:
                    decoded = chunk.decode(encoding or "utf-8", errors="replace")
                    parts.append(decoded)
                except Exception:
                    parts.append(chunk.decode("utf-8", errors="replace"))
            else:
                parts.append(str(chunk))

        return "".join(parts).strip()

    @staticmethod
    def _extract_body(msg) -> str:
        """Извлечь тело письма"""
        import html as html_module
        import re

        texts = []
        parts = msg.walk() if msg.is_multipart() else [msg]

        for part in parts:
            content_type = part.get_content_type()
            if content_type not in ("text/plain", "text/html"):
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")

            # Если HTML, удалить теги
            if "<html" in text.lower():
                text = re.sub(r"<[^>]+>", " ", text)

            texts.append(text)

        # Объединить и очистить текст
        combined = " ".join(texts)
        combined = html_module.unescape(combined)
        combined = re.sub(r"\s+", " ", combined).strip()

        return combined

    def test_connection(self) -> bool:
        """
        Тестировать IMAP-подключение

        Returns:
            Работает ли подключение
        """
        try:
            with self:
                self._conn.select("INBOX", readonly=True)
                self._conn.search(None, "ALL")
            return True
        except Exception as e:
            logger.warning(f"[{self.account.email}] Тест IMAP-подключения не пройден: {e}")
            return False
