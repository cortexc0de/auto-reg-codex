"""
Функция загрузки CPA (Codex Protocol API)
"""

import json
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

from curl_cffi import requests as cffi_requests
from curl_cffi import CurlMime

from ..database.session import get_db
from ..database.models import Account
from ..config.settings import get_settings

logger = logging.getLogger(__name__)


def generate_token_json(account: Account) -> dict:
    """
    Генерация Token JSON в формате CPA

    Args:
        account: Экземпляр модели аккаунта

    Returns:
        Словарь токена в формате CPA
    """
    return {
        "type": "codex",
        "email": account.email,
        "expired": account.expires_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if account.expires_at else "",
        "id_token": account.id_token or "",
        "account_id": account.account_id or "",
        "access_token": account.access_token or "",
        "last_refresh": account.last_refresh.strftime("%Y-%m-%dT%H:%M:%S+08:00") if account.last_refresh else "",
        "refresh_token": account.refresh_token or "",
    }


def upload_to_cpa(token_data: dict, proxy: str = None) -> Tuple[bool, str]:
    """
    Загрузка одного аккаунта на платформу управления CPA (без прокси)

    Args:
        token_data: Данные Token JSON
        proxy: Зарезервированный параметр, не используется (загрузка CPA всегда выполняется напрямую)

    Returns:
        (флаг успеха, сообщение или информация об ошибке)
    """
    settings = get_settings()

    if not settings.cpa_enabled:
        return False, "Загрузка CPA не включена"

    if not settings.cpa_api_url:
        return False, "URL API CPA не настроен"

    api_url = settings.cpa_api_url.rstrip("/")
    upload_url = f"{api_url}/v0/management/auth-files"

    filename = f"{token_data['email']}.json"
    file_content = json.dumps(token_data, ensure_ascii=False, indent=2).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {settings.cpa_api_token.get_secret_value()}",
    }

    try:
        mime = CurlMime()
        mime.addpart(
            name="file",
            data=file_content,
            filename=filename,
            content_type="application/json",
        )

        response = cffi_requests.post(
            upload_url,
            multipart=mime,
            headers=headers,
            proxies=None,
            timeout=30,
            impersonate="chrome110",
        )

        if response.status_code in (200, 201):
            return True, "Загрузка успешна"

        error_msg = f"Ошибка загрузки: HTTP {response.status_code}"
        try:
            error_detail = response.json()
            if isinstance(error_detail, dict):
                error_msg = error_detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {response.text[:200]}"
        return False, error_msg

    except Exception as e:
        logger.error(f"Исключение при загрузке CPA: {e}")
        return False, f"Исключение при загрузке: {str(e)}"


def batch_upload_to_cpa(account_ids: List[int], proxy: str = None) -> dict:
    """
    Пакетная загрузка аккаунтов на платформу управления CPA

    Args:
        account_ids: Список ID аккаунтов
        proxy: Необязательный URL прокси

    Returns:
        Словарь со статистикой успехов/ошибок и подробностями
    """
    results = {
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "details": []
    }

    with get_db() as db:
        for account_id in account_ids:
            account = db.query(Account).filter(Account.id == account_id).first()

            if not account:
                results["failed_count"] += 1
                results["details"].append({
                    "id": account_id,
                    "email": None,
                    "success": False,
                    "error": "Аккаунт не существует"
                })
                continue

            # Проверка наличия токена
            if not account.access_token:
                results["skipped_count"] += 1
                results["details"].append({
                    "id": account_id,
                    "email": account.email,
                    "success": False,
                    "error": "Отсутствует токен"
                })
                continue

            # Генерация Token JSON
            token_data = generate_token_json(account)

            # Загрузка
            success, message = upload_to_cpa(token_data, proxy)

            if success:
                # Обновление статуса в базе данных
                account.cpa_uploaded = True
                account.cpa_uploaded_at = datetime.utcnow()
                db.commit()

                results["success_count"] += 1
                results["details"].append({
                    "id": account_id,
                    "email": account.email,
                    "success": True,
                    "message": message
                })
            else:
                results["failed_count"] += 1
                results["details"].append({
                    "id": account_id,
                    "email": account.email,
                    "success": False,
                    "error": message
                })

    return results


def test_cpa_connection(api_url: str, api_token: str, proxy: str = None) -> Tuple[bool, str]:
    """
    Тестирование соединения с CPA (без прокси)

    Args:
        api_url: URL API CPA
        api_token: Токен API CPA
        proxy: Зарезервированный параметр, не используется (CPA всегда подключается напрямую)

    Returns:
        (флаг успеха, сообщение)
    """
    if not api_url:
        return False, "URL API не может быть пустым"

    if not api_token:
        return False, "Токен API не может быть пустым"

    api_url = api_url.rstrip("/")
    test_url = f"{api_url}/v0/management/auth-files"
    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        response = cffi_requests.options(
            test_url,
            headers=headers,
            proxies=None,
            timeout=10,
            impersonate="chrome110",
        )

        if response.status_code in (200, 204, 401, 403, 405):
            if response.status_code == 401:
                return False, "Соединение установлено, но токен API недействителен"
            return True, "Тест соединения CPA пройден успешно"

        return False, f"Сервер вернул аномальный код состояния: {response.status_code}"

    except cffi_requests.exceptions.ConnectionError as e:
        return False, f"Не удалось подключиться к серверу: {str(e)}"
    except cffi_requests.exceptions.Timeout:
        return False, "Время ожидания соединения истекло, проверьте сетевые настройки"
    except Exception as e:
        return False, f"Тест соединения не пройден: {str(e)}"
