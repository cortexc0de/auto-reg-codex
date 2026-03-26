"""
API маршруты для управления почтовыми ящиками (mailbox dashboard)
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ...config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class MailboxCreateRequest(BaseModel):
    service: str


class MailboxDeleteRequest(BaseModel):
    service: str
    mailbox_id: str


def _get_service_config(service: str):
    """Возвращает (base_url, token) для указанного сервиса."""
    settings = get_settings()
    if service == "axiomlauncher":
        base_url = settings.axiomlauncher_api_url
        token_val = settings.axiomlauncher_api_token
        enabled = settings.axiomlauncher_enabled
    elif service == "abuzovo":
        base_url = settings.abuzovo_api_url
        token_val = settings.abuzovo_api_token
        enabled = settings.abuzovo_enabled
    else:
        raise HTTPException(400, "Неизвестный сервис")

    token = token_val.get_secret_value() if hasattr(token_val, "get_secret_value") else str(token_val)
    return base_url, token, enabled


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@router.get("/services")
async def list_services():
    """Список доступных почтовых сервисов и их статус."""
    settings = get_settings()
    return {
        "services": [
            {"name": "abuzovo", "label": "Abuzovo", "enabled": bool(settings.abuzovo_enabled)},
            {"name": "axiomlauncher", "label": "AxiomLauncher", "enabled": bool(settings.axiomlauncher_enabled)},
        ]
    }


@router.get("/list")
async def list_mailboxes(service: str):
    """Список всех почтовых ящиков сервиса."""
    base_url, token, enabled = _get_service_config(service)
    if not enabled:
        raise HTTPException(400, f"Сервис {service} отключён")

    from curl_cffi import requests as cffi_requests
    try:
        resp = cffi_requests.get(
            f"{base_url}/api/v1/mailboxes",
            headers=_headers(token),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Ошибка получения ящиков %s: %s", service, e)
        raise HTTPException(502, f"Ошибка запроса к {service}: {e}")


@router.post("/create")
async def create_mailbox(body: MailboxCreateRequest):
    """Создать новый почтовый ящик."""
    base_url, token, enabled = _get_service_config(body.service)
    if not enabled:
        raise HTTPException(400, f"Сервис {body.service} отключён")

    from curl_cffi import requests as cffi_requests
    try:
        resp = cffi_requests.post(
            f"{base_url}/api/v1/mailboxes",
            headers=_headers(token),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Ошибка создания ящика %s: %s", body.service, e)
        raise HTTPException(502, f"Ошибка запроса к {body.service}: {e}")


@router.delete("/delete")
async def delete_mailbox(body: MailboxDeleteRequest):
    """Удалить почтовый ящик."""
    base_url, token, enabled = _get_service_config(body.service)
    if not enabled:
        raise HTTPException(400, f"Сервис {body.service} отключён")

    from curl_cffi import requests as cffi_requests
    try:
        resp = cffi_requests.delete(
            f"{base_url}/api/v1/mailboxes",
            headers=_headers(token),
            json={"mailbox_id": body.mailbox_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Ошибка удаления ящика %s: %s", body.service, e)
        raise HTTPException(502, f"Ошибка запроса к {body.service}: {e}")


@router.get("/messages")
async def get_messages(service: str, mailbox_id: str):
    """Получить входящие сообщения для ящика."""
    base_url, token, enabled = _get_service_config(service)
    if not enabled:
        raise HTTPException(400, f"Сервис {service} отключён")

    from curl_cffi import requests as cffi_requests
    try:
        resp = cffi_requests.get(
            f"{base_url}/api/v1/messages",
            headers=_headers(token),
            params={"mailbox_id": mailbox_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Ошибка получения сообщений %s/%s: %s", service, mailbox_id, e)
        raise HTTPException(502, f"Ошибка запроса к {service}: {e}")


@router.get("/domains")
async def get_domains(service: str):
    """Получить доступные домены сервиса."""
    base_url, token, enabled = _get_service_config(service)
    if not enabled:
        raise HTTPException(400, f"Сервис {service} отключён")

    from curl_cffi import requests as cffi_requests
    try:
        resp = cffi_requests.get(
            f"{base_url}/api/v1/domains",
            headers=_headers(token),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Ошибка получения доменов %s: %s", service, e)
        raise HTTPException(502, f"Ошибка запроса к {service}: {e}")
