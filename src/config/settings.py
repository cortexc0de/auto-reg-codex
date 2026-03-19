"""
Управление конфигурацией — полностью на основе хранения в базе данных
Все настройки загружаются из базы данных, файлы окружения и .env больше не используются
"""

import os
from typing import Optional, Dict, Any, Type, List
from enum import Enum
from pydantic import BaseModel, field_validator
from pydantic.types import SecretStr
from dataclasses import dataclass


class SettingCategory(str, Enum):
    """Категория настроек"""
    GENERAL = "general"
    DATABASE = "database"
    WEBUI = "webui"
    LOG = "log"
    OPENAI = "openai"
    PROXY = "proxy"
    REGISTRATION = "registration"
    EMAIL = "email"
    TEMPMAIL = "tempmail"
    CUSTOM_DOMAIN = "custom_domain"
    SECURITY = "security"
    CPA = "cpa"
    ABUZOVO = "abuzovo"
    WORKSPACE = "workspace"


@dataclass
class SettingDefinition:
    """Определение настройки"""
    db_key: str
    default_value: Any
    category: SettingCategory
    description: str = ""
    is_secret: bool = False


# Определения всех элементов конфигурации (включая ключ БД, значение по умолчанию, категорию, описание)
SETTING_DEFINITIONS: Dict[str, SettingDefinition] = {
    # Информация о приложении
    "app_name": SettingDefinition(
        db_key="app.name",
        default_value="Система автоматической регистрации OpenAI/Codex CLI",
        category=SettingCategory.GENERAL,
        description="Название приложения"
    ),
    "app_version": SettingDefinition(
        db_key="app.version",
        default_value="2.0.0",
        category=SettingCategory.GENERAL,
        description="Версия приложения"
    ),
    "debug": SettingDefinition(
        db_key="app.debug",
        default_value=False,
        category=SettingCategory.GENERAL,
        description="Режим отладки"
    ),

    # Конфигурация базы данных
    "database_url": SettingDefinition(
        db_key="database.url",
        default_value="data/database.db",
        category=SettingCategory.DATABASE,
        description="Путь к базе данных или строка подключения"
    ),

    # Конфигурация Web UI
    "webui_host": SettingDefinition(
        db_key="webui.host",
        default_value="0.0.0.0",
        category=SettingCategory.WEBUI,
        description="Адрес прослушивания Web UI"
    ),
    "webui_port": SettingDefinition(
        db_key="webui.port",
        default_value=8000,
        category=SettingCategory.WEBUI,
        description="Порт прослушивания Web UI"
    ),
    "webui_secret_key": SettingDefinition(
        db_key="webui.secret_key",
        default_value="your-secret-key-change-in-production",
        category=SettingCategory.WEBUI,
        description="Секретный ключ Web UI",
        is_secret=True
    ),

    # Конфигурация логов
    "log_level": SettingDefinition(
        db_key="log.level",
        default_value="INFO",
        category=SettingCategory.LOG,
        description="Уровень логирования"
    ),
    "log_file": SettingDefinition(
        db_key="log.file",
        default_value="logs/app.log",
        category=SettingCategory.LOG,
        description="Путь к файлу логов"
    ),
    "log_retention_days": SettingDefinition(
        db_key="log.retention_days",
        default_value=30,
        category=SettingCategory.LOG,
        description="Срок хранения логов (дней)"
    ),

    # Конфигурация OpenAI
    "openai_client_id": SettingDefinition(
        db_key="openai.client_id",
        default_value="app_EMoamEEZ73f0CkXaXp7hrann",
        category=SettingCategory.OPENAI,
        description="OpenAI OAuth Client ID"
    ),
    "openai_auth_url": SettingDefinition(
        db_key="openai.auth_url",
        default_value="https://auth.openai.com/oauth/authorize",
        category=SettingCategory.OPENAI,
        description="URL авторизации OpenAI OAuth"
    ),
    "openai_token_url": SettingDefinition(
        db_key="openai.token_url",
        default_value="https://auth.openai.com/oauth/token",
        category=SettingCategory.OPENAI,
        description="URL токена OpenAI OAuth"
    ),
    "openai_redirect_uri": SettingDefinition(
        db_key="openai.redirect_uri",
        default_value="http://localhost:1455/auth/callback",
        category=SettingCategory.OPENAI,
        description="URI обратного вызова OpenAI OAuth"
    ),
    "openai_scope": SettingDefinition(
        db_key="openai.scope",
        default_value="openid email profile offline_access",
        category=SettingCategory.OPENAI,
        description="Области разрешений OpenAI OAuth"
    ),

    # Конфигурация прокси
    "proxy_enabled": SettingDefinition(
        db_key="proxy.enabled",
        default_value=False,
        category=SettingCategory.PROXY,
        description="Включить ли прокси"
    ),
    "proxy_type": SettingDefinition(
        db_key="proxy.type",
        default_value="http",
        category=SettingCategory.PROXY,
        description="Тип прокси (http/socks5)"
    ),
    "proxy_host": SettingDefinition(
        db_key="proxy.host",
        default_value="127.0.0.1",
        category=SettingCategory.PROXY,
        description="Адрес прокси-сервера"
    ),
    "proxy_port": SettingDefinition(
        db_key="proxy.port",
        default_value=7890,
        category=SettingCategory.PROXY,
        description="Порт прокси-сервера"
    ),
    "proxy_username": SettingDefinition(
        db_key="proxy.username",
        default_value="",
        category=SettingCategory.PROXY,
        description="Имя пользователя прокси"
    ),
    "proxy_password": SettingDefinition(
        db_key="proxy.password",
        default_value="",
        category=SettingCategory.PROXY,
        description="Пароль прокси",
        is_secret=True
    ),
    "proxy_dynamic_enabled": SettingDefinition(
        db_key="proxy.dynamic_enabled",
        default_value=False,
        category=SettingCategory.PROXY,
        description="Включить ли динамический прокси"
    ),
    "proxy_dynamic_api_url": SettingDefinition(
        db_key="proxy.dynamic_api_url",
        default_value="",
        category=SettingCategory.PROXY,
        description="Адрес API динамического прокси, возвращает строку URL прокси"
    ),
    "proxy_dynamic_api_key": SettingDefinition(
        db_key="proxy.dynamic_api_key",
        default_value="",
        category=SettingCategory.PROXY,
        description="Ключ API динамического прокси (необязательно)",
        is_secret=True
    ),
    "proxy_dynamic_api_key_header": SettingDefinition(
        db_key="proxy.dynamic_api_key_header",
        default_value="X-API-Key",
        category=SettingCategory.PROXY,
        description="Имя заголовка ключа API динамического прокси"
    ),
    "proxy_dynamic_result_field": SettingDefinition(
        db_key="proxy.dynamic_result_field",
        default_value="",
        category=SettingCategory.PROXY,
        description="Путь к полю для извлечения URL прокси из JSON ответа (пустое — использовать текст ответа)"
    ),

    # Конфигурация регистрации
    "registration_max_retries": SettingDefinition(
        db_key="registration.max_retries",
        default_value=3,
        category=SettingCategory.REGISTRATION,
        description="Максимальное количество повторных попыток регистрации"
    ),
    "registration_timeout": SettingDefinition(
        db_key="registration.timeout",
        default_value=120,
        category=SettingCategory.REGISTRATION,
        description="Таймаут регистрации (сек)"
    ),
    "registration_default_password_length": SettingDefinition(
        db_key="registration.default_password_length",
        default_value=12,
        category=SettingCategory.REGISTRATION,
        description="Длина пароля по умолчанию"
    ),
    "registration_sleep_min": SettingDefinition(
        db_key="registration.sleep_min",
        default_value=5,
        category=SettingCategory.REGISTRATION,
        description="Минимальный интервал между регистрациями (сек)"
    ),
    "registration_sleep_max": SettingDefinition(
        db_key="registration.sleep_max",
        default_value=30,
        category=SettingCategory.REGISTRATION,
        description="Максимальный интервал между регистрациями (сек)"
    ),

    # Конфигурация почтовых сервисов
    "email_service_priority": SettingDefinition(
        db_key="email.service_priority",
        default_value={"tempmail": 0, "outlook": 1, "custom_domain": 2, "abuzovo": 3},
        category=SettingCategory.EMAIL,
        description="Приоритет почтовых сервисов"
    ),

    # Конфигурация Tempmail.lol
    "tempmail_base_url": SettingDefinition(
        db_key="tempmail.base_url",
        default_value="https://api.tempmail.lol/v2",
        category=SettingCategory.TEMPMAIL,
        description="Адрес API Tempmail"
    ),
    "tempmail_timeout": SettingDefinition(
        db_key="tempmail.timeout",
        default_value=30,
        category=SettingCategory.TEMPMAIL,
        description="Таймаут Tempmail (сек)"
    ),
    "tempmail_max_retries": SettingDefinition(
        db_key="tempmail.max_retries",
        default_value=3,
        category=SettingCategory.TEMPMAIL,
        description="Максимальное количество повторных попыток Tempmail"
    ),

    # Конфигурация почты с пользовательским доменом
    "custom_domain_base_url": SettingDefinition(
        db_key="custom_domain.base_url",
        default_value="",
        category=SettingCategory.CUSTOM_DOMAIN,
        description="Адрес API пользовательского домена"
    ),
    "custom_domain_api_key": SettingDefinition(
        db_key="custom_domain.api_key",
        default_value="",
        category=SettingCategory.CUSTOM_DOMAIN,
        description="Ключ API пользовательского домена",
        is_secret=True
    ),

    # Конфигурация безопасности
    "encryption_key": SettingDefinition(
        db_key="security.encryption_key",
        default_value="your-encryption-key-change-in-production",
        category=SettingCategory.SECURITY,
        description="Ключ шифрования",
        is_secret=True
    ),

    # Конфигурация Team Manager
    "tm_enabled": SettingDefinition(
        db_key="tm.enabled",
        default_value=False,
        category=SettingCategory.GENERAL,
        description="Включить ли загрузку в Team Manager"
    ),
    "tm_api_url": SettingDefinition(
        db_key="tm.api_url",
        default_value="",
        category=SettingCategory.GENERAL,
        description="Адрес API Team Manager"
    ),
    "tm_api_key": SettingDefinition(
        db_key="tm.api_key",
        default_value="",
        category=SettingCategory.GENERAL,
        description="API Key Team Manager",
        is_secret=True
    ),

    # Конфигурация загрузки CPA
    "cpa_enabled": SettingDefinition(
        db_key="cpa.enabled",
        default_value=False,
        category=SettingCategory.CPA,
        description="Включить ли загрузку CPA"
    ),
    "cpa_api_url": SettingDefinition(
        db_key="cpa.api_url",
        default_value="",
        category=SettingCategory.CPA,
        description="Адрес API CPA"
    ),
    "cpa_api_token": SettingDefinition(
        db_key="cpa.api_token",
        default_value="",
        category=SettingCategory.CPA,
        description="Токен API CPA",
        is_secret=True
    ),

    # Конфигурация кода подтверждения
    "email_code_timeout": SettingDefinition(
        db_key="email_code.timeout",
        default_value=120,
        category=SettingCategory.EMAIL,
        description="Таймаут ожидания кода подтверждения (сек)"
    ),
    "email_code_poll_interval": SettingDefinition(
        db_key="email_code.poll_interval",
        default_value=3,
        category=SettingCategory.EMAIL,
        description="Интервал опроса кода подтверждения (сек)"
    ),

    # Конфигурация Outlook
    "outlook_provider_priority": SettingDefinition(
        db_key="outlook.provider_priority",
        default_value=["imap_old", "imap_new", "graph_api"],
        category=SettingCategory.EMAIL,
        description="Приоритет провайдеров Outlook"
    ),
    "outlook_health_failure_threshold": SettingDefinition(
        db_key="outlook.health_failure_threshold",
        default_value=5,
        category=SettingCategory.EMAIL,
        description="Порог последовательных неудач провайдера Outlook"
    ),
    "outlook_health_disable_duration": SettingDefinition(
        db_key="outlook.health_disable_duration",
        default_value=60,
        category=SettingCategory.EMAIL,
        description="Длительность отключения провайдера Outlook (сек)"
    ),
    "outlook_default_client_id": SettingDefinition(
        db_key="outlook.default_client_id",
        default_value="24d9a0ed-8787-4584-883c-2fd79308940a",
        category=SettingCategory.EMAIL,
        description="OAuth Client ID Outlook по умолчанию"
    ),

    # Конфигурация Abuzovo
    "abuzovo_enabled": SettingDefinition("abuzovo.enabled", False, SettingCategory.ABUZOVO, "Включить Abuzovo email-сервис"),
    "abuzovo_api_url": SettingDefinition("abuzovo.api_url", "https://abuzovo-bot.vercel.app", SettingCategory.ABUZOVO, "URL API Abuzovo"),
    "abuzovo_api_token": SettingDefinition("abuzovo.api_token", "", SettingCategory.ABUZOVO, "API Bearer-токен Abuzovo", is_secret=True),
    "abuzovo_default_domain_id": SettingDefinition("abuzovo.default_domain_id", "", SettingCategory.ABUZOVO, "ID домена по умолчанию для создания ящиков"),
    "abuzovo_email_type": SettingDefinition("abuzovo.email_type", "random", SettingCategory.ABUZOVO, "Тип создания ящика (random)"),
    "workspace_monitoring_enabled": SettingDefinition("workspace.monitoring_enabled", False, SettingCategory.WORKSPACE, "Включить мониторинг рабочих областей"),
    "workspace_monitoring_interval": SettingDefinition("workspace.monitoring_interval", 300, SettingCategory.WORKSPACE, "Интервал проверки в секундах"),
    "workspace_auto_kick_enabled": SettingDefinition("workspace.auto_kick_enabled", False, SettingCategory.WORKSPACE, "Автоматический кик просроченных"),
    "workspace_auto_kick_duration": SettingDefinition("workspace.auto_kick_duration", 1, SettingCategory.WORKSPACE, "Кикать если приглашён на N дней и срок истёк"),
    "workspace_auto_redistribute_enabled": SettingDefinition("workspace.auto_redistribute_enabled", False, SettingCategory.WORKSPACE, "Автоперераспределение при бане"),
    "workspace_ban_detection_enabled": SettingDefinition("workspace.ban_detection_enabled", False, SettingCategory.WORKSPACE, "Детекция бана по письмам"),
    "workspace_ban_keywords": SettingDefinition("workspace.ban_keywords", ["banned", "suspended", "violation", "restricted", "deactivated"], SettingCategory.WORKSPACE, "Ключевые слова для детекта бана в письмах"),
    "workspace_long_duration_days": SettingDefinition("workspace.long_duration_days", 30, SettingCategory.WORKSPACE, "Порог долгосрочного пользователя (дней)"),
}

