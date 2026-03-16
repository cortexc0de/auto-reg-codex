"""
Модуль получения динамических прокси
Поддерживает получение URL динамического прокси через внешний API
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def fetch_dynamic_proxy(api_url: str, api_key: str = "", api_key_header: str = "X-API-Key", result_field: str = "") -> Optional[str]:
    """
    Получение URL прокси через API прокси

    Args:
        api_url: Адрес API прокси, ответ должен быть строкой URL прокси или JSON, содержащим URL прокси
        api_key: API-ключ (необязательно)
        api_key_header: Имя заголовка для API-ключа
        result_field: Путь поля для извлечения URL прокси из JSON-ответа, поддерживает разделение точкой (например, "data.proxy"), если пусто — используется текст ответа

    Returns:
        Строка URL прокси (например, http://user:pass@host:port), при ошибке возвращает None
    """
    try:
        from curl_cffi import requests as cffi_requests

        headers = {}
        if api_key:
            headers[api_key_header] = api_key

        response = cffi_requests.get(
            api_url,
            headers=headers,
            timeout=10,
            impersonate="chrome110"
        )

        if response.status_code != 200:
            logger.warning(f"API динамического прокси вернул код ошибки: {response.status_code}")
            return None

        text = response.text.strip()

        # Попытка разбора JSON
        if result_field or text.startswith("{") or text.startswith("["):
            try:
                import json
                data = json.loads(text)
                if result_field:
                    # Последовательное извлечение по пути с разделением точкой
                    for key in result_field.split("."):
                        if isinstance(data, dict):
                            data = data.get(key)
                        elif isinstance(data, list) and key.isdigit():
                            data = data[int(key)]
                        else:
                            data = None
                        if data is None:
                            break
                    proxy_url = str(data).strip() if data is not None else None
                else:
                    # Поле не указано, попытка использовать распространённые имена ключей
                    for key in ("proxy", "url", "proxy_url", "data", "ip"):
                        val = data.get(key) if isinstance(data, dict) else None
                        if val:
                            proxy_url = str(val).strip()
                            break
                    else:
                        proxy_url = text
            except (ValueError, AttributeError):
                proxy_url = text
        else:
            proxy_url = text

        if not proxy_url:
            logger.warning("API динамического прокси вернул пустой URL прокси")
            return None

        # Если протокол не указан, добавить http:// по умолчанию
        if not re.match(r'^(http|socks5)://', proxy_url):
            proxy_url = "http://" + proxy_url

        logger.info(f"Динамический прокси успешно получен: {proxy_url[:40]}..." if len(proxy_url) > 40 else f"Динамический прокси успешно получен: {proxy_url}")
        return proxy_url

    except Exception as e:
        logger.error(f"Не удалось получить динамический прокси: {e}")
        return None


def get_proxy_url_for_task() -> Optional[str]:
    """
    Получение URL прокси для задачи регистрации.
    Приоритетно используется динамический прокси (если включён), иначе — статическая конфигурация прокси.

    Returns:
        URL прокси или None
    """
    from ..config.settings import get_settings
    settings = get_settings()

    # Приоритетное использование динамического прокси
    if settings.proxy_dynamic_enabled and settings.proxy_dynamic_api_url:
        api_key = settings.proxy_dynamic_api_key.get_secret_value() if settings.proxy_dynamic_api_key else ""
        proxy_url = fetch_dynamic_proxy(
            api_url=settings.proxy_dynamic_api_url,
            api_key=api_key,
            api_key_header=settings.proxy_dynamic_api_key_header,
            result_field=settings.proxy_dynamic_result_field,
        )
        if proxy_url:
            return proxy_url
        logger.warning("Не удалось получить динамический прокси, переключение на статический прокси")

    # Использование статического прокси
    return settings.proxy_url
