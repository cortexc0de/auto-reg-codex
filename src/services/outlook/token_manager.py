"""
Менеджер токенов
Поддержка нескольких конечных точек Microsoft Token, автоматический выбор подходящей
"""

import json
import logging
import threading
import time
from typing import Dict, Optional, Any

from curl_cffi import requests as _requests

from .base import ProviderType, TokenEndpoint, TokenInfo
from .account import OutlookAccount


logger = logging.getLogger(__name__)


# Конфигурация Scope для каждого провайдера
PROVIDER_SCOPES = {
    ProviderType.IMAP_OLD: "",  # Старый IMAP не требует специального scope
    ProviderType.IMAP_NEW: "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
    ProviderType.GRAPH_API: "https://graph.microsoft.com/.default",
}

# Конечные точки Token для каждого провайдера
PROVIDER_TOKEN_URLS = {
    ProviderType.IMAP_OLD: TokenEndpoint.LIVE.value,
    ProviderType.IMAP_NEW: TokenEndpoint.CONSUMERS.value,
    ProviderType.GRAPH_API: TokenEndpoint.COMMON.value,
}


class TokenManager:
    """
    Менеджер токенов
    Поддержка получения и кэширования Token через несколько конечных точек
    """

    # Кэш Token: key = (email, provider_type) -> TokenInfo
    _token_cache: Dict[tuple, TokenInfo] = {}
    _cache_lock = threading.Lock()

    # Таймаут по умолчанию
    DEFAULT_TIMEOUT = 30
    # Время опережающего обновления Token (в секундах)
    REFRESH_BUFFER = 120

    def __init__(
        self,
        account: OutlookAccount,
        provider_type: ProviderType,
        proxy_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Инициализация менеджера токенов

        Args:
            account: Учётная запись Outlook
            provider_type: Тип провайдера
            proxy_url: URL прокси (опционально)
            timeout: Таймаут запроса
        """
        self.account = account
        self.provider_type = provider_type
        self.proxy_url = proxy_url
        self.timeout = timeout

        # Получить конечную точку и Scope
        self.token_url = PROVIDER_TOKEN_URLS.get(provider_type, TokenEndpoint.LIVE.value)
        self.scope = PROVIDER_SCOPES.get(provider_type, "")

    def get_cached_token(self) -> Optional[TokenInfo]:
        """Получить кэшированный Token"""
        cache_key = (self.account.email.lower(), self.provider_type)
        with self._cache_lock:
            token = self._token_cache.get(cache_key)
            if token and not token.is_expired(self.REFRESH_BUFFER):
                return token
        return None

    def set_cached_token(self, token: TokenInfo):
        """Кэшировать Token"""
        cache_key = (self.account.email.lower(), self.provider_type)
        with self._cache_lock:
            self._token_cache[cache_key] = token

    def clear_cache(self):
        """Очистить кэш"""
        cache_key = (self.account.email.lower(), self.provider_type)
        with self._cache_lock:
            self._token_cache.pop(cache_key, None)

    def get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """
        Получить Access Token

        Args:
            force_refresh: Принудительное обновление

        Returns:
            Строка Access Token, None при неудаче
        """
        # Проверить кэш
        if not force_refresh:
            cached = self.get_cached_token()
            if cached:
                logger.debug(f"[{self.account.email}] Используется кэшированный Token ({self.provider_type.value})")
                return cached.access_token

        # Обновить Token
        try:
            token = self._refresh_token()
            if token:
                self.set_cached_token(token)
                return token.access_token
        except Exception as e:
            logger.error(f"[{self.account.email}] Не удалось получить Token ({self.provider_type.value}): {e}")

        return None

    def _refresh_token(self) -> Optional[TokenInfo]:
        """
        Обновить Token

        Returns:
            Объект TokenInfo, None при неудаче
        """
        if not self.account.client_id or not self.account.refresh_token:
            raise ValueError("Отсутствует client_id или refresh_token")

        logger.debug(f"[{self.account.email}] Обновление Token ({self.provider_type.value})...")
        logger.debug(f"[{self.account.email}] Token URL: {self.token_url}")

        # Построение тела запроса
        data = {
            "client_id": self.account.client_id,
            "refresh_token": self.account.refresh_token,
            "grant_type": "refresh_token",
        }

        # Добавить Scope (при необходимости)
        if self.scope:
            data["scope"] = self.scope

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        proxies = None
        if self.proxy_url:
            proxies = {"http": self.proxy_url, "https": self.proxy_url}

        try:
            resp = _requests.post(
                self.token_url,
                data=data,
                headers=headers,
                proxies=proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )

            if resp.status_code != 200:
                error_body = resp.text
                logger.error(f"[{self.account.email}] Обновление Token не удалось: HTTP {resp.status_code}")
                logger.debug(f"[{self.account.email}] Ответ об ошибке: {error_body[:500]}")

                if "service abuse" in error_body.lower():
                    logger.warning(f"[{self.account.email}] Учётная запись возможно заблокирована")
                elif "invalid_grant" in error_body.lower():
                    logger.warning(f"[{self.account.email}] Refresh Token недействителен")

                return None

            response_data = resp.json()

            # Разбор ответа
            token = TokenInfo.from_response(response_data, self.scope)
            logger.info(
                f"[{self.account.email}] Token успешно обновлён ({self.provider_type.value}), "
                f"срок действия {int(token.expires_at - time.time())} секунд"
            )
            return token

        except json.JSONDecodeError as e:
            logger.error(f"[{self.account.email}] Ошибка разбора JSON: {e}")
            return None

        except Exception as e:
            logger.error(f"[{self.account.email}] Неизвестная ошибка: {e}")
            return None

    @classmethod
    def clear_all_cache(cls):
        """Очистить весь кэш Token"""
        with cls._cache_lock:
            cls._token_cache.clear()
            logger.info("Весь кэш Token очищен")

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Получить статистику кэша"""
        with cls._cache_lock:
            return {
                "cache_size": len(cls._token_cache),
                "entries": [
                    {
                        "email": key[0],
                        "provider": key[1].value,
                    }
                    for key in cls._token_cache.keys()
                ],
            }


def create_token_manager(
    account: OutlookAccount,
    provider_type: ProviderType,
    proxy_url: Optional[str] = None,
    timeout: int = TokenManager.DEFAULT_TIMEOUT,
) -> TokenManager:
    """
    Фабричная функция создания менеджера токенов

    Args:
        account: Учётная запись Outlook
        provider_type: Тип провайдера
        proxy_url: URL прокси
        timeout: Таймаут

    Returns:
        Экземпляр TokenManager
    """
    return TokenManager(account, provider_type, proxy_url, timeout)