# Маппинг имён атрибутов к ключам БД (для обратной совместимости)
DB_SETTING_KEYS = {name: defn.db_key for name, defn in SETTING_DEFINITIONS.items()}

# Маппинг определений типов
SETTING_TYPES: Dict[str, Type] = {
    "debug": bool,
    "webui_port": int,
    "log_retention_days": int,
    "proxy_enabled": bool,
    "proxy_port": int,
    "proxy_dynamic_enabled": bool,
    "registration_max_retries": int,
    "registration_timeout": int,
    "registration_default_password_length": int,
    "registration_sleep_min": int,
    "registration_sleep_max": int,
    "email_service_priority": dict,
    "tempmail_timeout": int,
    "tempmail_max_retries": int,
    "tm_enabled": bool,
    "cpa_enabled": bool,
    "email_code_timeout": int,
    "email_code_poll_interval": int,
    "outlook_provider_priority": list,
    "outlook_health_failure_threshold": int,
    "outlook_health_disable_duration": int,
    "abuzovo.enabled": bool,
    "workspace.monitoring_enabled": bool,
    "workspace.monitoring_interval": int,
    "workspace.auto_kick_enabled": bool,
    "workspace.auto_kick_duration": int,
    "workspace.auto_redistribute_enabled": bool,
    "workspace.ban_detection_enabled": bool,
    "workspace.ban_keywords": list,
    "workspace.long_duration_days": int,
}

