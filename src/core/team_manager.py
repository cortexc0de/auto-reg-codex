"""
Функция загрузки Team Manager
По аналогии с загрузкой CPA, прямое подключение без прокси
"""

import logging
from typing import List, Tuple
from datetime import datetime

from curl_cffi import requests as cffi_requests

from ..database.session import get_db
from ..database.models import Account
from ..config.settings import get_settings

logger = logging.getLogger(__name__)


def upload_to_team_manager(
    account: Account,
    api_url: str,
    api_key: str,
) -> Tuple[bool, str]:
    """
    Загрузка одного аккаунта в Team Manager (прямое подключение, без прокси)

    Returns:
        (флаг успеха, сообщение)
    """
    if not api_url:
        return False, "URL API Team Manager не настроен"
    if not api_key:
        return False, "API Key Team Manager не настроен"
    if not account.access_token:
        return False, "У аккаунта отсутствует access_token"

    url = api_url.rstrip("/") + "/api/accounts/import"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "import_type": "single",
        "email": account.email,
        "access_token": account.access_token or "",
        "session_token": account.session_token or "",
        "refresh_token": account.refresh_token or "",
        "client_id": account.client_id or "",
    }

    try:
        resp = cffi_requests.post(
            url,
            headers=headers,
            json=payload,
            proxies=None,
            timeout=30,
            impersonate="chrome110",
        )
        if resp.status_code in (200, 201):
            return True, "Загрузка успешна"
        error_msg = f"Ошибка загрузки: HTTP {resp.status_code}"
        try:
            detail = resp.json()
            if isinstance(detail, dict):
                error_msg = detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {resp.text[:200]}"
        return False, error_msg
    except Exception as e:
        logger.error(f"Исключение при загрузке в Team Manager: {e}")
        return False, f"Исключение при загрузке: {str(e)}"


def batch_upload_to_team_manager(
    account_ids: List[int],
    api_url: str,
    api_key: str,
) -> dict:
    """
    Пакетная загрузка аккаунтов в Team Manager

    Returns:
        Словарь со статистикой успехов/ошибок и подробностями
    """
    results = {
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "details": [],
    }

    with get_db() as db:
        for account_id in account_ids:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account:
                results["failed_count"] += 1
                results["details"].append(
                    {"id": account_id, "email": None, "success": False, "error": "Аккаунт не существует"}
                )
                continue

            if not account.access_token:
                results["skipped_count"] += 1
                results["details"].append(
                    {"id": account_id, "email": account.email, "success": False, "error": "Отсутствует токен"}
                )
                continue

            success, message = upload_to_team_manager(account, api_url, api_key)
            if success:
                results["success_count"] += 1
                results["details"].append(
                    {"id": account_id, "email": account.email, "success": True, "message": message}
                )
            else:
                results["failed_count"] += 1
                results["details"].append(
                    {"id": account_id, "email": account.email, "success": False, "error": message}
                )

    return results


def test_team_manager_connection(api_url: str, api_key: str) -> Tuple[bool, str]:
    """
    Тестирование соединения с Team Manager (прямое подключение)

    Returns:
        (флаг успеха, сообщение)
    """
    if not api_url:
        return False, "URL API не может быть пустым"
    if not api_key:
        return False, "API Key не может быть пустым"

    url = api_url.rstrip("/") + "/api/accounts/import"
    headers = {"X-API-Key": api_key}

    try:
        resp = cffi_requests.options(
            url,
            headers=headers,
            proxies=None,
            timeout=10,
            impersonate="chrome110",
        )
        if resp.status_code in (200, 204, 401, 403, 405):
            if resp.status_code == 401:
                return False, "Соединение установлено, но API Key недействителен"
            return True, "Тест соединения Team Manager пройден успешно"
        return False, f"Сервер вернул аномальный код состояния: {resp.status_code}"
    except cffi_requests.exceptions.ConnectionError as e:
        return False, f"Не удалось подключиться к серверу: {str(e)}"
    except cffi_requests.exceptions.Timeout:
        return False, "Время ожидания соединения истекло, проверьте сетевые настройки"
    except Exception as e:
        return False, f"Тест соединения не пройден: {str(e)}"
