"""
Реализация почтового сервиса Tempmail.lol
"""

import re
import time
import logging
from typing import Optional, Dict, Any, List
import json

from curl_cffi import requests as cffi_requests

from .base import BaseEmailService, EmailServiceError, EmailServiceType
from ..core.http_client import HTTPClient, RequestConfig
from ..config.constants import OTP_CODE_PATTERN


logger = logging.getLogger(__name__)


class TempmailService(BaseEmailService):
    """
    Почтовый сервис Tempmail.lol
    На основе Tempmail.lol API v2
    """

    def __init__(self, config: Dict[str, Any] = None, name: str = None):
        """
        Инициализация сервиса Tempmail

        Args:
            config: Словарь конфигурации, поддерживает следующие ключи:
                - base_url: Базовый URL API (по умолчанию: https://api.tempmail.lol/v2)
                - timeout: Таймаут запроса (по умолчанию: 30)
                - max_retries: Максимальное количество повторных попыток (по умолчанию: 3)
                - proxy_url: URL прокси
            name: Название сервиса
        """
        super().__init__(EmailServiceType.TEMPMAIL, name)

        # Конфигурация по умолчанию
        default_config = {
            "base_url": "https://api.tempmail.lol/v2",
            "timeout": 30,
            "max_retries": 3,
            "proxy_url": None,
        }

        self.config = {**default_config, **(config or {})}

        # Создание HTTP-клиента
        http_config = RequestConfig(
            timeout=self.config["timeout"],
            max_retries=self.config["max_retries"],
        )
        self.http_client = HTTPClient(
            proxy_url=self.config.get("proxy_url"),
            config=http_config
        )

        # Переменные состояния
        self._email_cache: Dict[str, Dict[str, Any]] = {}
        self._last_check_time: float = 0

    def create_email(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Создать новый временный почтовый ящик

        Args:
            config: Параметры конфигурации (Tempmail.lol в настоящее время не поддерживает пользовательскую конфигурацию)

        Returns:
            Словарь с информацией о почте:
            - email: Почтовый адрес
            - service_id: Токен почтового ящика
            - token: Токен почтового ящика (то же, что service_id)
            - created_at: Временная метка создания
        """
        try:
            # Отправить запрос на создание
            response = self.http_client.post(
                f"{self.config['base_url']}/inbox/create",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={}
            )

            if response.status_code not in (200, 201):
                self.update_status(False, EmailServiceError(f"Запрос не удался, код состояния: {response.status_code}"))
                raise EmailServiceError(f"Запрос Tempmail.lol не удался, код состояния: {response.status_code}")

            data = response.json()
            email = str(data.get("address", "")).strip()
            token = str(data.get("token", "")).strip()

            if not email or not token:
                self.update_status(False, EmailServiceError("Возвращённые данные неполные"))
                raise EmailServiceError("Данные, возвращённые Tempmail.lol, неполные")

            # Кэширование информации о почтовом ящике
            email_info = {
                "email": email,
                "service_id": token,
                "token": token,
                "created_at": time.time(),
            }
            self._email_cache[email] = email_info

            logger.info(f"Успешно создан почтовый ящик Tempmail.lol: {email}")
            self.update_status(True)
            return email_info

        except Exception as e:
            self.update_status(False, e)
            if isinstance(e, EmailServiceError):
                raise
            raise EmailServiceError(f"Не удалось создать почтовый ящик Tempmail.lol: {e}")

    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = 120,
        pattern: str = OTP_CODE_PATTERN,
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        """
        Получить код подтверждения из Tempmail.lol

        Args:
            email: Почтовый адрес
            email_id: Токен почтового ящика (если не указан, ищется в кэше)
            timeout: Таймаут (в секундах)
            pattern: Регулярное выражение для кода подтверждения
            otp_sent_at: Временная метка отправки OTP (сервис Tempmail не использует этот параметр)

        Returns:
            Строка с кодом подтверждения, None если таймаут или код не найден
        """
        token = email_id
        if not token:
            # Поиск токена в кэше
            if email in self._email_cache:
                token = self._email_cache[email].get("token")
            else:
                logger.warning(f"Не найден токен для почтового ящика {email}, невозможно получить код подтверждения")
                return None

        if not token:
            logger.warning(f"Почтовый ящик {email} не имеет токена, невозможно получить код подтверждения")
            return None

        logger.info(f"Ожидание кода подтверждения для почтового ящика {email}...")

        start_time = time.time()
        seen_ids = set()

        while time.time() - start_time < timeout:
            try:
                # Получить список писем
                response = self.http_client.get(
                    f"{self.config['base_url']}/inbox",
                    params={"token": token},
                    headers={"Accept": "application/json"}
                )

                if response.status_code != 200:
                    time.sleep(3)
                    continue

                data = response.json()

                # Проверить, не истёк ли срок действия inbox
                if data is None or (isinstance(data, dict) and not data):
                    logger.warning(f"Почтовый ящик {email} истёк")
                    return None

                email_list = data.get("emails", []) if isinstance(data, dict) else []

                if not isinstance(email_list, list):
                    time.sleep(3)
                    continue

                for msg in email_list:
                    if not isinstance(msg, dict):
                        continue

                    # Использование date в качестве уникального идентификатора
                    msg_date = msg.get("date", 0)
                    if not msg_date or msg_date in seen_ids:
                        continue
                    seen_ids.add(msg_date)

                    sender = str(msg.get("from", "")).lower()
                    subject = str(msg.get("subject", ""))
                    body = str(msg.get("body", ""))
                    html = str(msg.get("html") or "")

                    content = "\n".join([sender, subject, body, html])

                    # Проверить, является ли это письмом от OpenAI
                    if "openai" not in sender and "openai" not in content.lower():
                        continue

                    # Извлечь код подтверждения
                    match = re.search(pattern, content)
                    if match:
                        code = match.group(1)
                        logger.info(f"Найден код подтверждения: {code}")
                        self.update_status(True)
                        return code

            except Exception as e:
                logger.debug(f"Ошибка при проверке писем: {e}")

            # Подождать перед следующей проверкой
            time.sleep(3)

        logger.warning(f"Таймаут ожидания кода подтверждения: {email}")
        return None

    def list_emails(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Показать все кэшированные почтовые ящики

        Note:
            API Tempmail.lol не поддерживает показ всех почтовых ящиков, здесь возвращаются кэшированные
        """
        return list(self._email_cache.values())

    def delete_email(self, email_id: str) -> bool:
        """
        Удалить почтовый ящик

        Note:
            API Tempmail.lol не поддерживает удаление почтовых ящиков, здесь удаление из кэша
        """
        # Поиск и удаление из кэша
        emails_to_delete = []
        for email, info in self._email_cache.items():
            if info.get("token") == email_id:
                emails_to_delete.append(email)

        for email in emails_to_delete:
            del self._email_cache[email]
            logger.info(f"Удалён почтовый ящик из кэша: {email}")

        return len(emails_to_delete) > 0

    def check_health(self) -> bool:
        """Проверить доступность сервиса Tempmail.lol"""
        try:
            response = self.http_client.get(
                f"{self.config['base_url']}/inbox/create",
                timeout=10
            )
            # Даже при ошибочном коде состояния сервис считается доступным (если есть подключение)
            self.update_status(True)
            return True
        except Exception as e:
            logger.warning(f"Проверка здоровья Tempmail.lol не пройдена: {e}")
            self.update_status(False, e)
            return False

    def get_inbox(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Получить содержимое входящих

        Args:
            token: Токен почтового ящика

        Returns:
            Данные входящих
        """
        try:
            response = self.http_client.get(
                f"{self.config['base_url']}/inbox",
                params={"token": token},
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                return None

            return response.json()
        except Exception as e:
            logger.error(f"Не удалось получить входящие: {e}")
            return None

    def wait_for_verification_code_with_callback(
        self,
        email: str,
        token: str,
        callback: callable = None,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Ожидать код подтверждения с поддержкой функции обратного вызова

        Args:
            email: Почтовый адрес
            token: Токен почтового ящика
            callback: Функция обратного вызова, принимает информацию о текущем состоянии
            timeout: Таймаут

        Returns:
            Код подтверждения или None
        """
        start_time = time.time()
        seen_ids = set()
        check_count = 0

        while time.time() - start_time < timeout:
            check_count += 1

            if callback:
                callback({
                    "status": "checking",
                    "email": email,
                    "check_count": check_count,
                    "elapsed_time": time.time() - start_time,
                })

            try:
                data = self.get_inbox(token)
                if not data:
                    time.sleep(3)
                    continue

                # Проверить, не истёк ли срок действия inbox
                if data is None or (isinstance(data, dict) and not data):
                    if callback:
                        callback({
                            "status": "expired",
                            "email": email,
                            "message": "Почтовый ящик истёк"
                        })
                    return None

                email_list = data.get("emails", []) if isinstance(data, dict) else []

                for msg in email_list:
                    msg_date = msg.get("date", 0)
                    if not msg_date or msg_date in seen_ids:
                        continue
                    seen_ids.add(msg_date)

                    sender = str(msg.get("from", "")).lower()
                    subject = str(msg.get("subject", ""))
                    body = str(msg.get("body", ""))
                    html = str(msg.get("html") or "")

                    content = "\n".join([sender, subject, body, html])

                    # Проверить, является ли это письмом от OpenAI
                    if "openai" not in sender and "openai" not in content.lower():
                        continue

                    # Извлечь код подтверждения
                    match = re.search(OTP_CODE_PATTERN, content)
                    if match:
                        code = match.group(1)
                        if callback:
                            callback({
                                "status": "found",
                                "email": email,
                                "code": code,
                                "message": "Код подтверждения найден"
                            })
                        return code

                if callback and check_count % 5 == 0:
                    callback({
                        "status": "waiting",
                        "email": email,
                        "check_count": check_count,
                        "message": f"Проверено {len(seen_ids)} писем, ожидание кода подтверждения..."
                    })

            except Exception as e:
                logger.debug(f"Ошибка при проверке писем: {e}")
                if callback:
                    callback({
                        "status": "error",
                        "email": email,
                        "error": str(e),
                        "message": "Ошибка при проверке писем"
                    })

            time.sleep(3)

        if callback:
            callback({
                "status": "timeout",
                "email": email,
                "message": "Таймаут ожидания кода подтверждения"
            })
        return None