# Поля, которые нужно обрабатывать как SecretStr
SECRET_FIELDS = {name for name, defn in SETTING_DEFINITIONS.items() if defn.is_secret}


def _convert_value(attr_name: str, value: str) -> Any:
    """Преобразование строкового значения из базы данных в правильный тип"""
    if attr_name in SECRET_FIELDS:
        return SecretStr(value) if value else SecretStr("")

    target_type = SETTING_TYPES.get(attr_name)
    if target_type is None:
        # Try DB key format (e.g. "workspace.ban_keywords" for attr "workspace_ban_keywords")
        defn = SETTING_DEFINITIONS.get(attr_name)
        if defn:
            target_type = SETTING_TYPES.get(defn.db_key, str)
        else:
            target_type = str

    if target_type == bool:
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes", "on")
    elif target_type == int:
        if isinstance(value, int):
            return value
        return int(value) if value else 0
    elif target_type == dict:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        import json
        import ast
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            try:
                return ast.literal_eval(value)
            except Exception:
                return {}
    elif target_type == list:
        if isinstance(value, list):
            return value
        if not value:
            return []
        import json
        import ast
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            try:
                return ast.literal_eval(value)
            except Exception:
                return []
    else:
        return value


def _value_to_string(value: Any) -> str:
    """Преобразование значения в строку для хранения в базе данных"""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (dict, list)):
        import json
        return json.dumps(value)
    elif value is None:
        return ""
    else:
        return str(value)


