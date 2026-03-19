"""
Маршруты API настроек
"""

import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...database import crud
from ...database.session import get_db
from ...config.settings import get_settings, update_settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== Pydantic Models ==============

class SettingItem(BaseModel):
    """Элемент настройки"""
    key: str
    value: str
    description: Optional[str] = None
    category: str = "general"


class SettingUpdateRequest(BaseModel):
    """Запрос на обновление настройки"""
    value: str


class ProxySettings(BaseModel):
    """Настройки прокси"""
    enabled: bool = False
    type: str = "http"  # http, socks5
    host: str = "127.0.0.1"
    port: int = 7890
    username: Optional[str] = None
    password: Optional[str] = None


class RegistrationSettings(BaseModel):
    """Настройки регистрации"""
    max_retries: int = 3
    timeout: int = 120
    default_password_length: int = 12
    sleep_min: int = 5
    sleep_max: int = 30


class WebUISettings(BaseModel):
    """Настройки Web UI"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class AllSettings(BaseModel):
    """Все настройки"""
    proxy: ProxySettings
    registration: RegistrationSettings
    webui: WebUISettings


# ============== API Endpoints ==============

@router.get("")
async def get_all_settings():
    """Получение всех настроек"""
    settings = get_settings()

    return {
        "proxy": {
            "enabled": settings.proxy_enabled,
            "type": settings.proxy_type,
            "host": settings.proxy_host,
            "port": settings.proxy_port,
            "username": settings.proxy_username,
            "has_password": bool(settings.proxy_password),
            "dynamic_enabled": settings.proxy_dynamic_enabled,
            "dynamic_api_url": settings.proxy_dynamic_api_url,
            "dynamic_api_key_header": settings.proxy_dynamic_api_key_header,
            "dynamic_result_field": settings.proxy_dynamic_result_field,
            "has_dynamic_api_key": bool(settings.proxy_dynamic_api_key and settings.proxy_dynamic_api_key.get_secret_value()),
        },
        "registration": {
            "max_retries": settings.registration_max_retries,
            "timeout": settings.registration_timeout,
            "default_password_length": settings.registration_default_password_length,
            "sleep_min": settings.registration_sleep_min,
            "sleep_max": settings.registration_sleep_max,
        },
        "webui": {
            "host": settings.webui_host,
            "port": settings.webui_port,
            "debug": settings.debug,
        },
        "tempmail": {
            "base_url": settings.tempmail_base_url,
            "timeout": settings.tempmail_timeout,
            "max_retries": settings.tempmail_max_retries,
        },
        "email_code": {
            "timeout": settings.email_code_timeout,
            "poll_interval": settings.email_code_poll_interval,
        },
    }


@router.get("/proxy")
async def get_proxy_settings():
    """Получение настроек прокси"""
    settings = get_settings()

    return {
        "enabled": settings.proxy_enabled,
        "type": settings.proxy_type,
        "host": settings.proxy_host,
        "port": settings.proxy_port,
        "username": settings.proxy_username,
        "has_password": bool(settings.proxy_password),
        "proxy_url": settings.proxy_url,
    }


@router.post("/proxy")
async def update_proxy_settings(request: ProxySettings):
    """Обновление настроек прокси"""
    update_dict = {
        "proxy_enabled": request.enabled,
        "proxy_type": request.type,
        "proxy_host": request.host,
        "proxy_port": request.port,
        "proxy_username": request.username,
    }

    if request.password:
        update_dict["proxy_password"] = request.password

    update_settings(**update_dict)

    return {"success": True, "message": "Настройки прокси обновлены"}


@router.post("/proxy/test")
async def test_proxy_settings(request: ProxySettings):
    """Тестирование подключения прокси"""
    import time
    from curl_cffi import requests as cffi_requests

    # Если пароль не передан (скрыт в UI), подставляем из сохранённых настроек
    password = request.password
    if not password and request.username:
        settings = get_settings()
        pw = settings.proxy_password
        if pw:
            password = pw.get_secret_value() if hasattr(pw, 'get_secret_value') else str(pw)

    auth = ""
    if request.username and password:
        from urllib.parse import quote
        auth = f"{quote(str(request.username), safe='')}:{quote(str(password), safe='')}@"

    # Определяем порядок попыток: выбранный тип первым, потом альтернативный
    schemes_to_try = []
    if request.type == "socks5":
        schemes_to_try = ["socks5", "socks5h"]
    elif request.type == "http":
        schemes_to_try = ["http", "socks5", "socks5h"]
    else:
        raise HTTPException(status_code=400, detail="Неподдерживаемый тип прокси")

    test_url = "https://api.ipify.org?format=json"
    last_error = ""

    for scheme in schemes_to_try:
        proxy_url = f"{scheme}://{auth}{request.host}:{request.port}"
        start_time = time.time()

        try:
            response = cffi_requests.get(
                test_url,
                proxy=proxy_url,
                timeout=10,
                impersonate="chrome120"
            )

            elapsed_time = time.time() - start_time

            if response.status_code == 200:
                ip_info = response.json()
                detected = scheme if scheme != request.type else request.type
                msg = f"Прокси подключен ({detected}), IP: {ip_info.get('ip', '?')}"
                if scheme != request.type:
                    msg += f" ⚠️ Авто-определён как {scheme.upper()}, смените тип"
                return {
                    "success": True,
                    "ip": ip_info.get("ip", ""),
                    "response_time": round(elapsed_time * 1000),
                    "detected_type": scheme,
                    "message": msg
                }
        except Exception as e:
            last_error = str(e)
            continue

    return {
        "success": False,
        "message": f"Прокси недоступен (пробовал {', '.join(schemes_to_try)}): {last_error}"
    }


@router.get("/proxy/dynamic")
async def get_dynamic_proxy_settings():
    """Получение настроек динамического прокси"""
    settings = get_settings()
    return {
        "enabled": settings.proxy_dynamic_enabled,
        "api_url": settings.proxy_dynamic_api_url,
        "api_key_header": settings.proxy_dynamic_api_key_header,
        "result_field": settings.proxy_dynamic_result_field,
        "has_api_key": bool(settings.proxy_dynamic_api_key and settings.proxy_dynamic_api_key.get_secret_value()),
    }


class DynamicProxySettings(BaseModel):
    """Настройки динамического прокси"""
    enabled: bool = False
    api_url: str = ""
    api_key: Optional[str] = None
    api_key_header: str = "X-API-Key"
    result_field: str = ""


@router.post("/proxy/dynamic")
async def update_dynamic_proxy_settings(request: DynamicProxySettings):
    """Обновление настроек динамического прокси"""
    update_dict = {
        "proxy_dynamic_enabled": request.enabled,
        "proxy_dynamic_api_url": request.api_url,
        "proxy_dynamic_api_key_header": request.api_key_header,
        "proxy_dynamic_result_field": request.result_field,
    }
    if request.api_key is not None:
        update_dict["proxy_dynamic_api_key"] = request.api_key

    update_settings(**update_dict)
    return {"success": True, "message": "Настройки динамического прокси обновлены"}


@router.post("/proxy/dynamic/test")
async def test_dynamic_proxy(request: DynamicProxySettings):
    """Тестирование API динамического прокси"""
    from ...core.dynamic_proxy import fetch_dynamic_proxy

    if not request.api_url:
        raise HTTPException(status_code=400, detail="Укажите адрес API динамического прокси")

    # Если api_key не передан, используем сохранённый
    api_key = request.api_key or ""
    if not api_key:
        settings = get_settings()
        if settings.proxy_dynamic_api_key:
            api_key = settings.proxy_dynamic_api_key.get_secret_value()

    proxy_url = fetch_dynamic_proxy(
        api_url=request.api_url,
        api_key=api_key,
        api_key_header=request.api_key_header,
        result_field=request.result_field,
    )

    if not proxy_url:
        return {"success": False, "message": "API динамического прокси вернул пустой результат или запрос не удался"}

    # Тестирование подключения через полученный прокси
    import time
    from curl_cffi import requests as cffi_requests
    try:
        proxies = {"http": proxy_url, "https": proxy_url}
        start = time.time()
        resp = cffi_requests.get(
            "https://api.ipify.org?format=json",
            proxies=proxies,
            timeout=10,
            impersonate="chrome110"
        )
        elapsed = round((time.time() - start) * 1000)
        if resp.status_code == 200:
            ip = resp.json().get("ip", "")
            return {"success": True, "proxy_url": proxy_url, "ip": ip, "response_time": elapsed,
                    "message": f"Динамический прокси доступен, выходной IP: {ip}, время ответа: {elapsed}мс"}
        return {"success": False, "proxy_url": proxy_url, "message": f"Ошибка подключения прокси: HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "proxy_url": proxy_url, "message": f"Ошибка подключения прокси: {e}"}


@router.get("/registration")
async def get_registration_settings():
    """Получение настроек регистрации"""
    settings = get_settings()

    return {
        "max_retries": settings.registration_max_retries,
        "timeout": settings.registration_timeout,
        "default_password_length": settings.registration_default_password_length,
        "sleep_min": settings.registration_sleep_min,
        "sleep_max": settings.registration_sleep_max,
    }


@router.post("/registration")
async def update_registration_settings(request: RegistrationSettings):
    """Обновление настроек регистрации"""
    update_settings(
        registration_max_retries=request.max_retries,
        registration_timeout=request.timeout,
        registration_default_password_length=request.default_password_length,
        registration_sleep_min=request.sleep_min,
        registration_sleep_max=request.sleep_max,
    )

    return {"success": True, "message": "Настройки регистрации обновлены"}


@router.get("/database")
async def get_database_info():
    """Получение информации о базе данных"""
    settings = get_settings()

    import os
    from pathlib import Path

    db_path = settings.database_url
    if db_path.startswith("sqlite:///"):
        db_path = db_path[10:]

    db_file = Path(db_path) if os.path.isabs(db_path) else Path(db_path)
    db_size = db_file.stat().st_size if db_file.exists() else 0

    with get_db() as db:
        from ...database.models import Account, EmailService, RegistrationTask

        account_count = db.query(Account).count()
        service_count = db.query(EmailService).count()
        task_count = db.query(RegistrationTask).count()

    return {
        "database_url": settings.database_url,
        "database_size_bytes": db_size,
        "database_size_mb": round(db_size / (1024 * 1024), 2),
        "accounts_count": account_count,
        "email_services_count": service_count,
        "tasks_count": task_count,
    }


@router.post("/database/backup")
async def backup_database():
    """Резервное копирование базы данных"""
    import shutil
    from datetime import datetime

    settings = get_settings()

    db_path = settings.database_url
    if db_path.startswith("sqlite:///"):
        db_path = db_path[10:]

    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Файл базы данных не существует")

    # Создание директории резервных копий
    backup_dir = Path(db_path).parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    # Генерация имени файла резервной копии
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"database_backup_{timestamp}.db"

    # Копирование файла базы данных
    shutil.copy2(db_path, backup_path)

    return {
        "success": True,
        "message": "Резервное копирование базы данных выполнено успешно",
        "backup_path": str(backup_path)
    }


@router.post("/database/cleanup")
async def cleanup_database(
    days: int = 30,
    keep_failed: bool = True
):
    """Очистка устаревших данных"""
    from datetime import datetime, timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    with get_db() as db:
        from ...database.models import RegistrationTask
        from sqlalchemy import delete

        # Удаление старых задач
        conditions = [RegistrationTask.created_at < cutoff_date]
        if not keep_failed:
            conditions.append(RegistrationTask.status != "failed")
        else:
            conditions.append(RegistrationTask.status.in_(["completed", "cancelled"]))

        result = db.execute(
            delete(RegistrationTask).where(*conditions)
        )
        db.commit()

        deleted_count = result.rowcount

    return {
        "success": True,
        "message": f"Очищено {deleted_count} устаревших записей задач",
        "deleted_count": deleted_count
    }


@router.get("/logs")
async def get_recent_logs(
    lines: int = 100,
    level: str = "INFO"
):
    """Получение последних логов"""
    settings = get_settings()

    log_file = settings.log_file
    if not log_file:
        return {"logs": [], "message": "Файл логов не настроен"}

    from pathlib import Path
    log_path = Path(log_file)

    if not log_path.exists():
        return {"logs": [], "message": "Файл логов не существует"}

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]

        return {
            "logs": [line.strip() for line in recent_lines],
            "total_lines": len(all_lines)
        }
    except Exception as e:
        return {"logs": [], "error": str(e)}


# ============== Настройки временной почты ==============

class TempmailSettings(BaseModel):
    """Настройки временной почты"""
    api_url: Optional[str] = None
    enabled: bool = True


class EmailCodeSettings(BaseModel):
    """Настройки ожидания кода подтверждения"""
    timeout: int = 120  # Таймаут ожидания кода подтверждения (сек)
    poll_interval: int = 3  # Интервал опроса кода подтверждения (сек)


@router.get("/tempmail")
async def get_tempmail_settings():
    """Получение настроек временной почты"""
    settings = get_settings()

    return {
        "api_url": settings.tempmail_base_url,
        "timeout": settings.tempmail_timeout,
        "max_retries": settings.tempmail_max_retries,
        "enabled": True  # Временная почта доступна по умолчанию
    }


@router.post("/tempmail")
async def update_tempmail_settings(request: TempmailSettings):
    """Обновление настроек временной почты"""
    update_dict = {}

    if request.api_url:
        update_dict["tempmail_base_url"] = request.api_url

    update_settings(**update_dict)

    return {"success": True, "message": "Настройки временной почты обновлены"}


# ============== Настройки ожидания кода подтверждения ==============

@router.get("/email-code")
async def get_email_code_settings():
    """Получение настроек ожидания кода подтверждения"""
    settings = get_settings()
    return {
        "timeout": settings.email_code_timeout,
        "poll_interval": settings.email_code_poll_interval,
    }


@router.post("/email-code")
async def update_email_code_settings(request: EmailCodeSettings):
    """Обновление настроек ожидания кода подтверждения"""
    # Проверка допустимого диапазона параметров
    if request.timeout < 30 or request.timeout > 600:
        raise HTTPException(status_code=400, detail="Таймаут должен быть от 30 до 600 секунд")
    if request.poll_interval < 1 or request.poll_interval > 30:
        raise HTTPException(status_code=400, detail="Интервал опроса должен быть от 1 до 30 секунд")

    update_settings(
        email_code_timeout=request.timeout,
        email_code_poll_interval=request.poll_interval,
    )

    return {"success": True, "message": "Настройки ожидания кода подтверждения обновлены"}


# ============== CRUD списка прокси ==============

class ProxyCreateRequest(BaseModel):
    """Запрос на создание прокси"""
    name: str
    type: str = "http"  # http, socks5
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: bool = True
    priority: int = 0


class ProxyUpdateRequest(BaseModel):
    """Запрос на обновление прокси"""
    name: Optional[str] = None
    type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


@router.get("/proxies")
async def get_proxies_list(enabled: Optional[bool] = None):
    """Получение списка прокси"""
    with get_db() as db:
        proxies = crud.get_proxies(db, enabled=enabled)
        return {
            "proxies": [p.to_dict() for p in proxies],
            "total": len(proxies)
        }


@router.post("/proxies")
async def create_proxy_item(request: ProxyCreateRequest):
    """Создание прокси"""
    with get_db() as db:
        proxy = crud.create_proxy(
            db,
            name=request.name,
            type=request.type,
            host=request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            enabled=request.enabled,
            priority=request.priority
        )
        return {"success": True, "proxy": proxy.to_dict()}


class ProxyBulkImportRequest(BaseModel):
    """Запрос на массовый импорт прокси"""
    proxies_text: str
    default_type: str = "http"


@router.post("/proxies/bulk-import")
async def bulk_import_proxies(request: ProxyBulkImportRequest):
    """Массовый импорт прокси из текста (по одному на строку)"""
    from ...core.utils import parse_proxy_string

    lines = request.proxies_text.strip().split("\n")
    imported = 0
    skipped = 0
    errors = []

    with get_db() as db:
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                skipped += 1
                continue

            try:
                parsed = parse_proxy_string(line)
                # If no scheme was in the string and default_type is set, use it
                if "://" not in line and request.default_type:
                    parsed["type"] = request.default_type

                name = f"{parsed['host']}:{parsed['port']}"
                crud.create_proxy(
                    db,
                    name=name,
                    type=parsed["type"],
                    host=parsed["host"],
                    port=parsed["port"],
                    username=parsed["username"],
                    password=parsed["password"],
                    enabled=True,
                    priority=0,
                )
                imported += 1
            except Exception as e:
                errors.append(f"Строка {i}: {str(e)}")
                skipped += 1

    return {
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }


@router.get("/proxies/{proxy_id}")
async def get_proxy_item(proxy_id: int):
    """Получение отдельного прокси"""
    with get_db() as db:
        proxy = crud.get_proxy_by_id(db, proxy_id)
        if not proxy:
            raise HTTPException(status_code=404, detail="Прокси не существует")
        return proxy.to_dict(include_password=True)


@router.patch("/proxies/{proxy_id}")
async def update_proxy_item(proxy_id: int, request: ProxyUpdateRequest):
    """Обновление прокси"""
    with get_db() as db:
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.type is not None:
            update_data["type"] = request.type
        if request.host is not None:
            update_data["host"] = request.host
        if request.port is not None:
            update_data["port"] = request.port
        if request.username is not None:
            update_data["username"] = request.username
        if request.password is not None:
            update_data["password"] = request.password
        if request.enabled is not None:
            update_data["enabled"] = request.enabled
        if request.priority is not None:
            update_data["priority"] = request.priority

        proxy = crud.update_proxy(db, proxy_id, **update_data)
        if not proxy:
            raise HTTPException(status_code=404, detail="Прокси не существует")
        return {"success": True, "proxy": proxy.to_dict()}


@router.delete("/proxies/{proxy_id}")
async def delete_proxy_item(proxy_id: int):
    """Удаление прокси"""
    with get_db() as db:
        success = crud.delete_proxy(db, proxy_id)
        if not success:
            raise HTTPException(status_code=404, detail="Прокси не существует")
        return {"success": True, "message": "Прокси удалён"}


@router.post("/proxies/{proxy_id}/test")
async def test_proxy_item(proxy_id: int):
    """Тестирование отдельного прокси"""
    import time
    from curl_cffi import requests as cffi_requests

    with get_db() as db:
        proxy = crud.get_proxy_by_id(db, proxy_id)
        if not proxy:
            raise HTTPException(status_code=404, detail="Прокси не существует")

        proxy_url = proxy.proxy_url
        test_url = "https://api.ipify.org?format=json"
        start_time = time.time()

        try:
            proxies = {
                "http": proxy_url,
                "https": proxy_url
            }

            response = cffi_requests.get(
                test_url,
                proxies=proxies,
                timeout=10,
                impersonate="chrome110"
            )

            elapsed_time = time.time() - start_time

            if response.status_code == 200:
                ip_info = response.json()
                return {
                    "success": True,
                    "ip": ip_info.get("ip", ""),
                    "response_time": round(elapsed_time * 1000),
                    "message": f"Прокси подключен успешно, выходной IP: {ip_info.get('ip', 'unknown')}"
                }
            else:
                return {
                    "success": False,
                    "message": f"Прокси вернул код ошибки: {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Ошибка подключения прокси: {str(e)}"
            }


@router.post("/proxies/test-all")
async def test_all_proxies():
    """Тестирование всех включённых прокси"""
    import time
    from curl_cffi import requests as cffi_requests

    with get_db() as db:
        proxies = crud.get_enabled_proxies(db)

        results = []
        for proxy in proxies:
            proxy_url = proxy.proxy_url
            test_url = "https://api.ipify.org?format=json"
            start_time = time.time()

            try:
                proxies_dict = {
                    "http": proxy_url,
                    "https": proxy_url
                }

                response = cffi_requests.get(
                    test_url,
                    proxies=proxies_dict,
                    timeout=10,
                    impersonate="chrome110"
                )

                elapsed_time = time.time() - start_time

                if response.status_code == 200:
                    ip_info = response.json()
                    results.append({
                        "id": proxy.id,
                        "name": proxy.name,
                        "success": True,
                        "ip": ip_info.get("ip", ""),
                        "response_time": round(elapsed_time * 1000)
                    })
                else:
                    results.append({
                        "id": proxy.id,
                        "name": proxy.name,
                        "success": False,
                        "message": f"Код статуса: {response.status_code}"
                    })

            except Exception as e:
                results.append({
                    "id": proxy.id,
                    "name": proxy.name,
                    "success": False,
                    "message": str(e)
                })

        success_count = sum(1 for r in results if r["success"])
        return {
            "total": len(proxies),
            "success": success_count,
            "failed": len(proxies) - success_count,
            "results": results
        }


@router.post("/proxies/{proxy_id}/enable")
async def enable_proxy(proxy_id: int):
    """Включение прокси"""
    with get_db() as db:
        proxy = crud.update_proxy(db, proxy_id, enabled=True)
        if not proxy:
            raise HTTPException(status_code=404, detail="Прокси не существует")
        return {"success": True, "message": "Прокси включён"}


@router.post("/proxies/{proxy_id}/disable")
async def disable_proxy(proxy_id: int):
    """Отключение прокси"""
    with get_db() as db:
        proxy = crud.update_proxy(db, proxy_id, enabled=False)
        if not proxy:
            raise HTTPException(status_code=404, detail="Прокси не существует")
        return {"success": True, "message": "Прокси отключён"}


# ============== Настройки CPA ==============

class CPASettings(BaseModel):
    """Настройки CPA"""
    enabled: bool = False
    api_url: str = ""
    api_token: str = ""


class CPATestRequest(BaseModel):
    """Запрос на тестирование CPA"""
    api_url: str
    api_token: str


@router.get("/cpa")
async def get_cpa_settings():
    """Получение настроек CPA"""
    settings = get_settings()

    return {
        "enabled": settings.cpa_enabled,
        "api_url": settings.cpa_api_url,
        "has_token": bool(settings.cpa_api_token and settings.cpa_api_token.get_secret_value()),
    }


@router.post("/cpa")
async def update_cpa_settings(request: CPASettings):
    """Обновление настроек CPA"""
    update_dict = {
        "cpa_enabled": request.enabled,
        "cpa_api_url": request.api_url,
    }

    # Обновляем token только если он предоставлен
    if request.api_token:
        update_dict["cpa_api_token"] = request.api_token

    update_settings(**update_dict)

    return {"success": True, "message": "Настройки CPA обновлены"}


@router.post("/cpa/test")
async def test_cpa_connection(request: CPATestRequest):
    """Тестирование подключения CPA"""
    from ...core.cpa_upload import test_cpa_connection as do_test

    settings = get_settings()
    proxy = settings.proxy_url

    # Если передано 'use_saved_token', используем сохранённый token
    api_token = request.api_token
    if api_token == 'use_saved_token' or not api_token:
        if settings.cpa_api_token:
            api_token = settings.cpa_api_token.get_secret_value()
        else:
            return {
                "success": False,
                "message": "API Token не настроен"
            }

    success, message = do_test(request.api_url, api_token, proxy)

    return {
        "success": success,
        "message": message
    }


# ============== Настройки Outlook ==============

class OutlookSettings(BaseModel):
    """Настройки Outlook"""
    default_client_id: Optional[str] = None


@router.get("/outlook")
async def get_outlook_settings():
    """Получение настроек Outlook"""
    settings = get_settings()

    return {
        "default_client_id": settings.outlook_default_client_id,
        "provider_priority": settings.outlook_provider_priority,
        "health_failure_threshold": settings.outlook_health_failure_threshold,
        "health_disable_duration": settings.outlook_health_disable_duration,
    }


@router.post("/outlook")
async def update_outlook_settings(request: OutlookSettings):
    """Обновление настроек Outlook"""
    update_dict = {}

    if request.default_client_id is not None:
        update_dict["outlook_default_client_id"] = request.default_client_id

    if update_dict:
        update_settings(**update_dict)

    return {"success": True, "message": "Настройки Outlook обновлены"}


# ============== Настройки Team Manager ==============

class TeamManagerSettings(BaseModel):
    """Настройки Team Manager"""
    enabled: bool = False
    api_url: str = ""
    api_key: str = ""


class TeamManagerTestRequest(BaseModel):
    """Запрос на тестирование Team Manager"""
    api_url: str
    api_key: str


@router.get("/team-manager")
async def get_team_manager_settings():
    """Получение настроек Team Manager"""
    settings = get_settings()
    return {
        "enabled": settings.tm_enabled,
        "api_url": settings.tm_api_url,
        "has_api_key": bool(settings.tm_api_key and settings.tm_api_key.get_secret_value()),
    }


@router.post("/team-manager")
async def update_team_manager_settings(request: TeamManagerSettings):
    """Обновление настроек Team Manager"""
    update_dict = {
        "tm_enabled": request.enabled,
        "tm_api_url": request.api_url,
    }
    if request.api_key:
        update_dict["tm_api_key"] = request.api_key
    update_settings(**update_dict)
    return {"success": True, "message": "Настройки Team Manager обновлены"}


@router.post("/team-manager/test")
async def test_team_manager_connection(request: TeamManagerTestRequest):
    """Тестирование подключения Team Manager"""
    from ...core.team_manager import test_team_manager_connection as do_test

    settings = get_settings()
    api_key = request.api_key
    if api_key == 'use_saved_key' or not api_key:
        if settings.tm_api_key:
            api_key = settings.tm_api_key.get_secret_value()
        else:
            return {"success": False, "message": "API Key не настроен"}

    success, message = do_test(request.api_url, api_key)
    return {"success": success, "message": message}


# ============== Настройки Abuzovo ==============

class AbuzovSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    api_url: Optional[str] = None
    api_token: Optional[str] = None
    default_domain_id: Optional[str] = None
    email_type: Optional[str] = None


@router.get("/abuzovo")
def get_abuzovo_settings():
    """Получение настроек Abuzovo"""
    settings = get_settings()
    return {
        "enabled": settings.abuzovo_enabled,
        "api_url": settings.abuzovo_api_url,
        "has_token": bool(settings.abuzovo_api_token and settings.abuzovo_api_token.get_secret_value()),
        "default_domain_id": settings.abuzovo_default_domain_id,
        "email_type": settings.abuzovo_email_type,
    }


@router.post("/abuzovo")
def update_abuzovo_settings(request: AbuzovSettingsRequest):
    """Обновить настройки Abuzovo"""
    updates = {}
    if request.enabled is not None:
        updates["abuzovo_enabled"] = request.enabled
    if request.api_url is not None:
        updates["abuzovo_api_url"] = request.api_url
    if request.api_token is not None:
        updates["abuzovo_api_token"] = request.api_token
    if request.default_domain_id is not None:
        updates["abuzovo_default_domain_id"] = request.default_domain_id
    if request.email_type is not None:
        updates["abuzovo_email_type"] = request.email_type
    if updates:
        update_settings(**updates)
    return {"success": True, "message": "Настройки Abuzovo обновлены"}


@router.post("/abuzovo/test")
def test_abuzovo_connection():
    """Тест подключения к Abuzovo API"""
    from curl_cffi import requests as cffi_requests

    settings = get_settings()
    api_url = settings.abuzovo_api_url.rstrip("/")
    api_token = settings.abuzovo_api_token.get_secret_value() if settings.abuzovo_api_token else ""

    if not api_token:
        raise HTTPException(status_code=400, detail="API токен не настроен")

    try:
        resp = cffi_requests.get(
            f"{api_url}/api/v1/domains",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=15,
            impersonate="chrome120",
        )
        if resp.status_code == 200:
            data = resp.json()
            domains = data.get("domains", [])
            prices = data.get("prices", {})
            return {
                "success": True,
                "message": f"Подключение успешно. Доменов: {len(domains)}",
                "domains": domains,
                "prices": prices,
            }
        elif resp.status_code == 401:
            return {"success": False, "message": "Неверный API токен"}
        else:
            return {"success": False, "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"Ошибка: {str(e)}"}


# ============== Workspace Settings ==============

class WorkspaceSettingsRequest(BaseModel):
    monitoring_enabled: Optional[bool] = None
    monitoring_interval: Optional[int] = None
    auto_kick_enabled: Optional[bool] = None
    auto_kick_duration: Optional[int] = None
    auto_redistribute_enabled: Optional[bool] = None
    ban_detection_enabled: Optional[bool] = None
    ban_keywords: Optional[str] = None  # JSON string
    long_duration_days: Optional[int] = None


@router.get("/workspace")
def get_workspace_settings():
    """Получить настройки Workspace Manager"""
    import json as _json
    from ...config.settings import get_settings
    settings = get_settings()
    ban_kw = settings.workspace_ban_keywords
    if isinstance(ban_kw, list):
        ban_kw = _json.dumps(ban_kw, ensure_ascii=False)
    return {
        "monitoring_enabled": settings.workspace_monitoring_enabled,
        "monitoring_interval": settings.workspace_monitoring_interval,
        "auto_kick_enabled": settings.workspace_auto_kick_enabled,
        "auto_kick_duration": settings.workspace_auto_kick_duration,
        "auto_redistribute_enabled": settings.workspace_auto_redistribute_enabled,
        "ban_detection_enabled": settings.workspace_ban_detection_enabled,
        "ban_keywords": ban_kw,
        "long_duration_days": settings.workspace_long_duration_days,
    }


@router.post("/workspace")
def update_workspace_settings(request: WorkspaceSettingsRequest):
    """Обновить настройки Workspace Manager"""
    from ...config.settings import update_settings
    updates = {}
    if request.monitoring_enabled is not None:
        updates["workspace_monitoring_enabled"] = request.monitoring_enabled
    if request.monitoring_interval is not None:
        updates["workspace_monitoring_interval"] = request.monitoring_interval
    if request.auto_kick_enabled is not None:
        updates["workspace_auto_kick_enabled"] = request.auto_kick_enabled
    if request.auto_kick_duration is not None:
        updates["workspace_auto_kick_duration"] = request.auto_kick_duration
    if request.auto_redistribute_enabled is not None:
        updates["workspace_auto_redistribute_enabled"] = request.auto_redistribute_enabled
    if request.ban_detection_enabled is not None:
        updates["workspace_ban_detection_enabled"] = request.ban_detection_enabled
    if request.ban_keywords is not None:
        import json as _json
        try:
            updates["workspace_ban_keywords"] = _json.loads(request.ban_keywords)
        except (ValueError, TypeError):
            updates["workspace_ban_keywords"] = request.ban_keywords
    if request.long_duration_days is not None:
        updates["workspace_long_duration_days"] = request.long_duration_days
    if updates:
        update_settings(**updates)
    return {"success": True, "message": "Настройки Workspace Manager обновлены"}
