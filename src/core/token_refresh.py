"""
Модуль обновления токенов
Поддерживает два способа обновления: Session Token и OAuth Refresh Token
"""

import logging
import json
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from curl_cffi import requests as cffi_requests

from ..config.settings import get_settings
from ..database.session import get_db
from ..database import crud
from ..database.models import Account

logger = logging.getLogger(__name__)


@dataclass
class TokenRefreshResult:
    """Результат обновления токена"""
    success: bool
    access_token: str = ""
    refresh_token: str = ""
    expires_at: Optional[datetime] = None
    error_message: str = ""


class TokenRefreshManager:
    """
    Менеджер обновления токенов
    Поддерживает два способа обновления:
    1. Обновление через Session Token (приоритетный)
    2. Обновление через OAuth Refresh Token
    """

    # Конечные точки OpenAI OAuth
    SESSION_URL = "https://chatgpt.com/api/auth/session"
    TOKEN_URL = "https://auth.openai.com/oauth/token"

    def __init__(self, proxy_url: Optional[str] = None):
        """
        Инициализация менеджера обновления токенов

        Args:
            proxy_url: URL прокси
        """
        self.proxy_url = proxy_url
        self.settings = get_settings()

    def _create_session(self) -> cffi_requests.Session:
        """Создание HTTP-сессии"""
        session = cffi_requests.Session(impersonate="chrome120", proxy=self.proxy_url)
        return session

    def refresh_by_session_token(self, session_token: str) -> TokenRefreshResult:
        """
        Обновление с помощью Session Token

        Args:
            session_token: Токен сессии

        Returns:
            TokenRefreshResult: Результат обновления
        """
        result = TokenRefreshResult(success=False)

        try:
            session = self._create_session()

            # Установка Cookie сессии
            session.cookies.set(
                "__Secure-next-auth.session-token",
                session_token,
                domain=".chatgpt.com",
                path="/"
            )

            # Запрос к конечной точке сессии
            response = session.get(
                self.SESSION_URL,
                headers={
                    "accept": "application/json",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=30
            )

            if response.status_code != 200:
                result.error_message = f"Не удалось обновить Session token: HTTP {response.status_code}"
                logger.warning(result.error_message)
                return result

            data = response.json()

            # Извлечение access_token
            access_token = data.get("accessToken")
            if not access_token:
                result.error_message = "Не удалось обновить Session token: accessToken не найден"
                logger.warning(result.error_message)
                return result

            # Извлечение времени истечения
            expires_at = None
            expires_str = data.get("expires")
            if expires_str:
                try:
                    expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                except:
                    pass

            result.success = True
            result.access_token = access_token
            result.expires_at = expires_at

            logger.info(f"Session token успешно обновлён, время истечения: {expires_at}")
            return result

        except Exception as e:
            result.error_message = f"Исключение при обновлении Session token: {str(e)}"
            logger.error(result.error_message)
            return result

    def refresh_by_oauth_token(
        self,
        refresh_token: str,
        client_id: Optional[str] = None
    ) -> TokenRefreshResult:
        """
        Обновление с помощью OAuth Refresh Token

        Args:
            refresh_token: Токен обновления OAuth
            client_id: OAuth Client ID

        Returns:
            TokenRefreshResult: Результат обновления
        """
        result = TokenRefreshResult(success=False)

        try:
            session = self._create_session()

            # Использование настроенного client_id или значения по умолчанию
            client_id = client_id or self.settings.openai_client_id

            # Формирование тела запроса
            token_data = {
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "redirect_uri": self.settings.openai_redirect_uri
            }

            response = session.post(
                self.TOKEN_URL,
                headers={
                    "content-type": "application/x-www-form-urlencoded",
                    "accept": "application/json"
                },
                data=token_data,
                timeout=30
            )

            if response.status_code != 200:
                result.error_message = f"Не удалось обновить OAuth token: HTTP {response.status_code}"
                logger.warning(f"{result.error_message}, ответ: {response.text[:200]}")
                return result

            data = response.json()

            # Извлечение токенов
            access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token", refresh_token)
            expires_in = data.get("expires_in", 3600)

            if not access_token:
                result.error_message = "Не удалось обновить OAuth token: access_token не найден"
                logger.warning(result.error_message)
                return result

            # Вычисление времени истечения
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            result.success = True
            result.access_token = access_token
            result.refresh_token = new_refresh_token
            result.expires_at = expires_at

            logger.info(f"OAuth token успешно обновлён, время истечения: {expires_at}")
            return result

        except Exception as e:
            result.error_message = f"Исключение при обновлении OAuth token: {str(e)}"
            logger.error(result.error_message)
            return result

    def refresh_account(self, account: Account) -> TokenRefreshResult:
        """
        Обновление токена аккаунта

        Приоритет:
        1. Обновление через Session Token
        2. Обновление через OAuth Refresh Token

        Args:
            account: Объект аккаунта

        Returns:
            TokenRefreshResult: Результат обновления
        """
        # Приоритетная попытка через Session Token
        if account.session_token:
            logger.info(f"Попытка обновления аккаунта {account.email} через Session Token")
            result = self.refresh_by_session_token(account.session_token)
            if result.success:
                return result
            logger.warning(f"Обновление через Session Token не удалось, попытка обновления через OAuth")

        # Попытка через OAuth Refresh Token
        if account.refresh_token:
            logger.info(f"Попытка обновления аккаунта {account.email} через OAuth Refresh Token")
            result = self.refresh_by_oauth_token(
                refresh_token=account.refresh_token,
                client_id=account.client_id
            )
            return result

        # Нет доступного способа обновления
        return TokenRefreshResult(
            success=False,
            error_message="У аккаунта нет доступного способа обновления (отсутствуют session_token и refresh_token)"
        )

    def validate_token(self, access_token: str) -> Tuple[bool, Optional[str]]:
        """
        Проверка действительности Access Token

        Args:
            access_token: Токен доступа

        Returns:
            Tuple[bool, Optional[str]]: (действителен ли, сообщение об ошибке)
        """
        try:
            session = self._create_session()

            # Вызов API OpenAI для проверки токена
            response = session.get(
                "https://chatgpt.com/backend-api/me",
                headers={
                    "authorization": f"Bearer {access_token}",
                    "accept": "application/json"
                },
                timeout=30
            )

            if response.status_code == 200:
                return True, None
            elif response.status_code == 401:
                return False, "Токен недействителен или истёк"
            elif response.status_code == 403:
                return False, "Аккаунт возможно заблокирован"
            else:
                return False, f"Ошибка проверки: HTTP {response.status_code}"

        except Exception as e:
            return False, f"Исключение при проверке: {str(e)}"


def refresh_account_token(account_id: int, proxy_url: Optional[str] = None) -> TokenRefreshResult:
    """
    Обновление токена указанного аккаунта и обновление базы данных

    Args:
        account_id: ID аккаунта
        proxy_url: URL прокси

    Returns:
        TokenRefreshResult: Результат обновления
    """
    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            return TokenRefreshResult(success=False, error_message="Аккаунт не существует")

        manager = TokenRefreshManager(proxy_url=proxy_url)
        result = manager.refresh_account(account)

        if result.success:
            # Обновление базы данных
            update_data = {
                "access_token": result.access_token,
                "last_refresh": datetime.utcnow()
            }

            if result.refresh_token:
                update_data["refresh_token"] = result.refresh_token

            if result.expires_at:
                update_data["expires_at"] = result.expires_at

            crud.update_account(db, account_id, **update_data)

        return result


def validate_account_token(account_id: int, proxy_url: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Проверка действительности токена указанного аккаунта

    Args:
        account_id: ID аккаунта
        proxy_url: URL прокси

    Returns:
        Tuple[bool, Optional[str]]: (действителен ли, сообщение об ошибке)
    """
    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            return False, "Аккаунт не существует"

        if not account.access_token:
            return False, "У аккаунта отсутствует access_token"

        manager = TokenRefreshManager(proxy_url=proxy_url)
        return manager.validate_token(account.access_token)