def init_default_settings() -> None:
    """
    Инициализация настроек по умолчанию в базе данных
    Если элемент настройки не существует, создаёт его с значением по умолчанию
    """
    try:
        from ..database.session import get_db
        from ..database.crud import get_setting, set_setting

        with get_db() as db:
            for attr_name, defn in SETTING_DEFINITIONS.items():
                existing = get_setting(db, defn.db_key)
                if not existing:
                    default_value = _value_to_string(defn.default_value)
                    set_setting(
                        db,
                        defn.db_key,
                        default_value,
                        category=defn.category.value,
                        description=defn.description
                    )
                    print(f"[Settings] Инициализация настройки по умолчанию: {defn.db_key} = {default_value if not defn.is_secret else '***'}")
    except Exception as e:
        print(f"[Settings] Ошибка инициализации настроек по умолчанию: {e}")


def _load_settings_from_db() -> Dict[str, Any]:
    """Загрузка всех настроек из базы данных"""
    try:
        from ..database.session import get_db
        from ..database.crud import get_setting

        settings_dict = {}
        with get_db() as db:
            for attr_name, defn in SETTING_DEFINITIONS.items():
                db_setting = get_setting(db, defn.db_key)
                if db_setting:
                    settings_dict[attr_name] = _convert_value(attr_name, db_setting.value)
                else:
                    # Настройка отсутствует в базе данных, используем значение по умолчанию
                    settings_dict[attr_name] = _convert_value(attr_name, _value_to_string(defn.default_value))
        return settings_dict
    except Exception as e:
        print(f"[Settings] Ошибка загрузки настроек из базы данных: {e}, используются значения по умолчанию")
        return {name: defn.default_value for name, defn in SETTING_DEFINITIONS.items()}


