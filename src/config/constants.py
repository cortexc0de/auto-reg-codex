"""
Определения констант
"""

import random
from datetime import datetime
from enum import Enum
from typing import Dict, List, Tuple


# ============================================================================
# Перечисления
# ============================================================================

class AccountStatus(str, Enum):
    """Статус аккаунта"""
    ACTIVE = "active"
    EXPIRED = "expired"
    BANNED = "banned"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """Статус задачи"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EmailServiceType(str, Enum):
    """Тип почтового сервиса"""
    TEMPMAIL = "tempmail"
    OUTLOOK = "outlook"
    CUSTOM_DOMAIN = "custom_domain"
    ABUZOVO = "abuzovo"
    AXIOMLAUNCHER = "axiomlauncher"


# ============================================================================
# Константы приложения
# ============================================================================

APP_NAME = "Система автоматической регистрации OpenAI/Codex CLI"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = "Система автоматической регистрации аккаунтов OpenAI/Codex CLI"

# ============================================================================
# Константы, связанные с OpenAI OAuth
# ============================================================================

# Параметры OAuth
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_AUTH_URL = "https://auth.openai.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
OAUTH_SCOPE = "openid email profile offline_access"

# Конечные точки API OpenAI
OPENAI_API_ENDPOINTS = {
    "sentinel": "https://sentinel.openai.com/backend-api/sentinel/req",
    "signup": "https://auth.openai.com/api/accounts/authorize/continue",
    "register": "https://auth.openai.com/api/accounts/user/register",
    "send_otp": "https://auth.openai.com/api/accounts/email-otp/send",
    "validate_otp": "https://auth.openai.com/api/accounts/email-otp/validate",
    "create_account": "https://auth.openai.com/api/accounts/create_account",
    "select_workspace": "https://auth.openai.com/api/accounts/workspace/select",
}

# Типы страниц OpenAI (для определения статуса аккаунта)
OPENAI_PAGE_TYPES = {
    "EMAIL_OTP_VERIFICATION": "email_otp_verification",  # Зарегистрированный аккаунт, требуется OTP подтверждение
    "PASSWORD_REGISTRATION": "password",  # Новый аккаунт, требуется установка пароля
}

# ============================================================================
# Константы, связанные с почтовыми сервисами
# ============================================================================

# Конечные точки API Tempmail.lol
TEMPMAIL_API_ENDPOINTS = {
    "create_inbox": "/inbox/create",
    "get_inbox": "/inbox",
}

# Конечные точки API почты с пользовательским доменом
CUSTOM_DOMAIN_API_ENDPOINTS = {
    "get_config": "/api/config",
    "create_email": "/api/emails/generate",
    "list_emails": "/api/emails",
    "get_email_messages": "/api/emails/{emailId}",
    "delete_email": "/api/emails/{emailId}",
    "get_message": "/api/emails/{emailId}/{messageId}",
}

# Конечные точки API Abuzovo
ABUZOVO_API_ENDPOINTS = {
    "domains": "/api/v1/domains",
    "mailboxes": "/api/v1/mailboxes",
    "messages": "/api/v1/messages",
}

# Конечные точки API AxiomLauncher
AXIOMLAUNCHER_API_ENDPOINTS = {
    "domains": "/api/v1/domains",
    "mailboxes": "/api/v1/mailboxes",
    "messages": "/api/v1/messages",
}

# Конфигурация почтовых сервисов по умолчанию
EMAIL_SERVICE_DEFAULTS = {
    "tempmail": {
        "base_url": "https://api.tempmail.lol/v2",
        "timeout": 30,
        "max_retries": 3,
    },
    "outlook": {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "smtp_server": "smtp.office365.com",
        "smtp_port": 587,
        "timeout": 30,
    },
    "custom_domain": {
        "base_url": "",  # Требуется настройка пользователем
        "api_key_header": "X-API-Key",
        "timeout": 30,
        "max_retries": 3,
    }
}

# ============================================================================
# Константы, связанные с процессом регистрации
# ============================================================================

# Код подтверждения
OTP_CODE_PATTERN = r"(?<!\d)(\d{6})(?!\d)"
OTP_MAX_ATTEMPTS = 40  # Максимальное количество попыток опроса

# Регулярные выражения для извлечения кода подтверждения (расширенная версия)
# Простое совпадение: любые 6 цифр
OTP_CODE_SIMPLE_PATTERN = r"(?<!\d)(\d{6})(?!\d)"
# Семантическое совпадение: код подтверждения с контекстом (например, "code is 123456", "код подтверждения 123456")
OTP_CODE_SEMANTIC_PATTERN = r'(?:code\s+is|验证码[是为]?\s*[:：]?\s*)(\d{6})'

# Отправители писем подтверждения OpenAI
OPENAI_EMAIL_SENDERS = [
    "noreply@openai.com",
    "no-reply@openai.com",
    "@openai.com",     # Точное совпадение домена
    ".openai.com",     # Совпадение поддомена (например, otp@tm1.openai.com)
]

# Ключевые слова писем подтверждения OpenAI
OPENAI_VERIFICATION_KEYWORDS = [
    "verify your email",
    "verification code",
    "验证码",
    "your openai code",
    "code is",
    "one-time code",
]

# Генерация пароля
PASSWORD_CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
DEFAULT_PASSWORD_LENGTH = 12

# Генерация информации о пользователе (для регистрации)

# Распространённые английские имена
FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
    "Emma", "Olivia", "Ava", "Isabella", "Sophia", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn",
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery", "Quinn", "Skyler",
    "Liam", "Noah", "Ethan", "Lucas", "Mason", "Oliver", "Elijah", "Aiden", "Henry", "Sebastian",
    "Grace", "Lily", "Chloe", "Zoey", "Nora", "Aria", "Hazel", "Aurora", "Stella", "Ivy"
]

def generate_random_user_info() -> dict:
    """
    Генерация случайной информации о пользователе

    Returns:
        Словарь с полями name и birthdate
    """
    # Случайный выбор имени
    name = random.choice(FIRST_NAMES)

    # Генерация случайной даты рождения (18-45 лет)
    current_year = datetime.now().year
    birth_year = random.randint(current_year - 45, current_year - 18)
    birth_month = random.randint(1, 12)
    # Определение количества дней по месяцу
    if birth_month in [1, 3, 5, 7, 8, 10, 12]:
        birth_day = random.randint(1, 31)
    elif birth_month in [4, 6, 9, 11]:
        birth_day = random.randint(1, 30)
    else:
        # Февраль, упрощённая обработка
        birth_day = random.randint(1, 28)

    birthdate = f"{birth_year}-{birth_month:02d}-{birth_day:02d}"

    return {
        "name": name,
        "birthdate": birthdate
    }

# Значения по умолчанию для совместимости
DEFAULT_USER_INFO = {
    "name": "Neo",
    "birthdate": "2000-02-20",
}

# ============================================================================
# Константы, связанные с прокси
# ============================================================================

PROXY_TYPES = ["http", "socks5", "socks5h"]
DEFAULT_PROXY_CONFIG = {
    "enabled": False,
    "type": "http",
    "host": "127.0.0.1",
    "port": 7890,
}

# ============================================================================
# Константы, связанные с базой данных
# ============================================================================

# Имена таблиц базы данных
DB_TABLE_NAMES = {
    "accounts": "accounts",
    "email_services": "email_services",
    "registration_tasks": "registration_tasks",
    "settings": "settings",
}

# Настройки по умолчанию
DEFAULT_SETTINGS = [
    # (ключ, значение, описание, категория)
    ("system.name", APP_NAME, "Название системы", "general"),
    ("system.version", APP_VERSION, "Версия системы", "general"),
    ("logs.retention_days", "30", "Срок хранения логов (дней)", "general"),
    ("openai.client_id", OAUTH_CLIENT_ID, "OpenAI OAuth Client ID", "openai"),
    ("openai.auth_url", OAUTH_AUTH_URL, "Адрес аутентификации OpenAI", "openai"),
    ("openai.token_url", OAUTH_TOKEN_URL, "Адрес токена OpenAI", "openai"),
    ("openai.redirect_uri", OAUTH_REDIRECT_URI, "Адрес обратного вызова OpenAI", "openai"),
    ("openai.scope", OAUTH_SCOPE, "Области разрешений OpenAI", "openai"),
    ("proxy.enabled", "false", "Включить ли прокси", "proxy"),
    ("proxy.type", "http", "Тип прокси (http/socks5)", "proxy"),
    ("proxy.host", "127.0.0.1", "Хост прокси", "proxy"),
    ("proxy.port", "7890", "Порт прокси", "proxy"),
    ("registration.max_retries", "3", "Максимальное количество повторных попыток", "registration"),
    ("registration.timeout", "120", "Таймаут (сек)", "registration"),
    ("registration.default_password_length", "12", "Длина пароля по умолчанию", "registration"),
    ("webui.host", "0.0.0.0", "Хост прослушивания Web UI", "webui"),
    ("webui.port", "8000", "Порт прослушивания Web UI", "webui"),
    ("webui.debug", "true", "Режим отладки", "webui"),
]

# ============================================================================
# Константы, связанные с Web UI
# ============================================================================

# События WebSocket
WEBSOCKET_EVENTS = {
    "CONNECT": "connect",
    "DISCONNECT": "disconnect",
    "LOG": "log",
    "STATUS": "status",
    "ERROR": "error",
    "COMPLETE": "complete",
}

# Коды статусов API ответов
API_STATUS_CODES = {
    "SUCCESS": 200,
    "CREATED": 201,
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "INTERNAL_ERROR": 500,
}

# Пагинация
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ============================================================================
# Сообщения об ошибках
# ============================================================================

ERROR_MESSAGES = {
    # Общие ошибки
    "DATABASE_ERROR": "Ошибка операции с базой данных",
    "CONFIG_ERROR": "Ошибка конфигурации",
    "NETWORK_ERROR": "Ошибка сетевого подключения",
    "TIMEOUT": "Превышено время ожидания",
    "VALIDATION_ERROR": "Ошибка валидации параметров",

    # Ошибки почтовых сервисов
    "EMAIL_SERVICE_UNAVAILABLE": "Почтовый сервис недоступен",
    "EMAIL_CREATION_FAILED": "Ошибка создания почтового ящика",
    "OTP_NOT_RECEIVED": "Код подтверждения не получен",
    "OTP_INVALID": "Недопустимый код подтверждения",

    # Ошибки, связанные с OpenAI
    "OPENAI_AUTH_FAILED": "Ошибка аутентификации OpenAI",
    "OPENAI_RATE_LIMIT": "Ограничение скорости API OpenAI",
    "OPENAI_CAPTCHA": "Встречена капча",

    # Ошибки прокси
    "PROXY_FAILED": "Ошибка подключения прокси",
    "PROXY_AUTH_FAILED": "Ошибка аутентификации прокси",

    # Ошибки аккаунтов
    "ACCOUNT_NOT_FOUND": "Аккаунт не существует",
    "ACCOUNT_ALREADY_EXISTS": "Аккаунт уже существует",
    "ACCOUNT_INVALID": "Недопустимый аккаунт",

    # Ошибки задач
    "TASK_NOT_FOUND": "Задача не существует",
    "TASK_ALREADY_RUNNING": "Задача уже выполняется",
    "TASK_CANCELLED": "Задача отменена",
}

# ============================================================================
# Регулярные выражения
# ============================================================================

REGEX_PATTERNS = {
    "EMAIL": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    "URL": r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+",
    "IP_ADDRESS": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "OTP_CODE": OTP_CODE_PATTERN,
}

# ============================================================================
# Константы времени
# ============================================================================

TIME_CONSTANTS = {
    "SECOND": 1,
    "MINUTE": 60,
    "HOUR": 3600,
    "DAY": 86400,
    "WEEK": 604800,
}


# ============================================================================
# Константы, связанные с Microsoft/Outlook
# ============================================================================

# Конечные точки токенов Microsoft OAuth2
MICROSOFT_TOKEN_ENDPOINTS = {
    # Конечная точка для старого IMAP
    "LIVE": "https://login.live.com/oauth20_token.srf",
    # Конечная точка для нового IMAP (требуется определённый scope)
    "CONSUMERS": "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
    # Конечная точка для Graph API
    "COMMON": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
}

# Конфигурация IMAP серверов
OUTLOOK_IMAP_SERVERS = {
    "OLD": "outlook.office365.com",  # Старый IMAP
    "NEW": "outlook.live.com",       # Новый IMAP
}

# Области Microsoft OAuth2
MICROSOFT_SCOPES = {
    # Старый IMAP не требует определённого scope
    "IMAP_OLD": "",
    # Scope, необходимый для нового IMAP
    "IMAP_NEW": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
    # Scope, необходимый для Graph API
    "GRAPH_API": "https://graph.microsoft.com/.default",
}

# Приоритет провайдеров Outlook по умолчанию
OUTLOOK_PROVIDER_PRIORITY = ["imap_new", "imap_old", "graph_api"]
