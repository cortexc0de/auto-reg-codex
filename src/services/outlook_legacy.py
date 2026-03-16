"""
Реализация почтового сервиса Outlook
Поддержка протокола IMAP, аутентификации XOAUTH2 и по паролю
"""

import imaplib
import email
import re
import time
import threading
import json
import urllib.parse
import urllib.request
import base64
import hashlib
import secrets
import logging
from typing import Optional, Dict, Any, List
from email.header import decode_header
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError

from .base import BaseEmailService, EmailServiceError, EmailServiceType
from ..config.constants import (
    OTP_CODE_PATTERN,
    OTP_CODE_SIMPLE_PATTERN,
    OTP_CODE_SEMANTIC_PATTERN,
    OPENAI_EMAIL_SENDERS,
    OPENAI_VERIFICATION_KEYWORDS,
)
from ..config.settings import get_settings


def get_email_code_settings() -> dict:
    """
    Получить настройки ожидания кода подтверждения

    Returns:
        dict: Словарь с timeout и poll_interval
    """
    settings = get_settings()
    return {
        "timeout": settings.email_code_timeout,
        "poll_interval": settings.email_code_poll_interval,
    }


logger = logging.getLogger(__name__)


class OutlookAccount:
    """Информация об учётной записи Outlook"""

    def __init__(
        self,
        email: str,
        password: str,
        client_id: str = "",
        refresh_token: str = ""
    ):
        self.email = email
        self.password = password
        self.client_id = client_id
        self.refresh_token = refresh_token

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "OutlookAccount":
        """Создать учётную запись из конфигурации"""
        return cls(
            email=config.get("email", ""),
            password=config.get("password", ""),
            client_id=config.get("client_id", ""),
            refresh_token=config.get("refresh_token", "")
        )

    def has_oauth(self) -> bool:
        """Поддерживает ли OAuth2"""
        return bool(self.client_id and self.refresh_token)

    def validate(self) -> bool:
        """Проверить, действительна ли информация об учётной записи"""
        return bool(self.email and self.password) or self.has_oauth()