def _save_settings_to_db(**kwargs) -> None:
    """Сохранение настроек в базу данных"""
    try:
        from ..database.session import get_db
        from ..database.crud import set_setting

        with get_db() as db:
            for attr_name, value in kwargs.items():
                if attr_name in SETTING_DEFINITIONS:
                    defn = SETTING_DEFINITIONS[attr_name]
                    str_value = _value_to_string(value)
                    set_setting(
                        db,
                        defn.db_key,
                        str_value,
                        category=defn.category.value,
                        description=defn.description
                    )
    except Exception as e:
        print(f"[Settings] Ошибка сохранения настроек в базу данных: {e}")


class Settings(BaseModel):
    """
    Конфигурация приложения — полностью на основе хранения в базе данных
    """

    # Информация о приложении
    app_name: str = "Система автоматической регистрации OpenAI/Codex CLI"
    app_version: str = "2.0.0"
    debug: bool = False

    # Конфигурация базы данных
    database_url: str = "data/database.db"

    @field_validator('database_url', mode='before')
    @classmethod
    def validate_database_url(cls, v):
        if isinstance(v, str) and v.startswith("sqlite:///"):
            return v
        if isinstance(v, str) and not v.startswith(("sqlite:///", "postgresql://", "mysql://")):
            # Если это путь к файлу, преобразуем в SQLite URL
            if os.path.isabs(v) or ":/" not in v:
                return f"sqlite:///{v}"
        return v

    # Конфигурация Web UI
    webui_host: str = "0.0.0.0"
    webui_port: int = 8000
    webui_secret_key: SecretStr = SecretStr("your-secret-key-change-in-production")

    # Конфигурация логов
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    log_retention_days: int = 30

    # Конфигурация OpenAI
    openai_client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann"
    openai_auth_url: str = "https://auth.openai.com/oauth/authorize"
    openai_token_url: str = "https://auth.openai.com/oauth/token"
    openai_redirect_uri: str = "http://localhost:1455/auth/callback"
    openai_scope: str = "openid email profile offline_access"

    # Конфигурация прокси
    proxy_enabled: bool = False
    proxy_type: str = "http"
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 7890
    proxy_username: Optional[str] = None
    proxy_password: Optional[SecretStr] = None
    proxy_dynamic_enabled: bool = False
    proxy_dynamic_api_url: str = ""
    proxy_dynamic_api_key: Optional[SecretStr] = None
    proxy_dynamic_api_key_header: str = "X-API-Key"
    proxy_dynamic_result_field: str = ""

    @property
    def proxy_url(self) -> Optional[str]:
        """Получение полного URL прокси"""
        if not self.proxy_enabled:
            return None

        if self.proxy_type == "http":
            scheme = "http"
        elif self.proxy_type == "socks5":
            scheme = "socks5"
        else:
            return None

        auth = ""
        if self.proxy_username and self.proxy_password:
            auth = f"{self.proxy_username}:{self.proxy_password.get_secret_value()}@"

        return f"{scheme}://{auth}{self.proxy_host}:{self.proxy_port}"

    # Конфигурация регистрации
    registration_max_retries: int = 3
    registration_timeout: int = 120
    registration_default_password_length: int = 12
    registration_sleep_min: int = 5
    registration_sleep_max: int = 30

    # Конфигурация почтовых сервисов
    email_service_priority: Dict[str, int] = {"tempmail": 0, "outlook": 1, "custom_domain": 2, "abuzovo": 3}

    # Конфигурация Tempmail.lol
    tempmail_base_url: str = "https://api.tempmail.lol/v2"
    tempmail_timeout: int = 30
    tempmail_max_retries: int = 3

    # Конфигурация почты с пользовательским доменом
    custom_domain_base_url: str = ""
    custom_domain_api_key: Optional[SecretStr] = None

    # Конфигурация безопасности
    encryption_key: SecretStr = SecretStr("your-encryption-key-change-in-production")

    # Конфигурация Team Manager
    tm_enabled: bool = False
    tm_api_url: str = ""
    tm_api_key: Optional[SecretStr] = None

    # Конфигурация загрузки CPA
    cpa_enabled: bool = False
    cpa_api_url: str = ""
    cpa_api_token: SecretStr = SecretStr("")

    # Конфигурация кода подтверждения
    email_code_timeout: int = 120
    email_code_poll_interval: int = 3

    # Конфигурация Outlook
    outlook_provider_priority: List[str] = ["imap_old", "imap_new", "graph_api"]
    outlook_health_failure_threshold: int = 5
    outlook_health_disable_duration: int = 60
    outlook_default_client_id: str = "24d9a0ed-8787-4584-883c-2fd79308940a"

    # Конфигурация Abuzovo
    abuzovo_enabled: bool = False
    abuzovo_api_url: str = "https://abuzovo-bot.vercel.app"
    abuzovo_api_token: SecretStr = SecretStr("")
    abuzovo_default_domain_id: str = ""
    abuzovo_email_type: str = "random"

    # Конфигурация Workspace Manager
    workspace_monitoring_enabled: bool = False
    workspace_monitoring_interval: int = 300
    workspace_auto_kick_enabled: bool = False
    workspace_auto_kick_duration: int = 1
    workspace_auto_redistribute_enabled: bool = False
    workspace_ban_detection_enabled: bool = False
    workspace_ban_keywords: list = ["banned", "suspended", "violation", "restricted", "deactivated"]
    workspace_long_duration_days: int = 30


