"""
Общие вспомогательные функции
"""

import os
import sys
import json
import time
import random
import string
import secrets
import hashlib
import logging
import base64
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Callable
from pathlib import Path

from ..config.constants import PASSWORD_CHARSET, DEFAULT_PASSWORD_LENGTH
from ..config.settings import get_settings


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
) -> logging.Logger:
    """
    Настройка системы логирования

    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Путь к файлу логов, если не указан — вывод только в консоль
        log_format: Формат логов

    Returns:
        Корневой логгер
    """
    # Установка уровня логирования
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Очистка существующих обработчиков
    root_logger.handlers.clear()

    # Создание форматтера
    formatter = logging.Formatter(log_format)

    # Обработчик консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)
    root_logger.addHandler(console_handler)

    # Обработчик файла (если указан файл логов)
    if log_file:
        # Убедиться, что директория логов существует
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(numeric_level)
        root_logger.addHandler(file_handler)

    return root_logger


def generate_password(length: int = DEFAULT_PASSWORD_LENGTH) -> str:
    """
    Генерация случайного пароля

    Args:
        length: Длина пароля

    Returns:
        Строка случайного пароля
    """
    if length < 4:
        length = 4

    # Убедиться, что пароль содержит хотя бы одну заглавную букву, одну строчную букву и одну цифру
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
    ]

    # Добавить остальные символы
    password.extend(secrets.choice(PASSWORD_CHARSET) for _ in range(length - 3))

    # Случайное перемешивание
    secrets.SystemRandom().shuffle(password)

    return ''.join(password)


def generate_random_string(length: int = 8) -> str:
    """
    Генерация случайной строки (только буквы)

    Args:
        length: Длина строки

    Returns:
        Случайная строка
    """
    chars = string.ascii_letters
    return ''.join(secrets.choice(chars) for _ in range(length))


def generate_uuid() -> str:
    """Генерация строки UUID"""
    return str(uuid.uuid4())


def get_timestamp() -> int:
    """Получение текущей метки времени (в секундах)"""
    return int(time.time())