class OutlookIMAPClient:
    """
    Клиент Outlook IMAP
    Поддержка аутентификации XOAUTH2 и по паролю
    """

    # Кэш Microsoft OAuth2 Token
    _token_cache: Dict[str, tuple] = {}
    _cache_lock = threading.Lock()

    def __init__(
        self,
        account: OutlookAccount,
        host: str = "outlook.office365.com",
        port: int = 993,
        timeout: int = 20
    ):
        self.account = account
        self.host = host
        self.port = port
        self.timeout = timeout
        self._conn: Optional[imaplib.IMAP4_SSL] = None

    @staticmethod
    def refresh_ms_token(account: OutlookAccount, timeout: int = 15) -> str:
        """Обновить access token Microsoft"""
        if not account.client_id or not account.refresh_token:
            raise RuntimeError("Отсутствует client_id или refresh_token")

        key = account.email.lower()
        with OutlookIMAPClient._cache_lock:
            cached = OutlookIMAPClient._token_cache.get(key)
            if cached and time.time() < cached[1]:
                return cached[0]

        body = urllib.parse.urlencode({
            "client_id": account.client_id,
            "refresh_token": account.refresh_token,
            "grant_type": "refresh_token",
            "redirect_uri": "https://login.live.com/oauth20_desktop.srf",
        }).encode()

        req = urllib.request.Request(
            "https://login.live.com/oauth20_token.srf",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
        except HTTPError as e:
            raise RuntimeError(f"Обновление MS OAuth не удалось: {e.code}") from e

        token = data.get("access_token")
        if not token:
            raise RuntimeError("Ответ MS OAuth не содержит access_token")

        ttl = int(data.get("expires_in", 3600))
        with OutlookIMAPClient._cache_lock:
            OutlookIMAPClient._token_cache[key] = (token, time.time() + ttl - 120)

        return token

    @staticmethod
    def _build_xoauth2(email_addr: str, token: str) -> bytes:
        """Построить строку аутентификации XOAUTH2"""
        return f"user={email_addr}\x01auth=Bearer {token}\x01\x01".encode()

    def connect(self):
        """Подключиться к IMAP-серверу"""
        self._conn = imaplib.IMAP4_SSL(self.host, self.port, timeout=self.timeout)

        # Предпочтительно использовать аутентификацию XOAUTH2
        if self.account.has_oauth():
            try:
                token = self.refresh_ms_token(self.account)
                self._conn.authenticate(
                    "XOAUTH2",
                    lambda _: self._build_xoauth2(self.account.email, token)
                )
                logger.debug(f"Подключение с XOAUTH2 аутентификацией: {self.account.email}")
                return
            except Exception as e:
                logger.warning(f"XOAUTH2 аутентификация не удалась, откат к аутентификации по паролю: {e}")

        # Откат к аутентификации по паролю
        self._conn.login(self.account.email, self.account.password)
        logger.debug(f"Подключение с аутентификацией по паролю: {self.account.email}")

    def _ensure_connection(self):
        """Убедиться, что соединение действительно"""
        if self._conn:
            try:
                self._conn.noop()
                return
            except Exception:
                self.close()

        self.connect()

    def get_recent_emails(
        self,
        count: int = 20,
        only_unseen: bool = True,
        timeout: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Получить последние письма

        Args:
            count: Количество получаемых писем
            only_unseen: Получать только непрочитанные
            timeout: Таймаут

        Returns:
            Список писем
        """
        self._ensure_connection()

        flag = "UNSEEN" if only_unseen else "ALL"
        self._conn.select("INBOX", readonly=True)

        _, data = self._conn.search(None, flag)
        if not data or not data[0]:
            return []

        # Получить последние письма
        ids = data[0].split()[-count:]
        result = []

        for mid in reversed(ids):
            try:
                _, payload = self._conn.fetch(mid, "(RFC822)")
                if not payload:
                    continue

                raw = b""
                for part in payload:
                    if isinstance(part, tuple) and len(part) > 1:
                        raw = part[1]
                        break

                if raw:
                    result.append(self._parse_email(raw))
            except Exception as e:
                logger.warning(f"Не удалось разобрать письмо (ID: {mid}): {e}")

        return result

    @staticmethod
    def _parse_email(raw: bytes) -> Dict[str, Any]:
        """Разобрать содержимое письма"""
        # Удалить возможный BOM
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]

        msg = email.message_from_bytes(raw)

        # Разобрать заголовки письма
        subject = OutlookIMAPClient._decode_header(msg.get("Subject", ""))
        sender = OutlookIMAPClient._decode_header(msg.get("From", ""))
        date_str = OutlookIMAPClient._decode_header(msg.get("Date", ""))
        to = OutlookIMAPClient._decode_header(msg.get("To", ""))
        delivered_to = OutlookIMAPClient._decode_header(msg.get("Delivered-To", ""))
        x_original_to = OutlookIMAPClient._decode_header(msg.get("X-Original-To", ""))

        # Извлечь тело письма
        body = OutlookIMAPClient._extract_body(msg)

        # Разобрать дату
        date_timestamp = 0
        try:
            if date_str:
                dt = parsedate_to_datetime(date_str)
                date_timestamp = int(dt.timestamp())
        except Exception:
            pass

        return {
            "subject": subject,
            "from": sender,
            "date": date_str,
            "date_timestamp": date_timestamp,
            "to": to,
            "delivered_to": delivered_to,
            "x_original_to": x_original_to,
            "body": body,
            "raw": raw.hex()[:100]  # Сохранение частичного хэша необработанных данных для отладки
        }

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
                parts.append(chunk)

        return "".join(parts).strip()

    @staticmethod
    def _extract_body(msg) -> str:
        """Извлечь тело письма"""
        import html as html_module

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

    def close(self):
        """Закрыть соединение"""
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

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class OutlookService(BaseEmailService):
    """
    Почтовый сервис Outlook
    Поддержка опроса нескольких учётных записей Outlook и получения кодов подтверждения
    """

    def __init__(self, config: Dict[str, Any] = None, name: str = None):
        """
        Инициализация сервиса Outlook

        Args:
            config: Словарь конфигурации, поддерживает следующие ключи:
                - accounts: Список учётных записей Outlook, каждая содержит:
                  - email: Почтовый адрес
                  - password: Пароль
                  - client_id: OAuth2 client_id (опционально)
                  - refresh_token: OAuth2 refresh_token (опционально)
                - imap_host: IMAP-сервер (по умолчанию: outlook.office365.com)
                - imap_port: Порт IMAP (по умолчанию: 993)
                - timeout: Таймаут (по умолчанию: 30)
                - max_retries: Максимальное количество повторных попыток (по умолчанию: 3)
            name: Название сервиса
        """
        super().__init__(EmailServiceType.OUTLOOK, name)

        # Конфигурация по умолчанию
        default_config = {
            "accounts": [],
            "imap_host": "outlook.office365.com",
            "imap_port": 993,
            "timeout": 30,
            "max_retries": 3,
            "proxy_url": None,
        }

        self.config = {**default_config, **(config or {})}

        # Разбор учётных записей
        self.accounts: List[OutlookAccount] = []
        self._current_account_index = 0
        self._account_locks: Dict[str, threading.Lock] = {}

        # Поддержка двух форматов конфигурации:
        # 1. Формат одной учётной записи: {"email": "xxx", "password": "xxx"}
        # 2. Формат нескольких учётных записей: {"accounts": [{"email": "xxx", "password": "xxx"}]}
        if "email" in self.config and "password" in self.config:
            # Формат одной учётной записи
            account = OutlookAccount.from_config(self.config)
            if account.validate():
                self.accounts.append(account)
                self._account_locks[account.email] = threading.Lock()
            else:
                logger.warning(f"Некорректная конфигурация учётной записи Outlook: {self.config}")
        else:
            # Формат нескольких учётных записей
            for account_config in self.config.get("accounts", []):
                account = OutlookAccount.from_config(account_config)
                if account.validate():
                    self.accounts.append(account)
                    self._account_locks[account.email] = threading.Lock()
                else:
                    logger.warning(f"Некорректная конфигурация учётной записи Outlook: {account_config}")

        if not self.accounts:
            logger.warning("Не настроены действительные учётные записи Outlook")

        # Ограничение IMAP-подключений (предотвращение ограничения скорости)
        self._imap_semaphore = threading.Semaphore(5)

        # Механизм дедупликации кодов подтверждения: email -> set of used codes
        self._used_codes: Dict[str, set] = {}

    def create_email(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Выбрать доступную учётную запись Outlook

        Args:
            config: Параметры конфигурации (в настоящее время не используются)

        Returns:
            Словарь с информацией о почте:
            - email: Почтовый адрес
            - service_id: Почта учётной записи (то же, что email)
            - account: Информация об учётной записи
        """
        if not self.accounts:
            self.update_status(False, EmailServiceError("Нет доступных учётных записей Outlook"))
            raise EmailServiceError("Нет доступных учётных записей Outlook")

        # Циклический выбор учётной записи
        with threading.Lock():
            account = self.accounts[self._current_account_index]
            self._current_account_index = (self._current_account_index + 1) % len(self.accounts)

        email_info = {
            "email": account.email,
            "service_id": account.email,  # Для Outlook service_id — это почтовый адрес
            "account": {
                "email": account.email,
                "has_oauth": account.has_oauth()
            }
        }

        logger.info(f"Выбрана учётная запись Outlook: {account.email}")
        self.update_status(True)
        return email_info

    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = None,
        pattern: str = OTP_CODE_PATTERN,
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        """
        Получить код подтверждения из почтового ящика Outlook

        Args:
            email: Почтовый адрес
            email_id: Не используется (для Outlook email является идентификатором)
            timeout: Таймаут (в секундах), по умолчанию используется значение из конфигурации
            pattern: Регулярное выражение для кода подтверждения
            otp_sent_at: Временная метка отправки OTP для фильтрации старых писем

        Returns:
            Строка с кодом подтверждения, None если таймаут или код не найден
        """
        # Найти соответствующую учётную запись
        account = None
        for acc in self.accounts:
            if acc.email.lower() == email.lower():
                account = acc
                break

        if not account:
            self.update_status(False, EmailServiceError(f"Не найдена учётная запись для почтового ящика: {email}"))
            return None

        # Получить настройки ожидания кода подтверждения из базы данных
        code_settings = get_email_code_settings()
        actual_timeout = timeout or code_settings["timeout"]
        poll_interval = code_settings["poll_interval"]

        logger.info(f"[{email}] Начало получения кода подтверждения, таймаут {actual_timeout}с, время отправки OTP: {otp_sent_at}")

        # Инициализация набора для дедупликации кодов подтверждения
        if email not in self._used_codes:
            self._used_codes[email] = set()
        used_codes = self._used_codes[email]

        # Вычисление минимальной временной метки (с запасом 60 секунд на расхождение часов)
        min_timestamp = (otp_sent_at - 60) if otp_sent_at else 0

        start_time = time.time()
        poll_count = 0

        while time.time() - start_time < actual_timeout:
            poll_count += 1
            loop_start = time.time()

            # Прогрессивная проверка писем: первые 3 раза только непрочитанные, затем все
            only_unseen = poll_count <= 3

            try:
                connect_start = time.time()
                with self._imap_semaphore:
                    with OutlookIMAPClient(
                        account,
                        host=self.config["imap_host"],
                        port=self.config["imap_port"],
                        timeout=10
                    ) as client:
                        connect_elapsed = time.time() - connect_start
                        logger.debug(f"[{email}] Время подключения IMAP: {connect_elapsed:.2f}с")

                        # Поиск писем
                        search_start = time.time()
                        emails = client.get_recent_emails(count=15, only_unseen=only_unseen)
                        search_elapsed = time.time() - search_start
                        logger.debug(f"[{email}] Найдено {len(emails)} писем (непрочитанные={only_unseen}), время {search_elapsed:.2f}с")

                        for mail in emails:
                            # Фильтрация по временной метке
                            mail_ts = mail.get("date_timestamp", 0)
                            if min_timestamp > 0 and mail_ts > 0 and mail_ts < min_timestamp:
                                logger.debug(f"[{email}] Пропуск старого письма: {mail.get('subject', '')[:50]}")
                                continue

                            # Проверить, является ли это верификационным письмом от OpenAI
                            if not self._is_openai_verification_mail(mail, email):
                                continue

                            # Извлечь код подтверждения
                            code = self._extract_code_from_mail(mail, pattern)
                            if code:
                                # Проверка дедупликации
                                if code in used_codes:
                                    logger.debug(f"[{email}] Пропуск уже использованного кода подтверждения: {code}")
                                    continue

                                used_codes.add(code)
                                elapsed = int(time.time() - start_time)
                                logger.info(f"[{email}] Найден код подтверждения: {code}, общее время {elapsed}с, опросов {poll_count}")
                                self.update_status(True)
                                return code

            except Exception as e:
                loop_elapsed = time.time() - loop_start
                logger.warning(f"[{email}] Ошибка проверки: {e}, время цикла {loop_elapsed:.2f}с")

            # Ожидание следующего опроса
            time.sleep(poll_interval)

        elapsed = int(time.time() - start_time)
        logger.warning(f"[{email}] Таймаут кода подтверждения ({actual_timeout}с), всего опросов {poll_count}")
        return None

    def list_emails(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Показать все доступные учётные записи Outlook

        Returns:
            Список учётных записей
        """
        return [
            {
                "email": account.email,
                "id": account.email,
                "has_oauth": account.has_oauth(),
                "type": "outlook"
            }
            for account in self.accounts
        ]

    def delete_email(self, email_id: str) -> bool:
        """
        Удалить почтовый ящик (Outlook не поддерживает удаление учётных записей)

        Args:
            email_id: Почтовый адрес

        Returns:
            False (Outlook не поддерживает удаление учётных записей)
        """
        logger.warning(f"Сервис Outlook не поддерживает удаление учётных записей: {email_id}")
        return False

    def check_health(self) -> bool:
        """Проверить доступность сервиса Outlook"""
        if not self.accounts:
            self.update_status(False, EmailServiceError("Нет настроенных учётных записей"))
            return False

        # Тестирование подключения первой учётной записи
        test_account = self.accounts[0]
        try:
            with self._imap_semaphore:
                with OutlookIMAPClient(
                    test_account,
                    host=self.config["imap_host"],
                    port=self.config["imap_port"],
                    timeout=10
                ) as client:
                    # Попытка выбрать почтовый ящик (быстрый тест)
                    client._conn.select("INBOX", readonly=True)
                    self.update_status(True)
                    return True
        except Exception as e:
            logger.warning(f"Проверка здоровья Outlook не пройдена ({test_account.email}): {e}")
            self.update_status(False, e)
            return False

    def _is_oai_mail(self, mail: Dict[str, Any]) -> bool:
        """Определить, связано ли письмо с OpenAI (старый метод, сохранён для совместимости)"""
        combined = f"{mail.get('from', '')} {mail.get('subject', '')} {mail.get('body', '')}".lower()
        keywords = ["openai", "chatgpt", "verification", "verification code", "code"]
        return any(keyword in combined for keyword in keywords)

    def _is_openai_verification_mail(
        self,
        mail: Dict[str, Any],
        target_email: str = None
    ) -> bool:
        """
        Строгое определение, является ли письмо верификационным от OpenAI

        Args:
            mail: Словарь с информацией о письме
            target_email: Целевой почтовый адрес (для проверки получателя)

        Returns:
            Является ли письмо верификационным от OpenAI
        """
        sender = mail.get("from", "").lower()

        # 1. Отправитель должен быть OpenAI
        valid_senders = OPENAI_EMAIL_SENDERS
        if not any(s in sender for s in valid_senders):
            logger.debug(f"Отправитель письма не OpenAI: {sender}")
            return False

        # 2. Тема или тело содержат ключевые слова верификации
        subject = mail.get("subject", "").lower()
        body = mail.get("body", "").lower()
        verification_keywords = OPENAI_VERIFICATION_KEYWORDS
        combined = f"{subject} {body}"
        if not any(kw in combined for kw in verification_keywords):
            logger.debug(f"Письмо не содержит ключевых слов верификации: {subject[:50]}")
            return False

        # 3. Проверка получателя (опционально)
        if target_email:
            recipients = f"{mail.get('to', '')} {mail.get('delivered_to', '')} {mail.get('x_original_to', '')}".lower()
            if target_email.lower() not in recipients:
                logger.debug(f"Получатель письма не совпадает: {recipients[:50]}")
                return False

        logger.debug(f"Определено как верификационное письмо OpenAI: {subject[:50]}")
        return True

    def _extract_code_from_mail(
        self,
        mail: Dict[str, Any],
        fallback_pattern: str = OTP_CODE_PATTERN
    ) -> Optional[str]:
        """
        Извлечь код подтверждения из письма

        Приоритет:
        1. Извлечение из темы (6-значное число)
        2. Извлечение из тела с семантическим regex (например, "code is 123456")
        3. Запасной вариант: любое 6-значное число

        Args:
            mail: Словарь с информацией о письме
            fallback_pattern: Запасное регулярное выражение

        Returns:
            Строка с кодом подтверждения, None если не найден
        """
        # Компиляция регулярных выражений
        re_simple = re.compile(OTP_CODE_SIMPLE_PATTERN)
        re_semantic = re.compile(OTP_CODE_SEMANTIC_PATTERN, re.IGNORECASE)

        # 1. Приоритет темы
        subject = mail.get("subject", "")
        match = re_simple.search(subject)
        if match:
            code = match.group(1)
            logger.debug(f"Код подтверждения извлечён из темы: {code}")
            return code

        # 2. Семантическое совпадение в теле
        body = mail.get("body", "")
        match = re_semantic.search(body)
        if match:
            code = match.group(1)
            logger.debug(f"Код подтверждения извлечён семантически из тела: {code}")
            return code

        # 3. Запасной вариант: любое 6-значное число
        match = re_simple.search(body)
        if match:
            code = match.group(1)
            logger.debug(f"Код подтверждения извлечён запасным методом из тела: {code}")
            return code

        return None

    def get_account_stats(self) -> Dict[str, Any]:
        """Получить статистику учётных записей"""
        total = len(self.accounts)
        oauth_count = sum(1 for acc in self.accounts if acc.has_oauth())

        return {
            "total_accounts": total,
            "oauth_accounts": oauth_count,
            "password_accounts": total - oauth_count,
            "accounts": [
                {
                    "email": acc.email,
                    "has_oauth": acc.has_oauth()
                }
                for acc in self.accounts
            ]
        }

    def add_account(self, account_config: Dict[str, Any]) -> bool:
        """Добавить новую учётную запись Outlook"""
        try:
            account = OutlookAccount.from_config(account_config)
            if not account.validate():
                return False

            self.accounts.append(account)
            self._account_locks[account.email] = threading.Lock()
            logger.info(f"Добавлена учётная запись Outlook: {account.email}")
            return True
        except Exception as e:
            logger.error(f"Не удалось добавить учётную запись Outlook: {e}")
            return False

    def remove_account(self, email: str) -> bool:
        """Удалить учётную запись Outlook"""
        for i, acc in enumerate(self.accounts):
            if acc.email.lower() == email.lower():
                self.accounts.pop(i)
                self._account_locks.pop(email, None)
                logger.info(f"Удалена учётная запись Outlook: {email}")
                return True
        return False