# Глобальный экземпляр конфигурации
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Получение глобального экземпляра конфигурации (шаблон синглтон)
    Полная загрузка конфигурации из базы данных
    """
    global _settings
    if _settings is None:
        # Сначала инициализируем настройки по умолчанию (если их нет в базе данных)
        init_default_settings()
        # Загружаем все настройки из базы данных
        settings_dict = _load_settings_from_db()
        _settings = Settings(**settings_dict)
    return _settings


def update_settings(**kwargs) -> Settings:
    """
    Обновление конфигурации и сохранение в базу данных
    """
    global _settings
    if _settings is None:
        _settings = get_settings()

    # Создание нового экземпляра конфигурации
    updated_data = _settings.model_dump()
    updated_data.update(kwargs)
    _settings = Settings(**updated_data)

    # Сохранение в базу данных
    _save_settings_to_db(**kwargs)

    return _settings


def get_database_url() -> str:
    """
    Получение URL базы данных (обработка относительных путей)
    """
    settings = get_settings()
    url = settings.database_url

    # Если URL — относительный путь, преобразуем в абсолютный
    if url.startswith("sqlite:///"):
        path = url[10:]  # Удаляем "sqlite:///"
        if not os.path.isabs(path):
            # Преобразуем в путь относительно корня проекта
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            abs_path = os.path.join(project_root, path)
            return f"sqlite:///{abs_path}"

    return url


def get_setting_definition(attr_name: str) -> Optional[SettingDefinition]:
    """Получение определения элемента настройки"""
    return SETTING_DEFINITIONS.get(attr_name)


def get_all_setting_definitions() -> Dict[str, SettingDefinition]:
    """Получение определений всех элементов настроек"""
    return SETTING_DEFINITIONS.copy()