def format_datetime(dt: Optional[datetime] = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Форматирование даты и времени

    Args:
        dt: Объект даты и времени, если None — используется текущее время
        fmt: Строка формата

    Returns:
        Отформатированная строка
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime(fmt)


def parse_datetime(dt_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> Optional[datetime]:
    """
    Парсинг строки даты и времени

    Args:
        dt_str: Строка даты и времени
        fmt: Строка формата

    Returns:
        Объект даты и времени, или None в случае ошибки парсинга
    """
    try:
        return datetime.strptime(dt_str, fmt)
    except (ValueError, TypeError):
        return None


def human_readable_size(size_bytes: int) -> str:
    """
    Преобразование размера в байтах в человекочитаемый формат

    Args:
        size_bytes: Размер в байтах

    Returns:
        Человекочитаемая строка
    """
    if size_bytes < 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0

    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1

    return f"{size_bytes:.2f} {units[unit_index]}"


def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    Функция повторных попыток с экспоненциальной задержкой

    Args:
        func: Функция для повторного вызова
        max_retries: Максимальное количество повторных попыток
        base_delay: Базовая задержка (в секундах)
        max_delay: Максимальная задержка (в секундах)
        backoff_factor: Коэффициент задержки
        exceptions: Типы перехватываемых исключений

    Returns:
        Возвращаемое значение функции

    Raises:
        Исключение последней попытки
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions as e:
            last_exception = e

            # Если это последняя попытка, выбросить исключение
            if attempt == max_retries:
                break

            # Вычисление времени задержки
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)

            # Добавление случайного джиттера
            delay *= (0.5 + random.random())

            # Запись в лог
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Попытка {func.__name__} не удалась (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                f"Ожидание {delay:.2f} сек. перед повторной попыткой..."
            )

            time.sleep(delay)

    # Все повторные попытки не удались, выбросить последнее исключение
    raise last_exception


class RetryDecorator:
    """Класс декоратора повторных попыток"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        exceptions: tuple = (Exception,)
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.exceptions = exceptions

    def __call__(self, func: Callable) -> Callable:
        """Вызов декоратора"""
        def wrapper(*args, **kwargs):
            def func_to_retry():
                return func(*args, **kwargs)

            return retry_with_backoff(
                func_to_retry,
                max_retries=self.max_retries,
                base_delay=self.base_delay,
                max_delay=self.max_delay,
                backoff_factor=self.backoff_factor,
                exceptions=self.exceptions
            )

        return wrapper


def validate_email(email: str) -> bool:
    """
    Проверка формата адреса электронной почты

    Args:
        email: Адрес электронной почты

    Returns:
        Валидный или нет
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_url(url: str) -> bool:
    """
    Проверка формата URL

    Args:
        url: URL

    Returns:
        Валидный или нет
    """
    pattern = r"^https?://[^\s/$.?#].[^\s]*$"
    return bool(re.match(pattern, url))


def sanitize_filename(filename: str) -> str:
    """
    Очистка имени файла, удаление небезопасных символов

    Args:
        filename: Исходное имя файла

    Returns:
        Очищенное имя файла
    """
    # Удаление опасных символов
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Удаление управляющих символов
    filename = ''.join(char for char in filename if ord(char) >= 32)
    # Ограничение длины
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    return filename


def read_json_file(filepath: str) -> Optional[Dict[str, Any]]:
    """
    Чтение JSON-файла

    Args:
        filepath: Путь к файлу

    Returns:
        Данные JSON, или None в случае ошибки чтения
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
        logging.getLogger(__name__).warning(f"Не удалось прочитать JSON-файл: {filepath} - {e}")
        return None


def write_json_file(filepath: str, data: Dict[str, Any], indent: int = 2) -> bool:
    """
    Запись JSON-файла

    Args:
        filepath: Путь к файлу
        data: Данные для записи
        indent: Количество пробелов отступа

    Returns:
        Успешно или нет
    """
    try:
        # Убедиться, что директория существует
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)

        return True
    except (IOError, TypeError) as e:
        logging.getLogger(__name__).error(f"Не удалось записать JSON-файл: {filepath} - {e}")
        return False


def get_project_root() -> Path:
    """
    Получение корневой директории проекта

    Returns:
        Объект Path корневой директории проекта
    """
    # Директория текущего файла
    current_dir = Path(__file__).parent

    # Поиск вверх до корневой директории проекта (содержащей pyproject.toml или setup.py)
    for parent in [current_dir] + list(current_dir.parents):
        if (parent / "pyproject.toml").exists() or (parent / "setup.py").exists():
            return parent

    # Если не найдено, возвращаем родительскую директорию текущей
    return current_dir.parent


def get_data_dir() -> Path:
    """
    Получение директории данных

    Returns:
        Объект Path директории данных
    """
    settings = get_settings()
    data_dir = Path(settings.database_url).parent

    # Если database_url — это SQLite URL, извлекаем путь
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url[10:]  # Удаляем "sqlite:///"
        data_dir = Path(db_path).parent

    # Убедиться, что директория существует
    data_dir.mkdir(parents=True, exist_ok=True)

    return data_dir


def get_logs_dir() -> Path:
    """
    Получение директории логов

    Returns:
        Объект Path директории логов
    """
    settings = get_settings()
    log_file = Path(settings.log_file)
    log_dir = log_file.parent

    # Убедиться, что директория существует
    log_dir.mkdir(parents=True, exist_ok=True)

    return log_dir


def format_duration(seconds: int) -> str:
    """
    Форматирование продолжительности

    Args:
        seconds: Количество секунд

    Returns:
        Отформатированная строка продолжительности
    """
    if seconds < 60:
        return f"{seconds} сек."

    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} мин. {seconds} сек."

    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} ч. {minutes} мин."

    days, hours = divmod(hours, 24)
    return f"{days} дн. {hours} ч."


def mask_sensitive_data(data: Union[str, Dict, List], mask_char: str = "*") -> Union[str, Dict, List]:
    """
    Маскирование конфиденциальных данных

    Args:
        data: Данные для маскирования
        mask_char: Символ маски

    Returns:
        Замаскированные данные
    """
    if isinstance(data, str):
        # Если это email, маскируем среднюю часть
        if "@" in data:
            local, domain = data.split("@", 1)
            if len(local) > 2:
                masked_local = local[0] + mask_char * (len(local) - 2) + local[-1]
            else:
                masked_local = mask_char * len(local)
            return f"{masked_local}@{domain}"

        # Если это токен или ключ, маскируем большую часть содержимого
        if len(data) > 10:
            return data[:4] + mask_char * (len(data) - 8) + data[-4:]
        return mask_char * len(data)

    elif isinstance(data, dict):
        masked_dict = {}
        for key, value in data.items():
            # Имена конфиденциальных полей
            sensitive_keys = ["password", "token", "secret", "key", "auth", "credential"]
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                masked_dict[key] = mask_sensitive_data(value, mask_char)
            else:
                masked_dict[key] = value
        return masked_dict

    elif isinstance(data, list):
        return [mask_sensitive_data(item, mask_char) for item in data]

    return data


def calculate_md5(data: Union[str, bytes]) -> str:
    """
    Вычисление хеша MD5

    Args:
        data: Данные для хеширования

    Returns:
        Строка хеша MD5
    """
    if isinstance(data, str):
        data = data.encode('utf-8')

    return hashlib.md5(data).hexdigest()


def calculate_sha256(data: Union[str, bytes]) -> str:
    """
    Вычисление хеша SHA256

    Args:
        data: Данные для хеширования

    Returns:
        Строка хеша SHA256
    """
    if isinstance(data, str):
        data = data.encode('utf-8')

    return hashlib.sha256(data).hexdigest()


def base64_encode(data: Union[str, bytes]) -> str:
    """Кодирование Base64"""
    if isinstance(data, str):
        data = data.encode('utf-8')

    return base64.b64encode(data).decode('utf-8')


def base64_decode(data: str) -> str:
    """Декодирование Base64"""
    try:
        decoded = base64.b64decode(data)
        return decoded.decode('utf-8')
    except (base64.binascii.Error, UnicodeDecodeError):
        return ""


class Timer:
    """Контекстный менеджер таймера"""

    def __init__(self, name: str = "Операция"):
        self.name = name
        self.start_time = None
        self.elapsed = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self.start_time
        logger = logging.getLogger(__name__)
        logger.debug(f"{self.name} заняла: {self.elapsed:.2f} сек.")

    def get_elapsed(self) -> float:
        """Получение прошедшего времени (в секундах)"""
        if self.elapsed is not None:
            return self.elapsed
        if self.start_time is not None:
            return time.time() - self.start_time
        return 0.0
