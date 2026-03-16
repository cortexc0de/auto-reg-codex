"""
Реализация почтового сервиса с пользовательским доменом
На основе REST API интерфейса из email.md
"""

import re
import time
import json
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

from .base import BaseEmailService, EmailServiceError, EmailServiceType
from ..core.http_client import HTTPClient, RequestConfig
from ..config.constants import OTP_CODE_PATTERN


logger = logging.getLogger(__name__)


class CustomDomainEmailService(BaseEmailService):
    """
    Почтовый сервис с пользовательским доменом
    На основе REST API интерфейса
    """

    def __init__(self, config: Dict[str, Any] = None, name: str = None):
        """
        Инициализация почтового сервиса с пользовательским доменом

        Args:
            config: Словарь конфигурации, поддерживает следующие ключи:
                - base_url: Базовый URL API (обязательно)
                - api_key: API-ключ (обязательно)
                - api_key_header: Имя заголовка API-ключа (по умолчанию: X-API-Key)
                - timeout: Таймаут запроса (по умолчанию: 30)
                - max_retries: Максимальное количество повторных попыток (по умолчанию: 3)
                - proxy_url: URL прокси
                - default_domain: Домен по умолчанию
                - default_expiry: Срок действия по умолчанию (в миллисекундах)
            name: Название сервиса
        """
        super().__init__(EmailServiceType.CUSTOM_DOMAIN, name)

        # Проверка обязательных параметров конфигурации
        required_keys = ["base_url", "api_key"]
        missing_keys = [key for key in required_keys if key not in (config or {})]

        if missing_keys:
            raise ValueError(f"Отсутствуют обязательные параметры конфигурации: {missing_keys}")

        # Конфигурация по умолчанию
        default_config = {
            "base_url": "",
            "api_key": "",
            "api_key_header": "X-API-Key",
            "timeout": 30,
            "max_retries": 3,
            "proxy_url": None,
            "default_domain": None,
            "default_expiry": 3600000,  # 1 час
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
        self._emails_cache: Dict[str, Dict[str, Any]] = {}
        self._last_config_check: float = 0
        self._cached_config: Optional[Dict[str, Any]] = None

    def _get_headers(self) -> Dict[str, str]:
        """Получить заголовки API-запроса"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # Добавить API-ключ
        api_key_header = self.config.get("api_key_header", "X-API-Key")
        headers[api_key_header] = self.config["api_key"]

        return headers

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Отправить API-запрос

        Args:
            method: HTTP-метод
            endpoint: Конечная точка API
            **kwargs: Параметры запроса

        Returns:
            JSON-данные ответа

        Raises:
            EmailServiceError: Ошибка запроса
        """
        url = urljoin(self.config["base_url"], endpoint)

        # Добавить заголовки по умолчанию
        kwargs.setdefault("headers", {})
        kwargs["headers"].update(self._get_headers())

        try:
            # Для POST-запросов отключить автоматическое перенаправление, обработать вручную для сохранения метода POST (избежать перехода HTTP->HTTPS с преобразованием в GET)
            if method.upper() == "POST":
                kwargs["allow_redirects"] = False
                response = self.http_client.request(method, url, **kwargs)
                # Обработка перенаправлений
                max_redirects = 5
                redirect_count = 0
                while response.status_code in (301, 302, 303, 307, 308) and redirect_count < max_redirects:
                    location = response.headers.get("Location", "")
                    if not location:
                        break
                    import urllib.parse as _urlparse
                    redirect_url = _urlparse.urljoin(url, location)
                    # 307/308 сохраняют POST, остальные (301/302/303) преобразуются в GET
                    if response.status_code in (307, 308):
                        redirect_method = method
                        redirect_kwargs = kwargs
                    else:
                        redirect_method = "GET"
                        # GET не передаёт тело запроса
                        redirect_kwargs = {k: v for k, v in kwargs.items() if k not in ("json", "data")}
                    response = self.http_client.request(redirect_method, redirect_url, **redirect_kwargs)
                    url = redirect_url
                    redirect_count += 1
            else:
                response = self.http_client.request(method, url, **kwargs)

            if response.status_code >= 400:
                error_msg = f"API-запрос не удался: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = f"{error_msg} - {error_data}"
                except:
                    error_msg = f"{error_msg} - {response.text[:200]}"

                self.update_status(False, EmailServiceError(error_msg))
                raise EmailServiceError(error_msg)

            # Разбор ответа
            try:
                return response.json()
            except json.JSONDecodeError:
                return {"raw_response": response.text}

        except Exception as e:
            self.update_status(False, e)
            if isinstance(e, EmailServiceError):
                raise
            raise EmailServiceError(f"API-запрос не удался: {method} {endpoint} - {e}")

    def get_config(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Получить конфигурацию системы

        Args:
            force_refresh: Принудительно обновить кэш

        Returns:
            Информация о конфигурации
        """
        # Проверить кэш
        if not force_refresh and self._cached_config and time.time() - self._last_config_check < 300:
            return self._cached_config

        try:
            response = self._make_request("GET", "/api/config")
            self._cached_config = response
            self._last_config_check = time.time()
            self.update_status(True)
            return response
        except Exception as e:
            logger.warning(f"Не удалось получить конфигурацию: {e}")
            return {}

    def create_email(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Создать временный почтовый ящик

        Args:
            config: Параметры конфигурации:
                - name: Префикс почтового ящика (опционально)
                - expiryTime: Срок действия (в миллисекундах) (опционально)
                - domain: Домен почтового ящика (опционально)

        Returns:
            Словарь с информацией о почте:
            - email: Почтовый адрес
            - service_id: ID почтового ящика
            - id: ID почтового ящика (то же, что service_id)
            - expiry: Информация о сроке действия
        """
        # Получить конфигурацию по умолчанию
        sys_config = self.get_config()
        default_domain = self.config.get("default_domain")
        if not default_domain and sys_config.get("emailDomains"):
            # Использовать первый домен из системной конфигурации
            domains = sys_config["emailDomains"].split(",")
            default_domain = domains[0].strip() if domains else None

        # Построить параметры запроса
        request_config = config or {}
        create_data = {
            "name": request_config.get("name", ""),
            "expiryTime": request_config.get("expiryTime", self.config.get("default_expiry", 3600000)),
            "domain": request_config.get("domain", default_domain),
        }

        # Удалить пустые значения
        create_data = {k: v for k, v in create_data.items() if v is not None and v != ""}

        try:
            response = self._make_request("POST", "/api/emails/generate", json=create_data)

            email = response.get("email", "").strip()
            email_id = response.get("id", "").strip()

            if not email or not email_id:
                raise EmailServiceError("API вернул неполные данные")

            email_info = {
                "email": email,
                "service_id": email_id,
                "id": email_id,
                "created_at": time.time(),
                "expiry": create_data.get("expiryTime"),
                "domain": create_data.get("domain"),
                "raw_response": response,
            }

            # Кэширование информации о почтовом ящике
            self._emails_cache[email_id] = email_info

            logger.info(f"Успешно создан почтовый ящик с пользовательским доменом: {email} (ID: {email_id})")
            self.update_status(True)
            return email_info

        except Exception as e:
            self.update_status(False, e)
            if isinstance(e, EmailServiceError):
                raise
            raise EmailServiceError(f"Не удалось создать почтовый ящик: {e}")

    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = 120,
        pattern: str = OTP_CODE_PATTERN,
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        """
        Получить код подтверждения из почтового ящика с пользовательским доменом

        Args:
            email: Почтовый адрес
            email_id: ID почтового ящика (если не указан, ищется в кэше)
            timeout: Таймаут (в секундах)
            pattern: Регулярное выражение для кода подтверждения
            otp_sent_at: Временная метка отправки OTP (сервис с пользовательским доменом не использует этот параметр)

        Returns:
            Строка с кодом подтверждения, None если таймаут или код не найден
        """
        # Поиск ID почтового ящика
        target_email_id = email_id
        if not target_email_id:
            # Поиск в кэше
            for eid, info in self._emails_cache.items():
                if info.get("email") == email:
                    target_email_id = eid
                    break

        if not target_email_id:
            logger.warning(f"Не найден ID для почтового ящика {email}, невозможно получить код подтверждения")
            return None

        logger.info(f"Получение кода подтверждения из почтового ящика с пользовательским доменом {email}...")

        start_time = time.time()
        seen_message_ids = set()

        while time.time() - start_time < timeout:
            try:
                # Получить список писем
                response = self._make_request("GET", f"/api/emails/{target_email_id}")

                messages = response.get("messages", [])
                if not isinstance(messages, list):
                    time.sleep(3)
                    continue

                for message in messages:
                    message_id = message.get("id")
                    if not message_id or message_id in seen_message_ids:
                        continue

                    seen_message_ids.add(message_id)

                    # Проверить, является ли это целевым письмом
                    sender = str(message.get("from_address", "")).lower()
                    subject = str(message.get("subject", ""))

                    # Получить содержимое письма
                    message_content = self._get_message_content(target_email_id, message_id)
                    if not message_content:
                        continue

                    content = f"{sender} {subject} {message_content}"

                    # Проверить, является ли это письмом от OpenAI
                    if "openai" not in sender and "openai" not in content.lower():
                        continue

                    # Извлечь код подтверждения
                    match = re.search(pattern, content)
                    if match:
                        code = match.group(1)
                        logger.info(f"Найден код подтверждения из почтового ящика с пользовательским доменом {email}: {code}")
                        self.update_status(True)
                        return code

            except Exception as e:
                logger.debug(f"Ошибка при проверке писем: {e}")

            # Подождать перед следующей проверкой
            time.sleep(3)

        logger.warning(f"Таймаут ожидания кода подтверждения: {email}")
        return None

    def _get_message_content(self, email_id: str, message_id: str) -> Optional[str]:
        """Получить содержимое письма"""
        try:
            response = self._make_request("GET", f"/api/emails/{email_id}/{message_id}")
            message = response.get("message", {})

            # Предпочтительно использовать текстовое содержимое, затем HTML
            content = message.get("content", "")
            if not content:
                html = message.get("html", "")
                if html:
                    # Простое удаление HTML-тегов
                    content = re.sub(r"<[^>]+>", " ", html)

            return content
        except Exception as e:
            logger.debug(f"Не удалось получить содержимое письма: {e}")
            return None

    def list_emails(self, cursor: str = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Показать все почтовые ящики

        Args:
            cursor: Курсор пагинации
            **kwargs: Другие параметры

        Returns:
            Список почтовых ящиков
        """
        params = {}
        if cursor:
            params["cursor"] = cursor

        try:
            response = self._make_request("GET", "/api/emails", params=params)
            emails = response.get("emails", [])

            # Обновить кэш
            for email_info in emails:
                email_id = email_info.get("id")
                if email_id:
                    self._emails_cache[email_id] = email_info

            self.update_status(True)
            return emails
        except Exception as e:
            logger.warning(f"Не удалось получить список почтовых ящиков: {e}")
            self.update_status(False, e)
            return []

    def delete_email(self, email_id: str) -> bool:
        """
        Удалить почтовый ящик

        Args:
            email_id: ID почтового ящика

        Returns:
            Успешно ли удаление
        """
        try:
            response = self._make_request("DELETE", f"/api/emails/{email_id}")
            success = response.get("success", False)

            if success:
                # Удалить из кэша
                self._emails_cache.pop(email_id, None)
                logger.info(f"Почтовый ящик успешно удалён: {email_id}")
            else:
                logger.warning(f"Не удалось удалить почтовый ящик: {email_id}")

            self.update_status(success)
            return success

        except Exception as e:
            logger.error(f"Не удалось удалить почтовый ящик: {email_id} - {e}")
            self.update_status(False, e)
            return False

    def check_health(self) -> bool:
        """Проверить доступность почтового сервиса с пользовательским доменом"""
        try:
            # Попытаться получить конфигурацию
            config = self.get_config(force_refresh=True)
            if config:
                logger.debug(f"Проверка здоровья почтового сервиса с пользовательским доменом пройдена, конфигурация: {config.get('defaultRole', 'N/A')}")
                self.update_status(True)
                return True
            else:
                logger.warning("Проверка здоровья почтового сервиса с пользовательским доменом не пройдена: конфигурация пуста")
                self.update_status(False, EmailServiceError("Конфигурация пуста"))
                return False
        except Exception as e:
            logger.warning(f"Проверка здоровья почтового сервиса с пользовательским доменом не пройдена: {e}")
            self.update_status(False, e)
            return False

    def get_email_messages(self, email_id: str, cursor: str = None) -> List[Dict[str, Any]]:
        """
        Получить список писем в почтовом ящике

        Args:
            email_id: ID почтового ящика
            cursor: Курсор пагинации

        Returns:
            Список писем
        """
        params = {}
        if cursor:
            params["cursor"] = cursor

        try:
            response = self._make_request("GET", f"/api/emails/{email_id}", params=params)
            messages = response.get("messages", [])
            self.update_status(True)
            return messages
        except Exception as e:
            logger.error(f"Не удалось получить список писем: {email_id} - {e}")
            self.update_status(False, e)
            return []

    def get_message_detail(self, email_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить подробности письма

        Args:
            email_id: ID почтового ящика
            message_id: ID письма

        Returns:
            Подробности письма
        """
        try:
            response = self._make_request("GET", f"/api/emails/{email_id}/{message_id}")
            message = response.get("message")
            self.update_status(True)
            return message
        except Exception as e:
            logger.error(f"Не удалось получить подробности письма: {email_id}/{message_id} - {e}")
            self.update_status(False, e)
            return None

    def create_email_share(self, email_id: str, expires_in: int = 86400000) -> Optional[Dict[str, Any]]:
        """
        Создать ссылку для общего доступа к почтовому ящику

        Args:
            email_id: ID почтового ящика
            expires_in: Срок действия (в миллисекундах)

        Returns:
            Информация об общем доступе
        """
        try:
            response = self._make_request(
                "POST",
                f"/api/emails/{email_id}/share",
                json={"expiresIn": expires_in}
            )
            self.update_status(True)
            return response
        except Exception as e:
            logger.error(f"Не удалось создать ссылку для общего доступа к почтовому ящику: {email_id} - {e}")
            self.update_status(False, e)
            return None

    def create_message_share(
        self,
        email_id: str,
        message_id: str,
        expires_in: int = 86400000
    ) -> Optional[Dict[str, Any]]:
        """
        Создать ссылку для общего доступа к письму

        Args:
            email_id: ID почтового ящика
            message_id: ID письма
            expires_in: Срок действия (в миллисекундах)

        Returns:
            Информация об общем доступе
        """
        try:
            response = self._make_request(
                "POST",
                f"/api/emails/{email_id}/messages/{message_id}/share",
                json={"expiresIn": expires_in}
            )
            self.update_status(True)
            return response
        except Exception as e:
            logger.error(f"Не удалось создать ссылку для общего доступа к письму: {email_id}/{message_id} - {e}")
            self.update_status(False, e)
            return None

    def get_service_info(self) -> Dict[str, Any]:
        """Получить информацию о сервисе"""
        config = self.get_config()
        return {
            "service_type": self.service_type.value,
            "name": self.name,
            "base_url": self.config["base_url"],
            "default_domain": self.config.get("default_domain"),
            "system_config": config,
            "cached_emails_count": len(self._emails_cache),
            "status": self.status.value,
        }
