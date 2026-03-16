"""
Обёртка HTTP-клиента
Обёртка HTTP-запросов на основе curl_cffi с поддержкой прокси и обработкой ошибок
"""

import time
import json
from typing import Optional, Dict, Any, Union, Tuple
from dataclasses import dataclass
import logging

from curl_cffi import requests as cffi_requests
from curl_cffi.requests import Session, Response

from ..config.constants import ERROR_MESSAGES
from ..config.settings import get_settings


logger = logging.getLogger(__name__)


@dataclass
class RequestConfig:
    """Настройка HTTP-запроса"""
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    impersonate: str = "chrome"
    verify_ssl: bool = True
    follow_redirects: bool = True


class HTTPClientError(Exception):
    """Исключение HTTP-клиента"""
    pass


class HTTPClient:
    """
    Обёртка HTTP-клиента
    Поддержка прокси, повторных попыток, обработки ошибок и управления сессиями
    """

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        config: Optional[RequestConfig] = None,
        session: Optional[Session] = None
    ):
        """
        Инициализация HTTP-клиента

        Args:
            proxy_url: URL прокси, например "http://127.0.0.1:7890"
            config: настройка запроса
            session: переиспользуемый объект сессии
        """
        self.proxy_url = proxy_url
        self.config = config or RequestConfig()
        self._session = session

    @property
    def proxies(self) -> Optional[Dict[str, str]]:
        """Получение настройки прокси"""
        if not self.proxy_url:
            return None
        return {
            "http": self.proxy_url,
            "https": self.proxy_url,
        }

    @property
    def session(self) -> Session:
        """Получение объекта сессии (синглтон)"""
        if self._session is None:
            self._session = Session(
                proxies=self.proxies,
                impersonate=self.config.impersonate,
                verify=self.config.verify_ssl,
                timeout=self.config.timeout
            )
        return self._session

    def request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Response:
        """
        Отправка HTTP-запроса

        Args:
            method: HTTP-метод (GET, POST, PUT, DELETE и т.д.)
            url: URL запроса
            **kwargs: другие параметры запроса

        Returns:
            Объект Response

        Raises:
            HTTPClientError: запрос не удался
        """
        # Установка параметров по умолчанию
        kwargs.setdefault("timeout", self.config.timeout)
        kwargs.setdefault("allow_redirects", self.config.follow_redirects)

        # Добавление настройки прокси
        if self.proxies and "proxies" not in kwargs:
            kwargs["proxies"] = self.proxies

        last_exception = None
        for attempt in range(self.config.max_retries):
            try:
                response = self.session.request(method, url, **kwargs)

                # Проверка кода ответа
                if response.status_code >= 400:
                    logger.warning(
                        f"HTTP {response.status_code} for {method} {url}"
                        f" (attempt {attempt + 1}/{self.config.max_retries})"
                    )

                    # Если серверная ошибка, повторить попытку
                    if response.status_code >= 500 and attempt < self.config.max_retries - 1:
                        time.sleep(self.config.retry_delay * (attempt + 1))
                        continue

                return response

            except (cffi_requests.RequestsError, ConnectionError, TimeoutError) as e:
                last_exception = e
                logger.warning(
                    f"Запрос не удался: {method} {url} (attempt {attempt + 1}/{self.config.max_retries}): {e}"
                )

                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    break

        raise HTTPClientError(
            f"Запрос не удался, достигнуто максимальное количество повторных попыток: {method} {url} - {last_exception}"
        )

    def get(self, url: str, **kwargs) -> Response:
        """Отправка GET-запроса"""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, data: Any = None, json: Any = None, **kwargs) -> Response:
        """Отправка POST-запроса"""
        return self.request("POST", url, data=data, json=json, **kwargs)

    def put(self, url: str, data: Any = None, json: Any = None, **kwargs) -> Response:
        """Отправка PUT-запроса"""
        return self.request("PUT", url, data=data, json=json, **kwargs)

    def delete(self, url: str, **kwargs) -> Response:
        """Отправка DELETE-запроса"""
        return self.request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs) -> Response:
        """Отправка HEAD-запроса"""
        return self.request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs) -> Response:
        """Отправка OPTIONS-запроса"""
        return self.request("OPTIONS", url, **kwargs)

    def patch(self, url: str, data: Any = None, json: Any = None, **kwargs) -> Response:
        """Отправка PATCH-запроса"""
        return self.request("PATCH", url, data=data, json=json, **kwargs)

    def download_file(self, url: str, filepath: str, chunk_size: int = 8192) -> None:
        """
        Скачивание файла

        Args:
            url: URL файла
            filepath: путь сохранения
            chunk_size: размер блока

        Raises:
            HTTPClientError: скачивание не удалось
        """
        try:
            response = self.get(url, stream=True)
            response.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)

        except Exception as e:
            raise HTTPClientError(f"Не удалось скачать файл: {url} - {e}")

    def check_proxy(self, test_url: str = "https://httpbin.org/ip") -> bool:
        """
        Проверка доступности прокси

        Args:
            test_url: тестовый URL

        Returns:
            bool: доступен ли прокси
        """
        if not self.proxy_url:
            return False

        try:
            response = self.get(test_url, timeout=10)
            return response.status_code == 200
        except Exception:
            return False

    def close(self):
        """Закрытие сессии"""
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class OpenAIHTTPClient(HTTPClient):
    """
    Специализированный HTTP-клиент для OpenAI
    Содержит методы запросов, специфичные для OpenAI API
    """

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        config: Optional[RequestConfig] = None
    ):
        """
        Инициализация HTTP-клиента OpenAI

        Args:
            proxy_url: URL прокси
            config: настройка запроса
        """
        super().__init__(proxy_url, config)

        # Настройки по умолчанию, специфичные для OpenAI
        if config is None:
            self.config.timeout = 30
            self.config.max_retries = 3

        # Заголовки запроса по умолчанию
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

    def check_ip_location(self) -> Tuple[bool, Optional[str]]:
        """
        Проверка геолокации IP

        Returns:
            Tuple[поддерживается ли, информация о местоположении]
        """
        try:
            response = self.get("https://cloudflare.com/cdn-cgi/trace", timeout=10)
            trace_text = response.text

            # Разбор информации о местоположении
            import re
            loc_match = re.search(r"loc=([A-Z]+)", trace_text)
            loc = loc_match.group(1) if loc_match else None

            # Проверка поддержки
            if loc in ["CN", "HK", "MO", "TW"]:
                return False, loc
            return True, loc

        except Exception as e:
            logger.error(f"Ошибка проверки геолокации IP: {e}")
            return False, None

    def send_openai_request(
        self,
        endpoint: str,
        method: str = "POST",
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Отправка запроса к API OpenAI

        Args:
            endpoint: конечная точка API
            method: HTTP-метод
            data: данные формы
            json_data: JSON-данные
            headers: заголовки запроса
            **kwargs: другие параметры

        Returns:
            JSON-данные ответа

        Raises:
            HTTPClientError: запрос не удался
        """
        # Объединение заголовков запроса
        request_headers = self.default_headers.copy()
        if headers:
            request_headers.update(headers)

        # Установка Content-Type
        if json_data is not None and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/json"
        elif data is not None and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            response = self.request(
                method,
                endpoint,
                data=data,
                json=json_data,
                headers=request_headers,
                **kwargs
            )

            # Проверка кода ответа
            response.raise_for_status()

            # Попытка разбора JSON
            try:
                return response.json()
            except json.JSONDecodeError:
                return {"raw_response": response.text}

        except cffi_requests.RequestsError as e:
            raise HTTPClientError(f"Запрос к OpenAI не удался: {endpoint} - {e}")

    def check_sentinel(self, did: str, proxies: Optional[Dict] = None) -> Optional[str]:
        """
        Проверка перехвата Sentinel

        Args:
            did: Device ID
            proxies: настройка прокси

        Returns:
            Sentinel token или None
        """
        from ..config.constants import OPENAI_API_ENDPOINTS

        try:
            sen_req_body = f'{{"p":"","id":"{did}","flow":"authorize_continue"}}'

            response = self.post(
                OPENAI_API_ENDPOINTS["sentinel"],
                headers={
                    "origin": "https://sentinel.openai.com",
                    "referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html?sv=20260219f9f6",
                    "content-type": "text/plain;charset=UTF-8",
                },
                data=sen_req_body,
            )

            if response.status_code == 200:
                return response.json().get("token")
            else:
                logger.warning(f"Проверка Sentinel не удалась: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Исключение при проверке Sentinel: {e}")
            return None


def create_http_client(
    proxy_url: Optional[str] = None,
    config: Optional[RequestConfig] = None
) -> HTTPClient:
    """
    Фабричная функция создания HTTP-клиента

    Args:
        proxy_url: URL прокси
        config: настройка запроса

    Returns:
        Экземпляр HTTPClient
    """
    return HTTPClient(proxy_url, config)


def create_openai_client(
    proxy_url: Optional[str] = None,
    config: Optional[RequestConfig] = None
) -> OpenAIHTTPClient:
    """
    Фабричная функция создания HTTP-клиента OpenAI

    Args:
        proxy_url: URL прокси
        config: настройка запроса

    Returns:
        Экземпляр OpenAIHTTPClient
    """
    return OpenAIHTTPClient(proxy_url, config)