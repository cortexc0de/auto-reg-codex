"""
Абстрактный базовый класс почтового сервиса
Базовый класс для всех реализаций почтовых сервисов
"""

import abc
import logging
from typing import Optional, Dict, Any, List
from enum import Enum

from ..config.constants import EmailServiceType


logger = logging.getLogger(__name__)


class EmailServiceError(Exception):
    """Исключение почтового сервиса"""
    pass


class EmailServiceStatus(Enum):
    """Статус почтового сервиса"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class BaseEmailService(abc.ABC):
    """
    Абстрактный базовый класс почтового сервиса

    Все почтовые сервисы должны реализовать этот интерфейс
    """

    def __init__(self, service_type: EmailServiceType, name: str = None):
        """
        Инициализация почтового сервиса

        Args:
            service_type: Тип сервиса
            name: Название сервиса
        """
        self.service_type = service_type
        self.name = name or f"{service_type.value}_service"
        self._status = EmailServiceStatus.HEALTHY
        self._last_error = None

    @property
    def status(self) -> EmailServiceStatus:
        """Получить статус сервиса"""
        return self._status

    @property
    def last_error(self) -> Optional[str]:
        """Получить информацию о последней ошибке"""
        return self._last_error

    @abc.abstractmethod
    def create_email(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Создать новый почтовый адрес

        Args:
            config: Параметры конфигурации, такие как префикс почты, домен и т.д.

        Returns:
            Словарь с информацией о почте, содержащий как минимум:
            - email: Почтовый адрес
            - service_id: ID в почтовом сервисе
            - token/credentials: Учётные данные для доступа (при необходимости)

        Raises:
            EmailServiceError: Ошибка создания
        """
        pass

    @abc.abstractmethod
    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = 120,
        pattern: str = r"(?<!\d)(\d{6})(?!\d)",
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        """
        Получить код подтверждения

        Args:
            email: Почтовый адрес
            email_id: ID в почтовом сервисе (при необходимости)
            timeout: Таймаут (в секундах)
            pattern: Регулярное выражение для кода подтверждения
            otp_sent_at: Временная метка отправки OTP для фильтрации старых писем

        Returns:
            Строка с кодом подтверждения, None если таймаут или код не найден

        Raises:
            EmailServiceError: Ошибка сервиса
        """
        pass

    @abc.abstractmethod
    def list_emails(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Показать все почтовые ящики (если сервис поддерживает)

        Args:
            **kwargs: Другие параметры

        Returns:
            Список почтовых ящиков

        Raises:
            EmailServiceError: Ошибка сервиса
        """
        pass

    @abc.abstractmethod
    def delete_email(self, email_id: str) -> bool:
        """
        Удалить почтовый ящик

        Args:
            email_id: ID в почтовом сервисе

        Returns:
            Успешно ли удаление

        Raises:
            EmailServiceError: Ошибка сервиса
        """
        pass

    @abc.abstractmethod
    def check_health(self) -> bool:
        """
        Проверить состояние здоровья сервиса

        Returns:
            Здоров ли сервис

        Note:
            Этот метод не должен выбрасывать исключения, следует перехватывать исключения и возвращать False
        """
        pass

    def get_email_info(self, email_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о почтовом ящике (опциональная реализация)

        Args:
            email_id: ID в почтовом сервисе

        Returns:
            Словарь с информацией о почтовом ящике, None если не существует
        """
        # Реализация по умолчанию: поиск перебором списка
        for email_info in self.list_emails():
            if email_info.get("id") == email_id:
                return email_info
        return None

    def wait_for_email(
        self,
        email: str,
        email_id: str = None,
        timeout: int = 120,
        check_interval: int = 3,
        expected_sender: str = None,
        expected_subject: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Ожидать и получить письмо (опциональная реализация)

        Args:
            email: Почтовый адрес
            email_id: ID в почтовом сервисе
            timeout: Таймаут (в секундах)
            check_interval: Интервал проверки (в секундах)
            expected_sender: Ожидаемый отправитель (проверка вхождения)
            expected_subject: Ожидаемая тема (проверка вхождения)

        Returns:
            Словарь с информацией о письме, None при таймауте
        """
        import time
        from datetime import datetime

        start_time = time.time()
        last_email_id = None

        while time.time() - start_time < timeout:
            try:
                emails = self.list_emails()
                for email_info in emails:
                    email_data = email_info.get("email", {})
                    current_email_id = email_info.get("id")

                    # Проверить, является ли это новым письмом
                    if last_email_id and current_email_id == last_email_id:
                        continue

                    # Проверить почтовый адрес
                    if email_data.get("address") != email:
                        continue

                    # Получить список писем
                    messages = self.get_email_messages(email_id or current_email_id)
                    for message in messages:
                        # Проверить отправителя
                        if expected_sender and expected_sender not in message.get("from", ""):
                            continue

                        # Проверить тему
                        if expected_subject and expected_subject not in message.get("subject", ""):
                            continue

                        # Вернуть информацию о письме
                        return {
                            "id": message.get("id"),
                            "from": message.get("from"),
                            "subject": message.get("subject"),
                            "content": message.get("content"),
                            "received_at": message.get("received_at"),
                            "email_info": email_info
                        }

                    # Обновить ID последнего проверенного письма
                    if messages:
                        last_email_id = current_email_id

            except Exception as e:
                logger.warning(f"Ошибка при ожидании письма: {e}")

            time.sleep(check_interval)

        return None

    def get_email_messages(self, email_id: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Получить список писем в почтовом ящике (опциональная реализация)

        Args:
            email_id: ID в почтовом сервисе
            **kwargs: Другие параметры

        Returns:
            Список писем

        Note:
            Это опциональный метод, некоторые сервисы могут не поддерживать его
        """
        raise NotImplementedError("Этот почтовый сервис не поддерживает получение списка писем")

    def get_message_content(self, email_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить содержимое письма (опциональная реализация)

        Args:
            email_id: ID в почтовом сервисе
            message_id: ID письма

        Returns:
            Словарь с содержимым письма

        Note:
            Это опциональный метод, некоторые сервисы могут не поддерживать его
        """
        raise NotImplementedError("Этот почтовый сервис не поддерживает получение содержимого писем")

    def update_status(self, success: bool, error: Exception = None):
        """
        Обновить статус сервиса

        Args:
            success: Успешна ли операция
            error: Информация об ошибке
        """
        if success:
            self._status = EmailServiceStatus.HEALTHY
            self._last_error = None
        else:
            self._status = EmailServiceStatus.DEGRADED
            if error:
                self._last_error = str(error)

    def __str__(self) -> str:
        """Строковое представление"""
        return f"{self.name} ({self.service_type.value})"


class EmailServiceFactory:
    """Фабрика почтовых сервисов"""

    _registry: Dict[EmailServiceType, type] = {}

    @classmethod
    def register(cls, service_type: EmailServiceType, service_class: type):
        """
        Зарегистрировать класс почтового сервиса

        Args:
            service_type: Тип сервиса
            service_class: Класс сервиса
        """
        if not issubclass(service_class, BaseEmailService):
            raise TypeError(f"{service_class} должен быть подклассом BaseEmailService")
        cls._registry[service_type] = service_class
        logger.info(f"Зарегистрирован почтовый сервис: {service_type.value} -> {service_class.__name__}")

    @classmethod
    def create(
        cls,
        service_type: EmailServiceType,
        config: Dict[str, Any],
        name: str = None
    ) -> BaseEmailService:
        """
        Создать экземпляр почтового сервиса

        Args:
            service_type: Тип сервиса
            config: Конфигурация сервиса
            name: Название сервиса

        Returns:
            Экземпляр почтового сервиса

        Raises:
            ValueError: Тип сервиса не зарегистрирован или конфигурация некорректна
        """
        if service_type not in cls._registry:
            raise ValueError(f"Незарегистрированный тип сервиса: {service_type.value}")

        service_class = cls._registry[service_type]
        try:
            instance = service_class(config, name)
            return instance
        except Exception as e:
            raise ValueError(f"Не удалось создать почтовый сервис: {e}")

    @classmethod
    def get_available_services(cls) -> List[EmailServiceType]:
        """
        Получить все зарегистрированные типы сервисов

        Returns:
            Список зарегистрированных типов сервисов
        """
        return list(cls._registry.keys())

    @classmethod
    def get_service_class(cls, service_type: EmailServiceType) -> Optional[type]:
        """
        Получить класс сервиса

        Args:
            service_type: Тип сервиса

        Returns:
            Класс сервиса, None если не зарегистрирован
        """
        return cls._registry.get(service_type)


# Упрощённая фабричная функция
def create_email_service(
    service_type: EmailServiceType,
    config: Dict[str, Any],
    name: str = None
) -> BaseEmailService:
    """
    Создать почтовый сервис (упрощённая фабричная функция)

    Args:
        service_type: Тип сервиса
        config: Конфигурация сервиса
        name: Название сервиса

    Returns:
        Экземпляр почтового сервиса
    """
    return EmailServiceFactory.create(service_type, config, name)
