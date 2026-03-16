"""
Абстрактный базовый класс провайдера Outlook
"""

import abc
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from ..base import ProviderType, EmailMessage, ProviderHealth, ProviderStatus
from ..account import OutlookAccount


logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Конфигурация провайдера"""
    timeout: int = 30
    max_retries: int = 3
    proxy_url: Optional[str] = None

    # Конфигурация проверки здоровья
    health_failure_threshold: int = 3
    health_disable_duration: int = 300  # секунд


class OutlookProvider(abc.ABC):
    """
    Абстрактный базовый класс провайдера Outlook
    Определяет интерфейс, который должны реализовать все провайдеры
    """

    def __init__(
        self,
        account: OutlookAccount,
        config: Optional[ProviderConfig] = None,
    ):
        """
        Инициализация провайдера

        Args:
            account: Учётная запись Outlook
            config: Конфигурация провайдера
        """
        self.account = account
        self.config = config or ProviderConfig()

        # Состояние здоровья
        self._health = ProviderHealth(provider_type=self.provider_type)

        # Состояние подключения
        self._connected = False
        self._last_error: Optional[str] = None

    @property
    @abc.abstractmethod
    def provider_type(self) -> ProviderType:
        """Получить тип провайдера"""
        pass

    @property
    def health(self) -> ProviderHealth:
        """Получить состояние здоровья"""
        return self._health

    @property
    def is_healthy(self) -> bool:
        """Проверить, здоров ли"""
        return (
            self._health.status == ProviderStatus.HEALTHY
            and not self._health.is_disabled()
        )

    @property
    def is_connected(self) -> bool:
        """Проверить, подключён ли"""
        return self._connected

    @abc.abstractmethod
    def connect(self) -> bool:
        """
        Подключиться к сервису

        Returns:
            Успешно ли подключение
        """
        pass

    @abc.abstractmethod
    def disconnect(self):
        """Отключиться"""
        pass

    @abc.abstractmethod
    def get_recent_emails(
        self,
        count: int = 20,
        only_unseen: bool = True,
    ) -> List[EmailMessage]:
        """
        Получить последние письма

        Args:
            count: Количество для получения
            only_unseen: Только непрочитанные

        Returns:
            Список писем
        """
        pass

    @abc.abstractmethod
    def test_connection(self) -> bool:
        """
        Тестировать, работает ли подключение

        Returns:
            Работает ли подключение
        """
        pass

    def record_success(self):
        """Записать успешную операцию"""
        self._health.record_success()
        self._last_error = None
        logger.debug(f"[{self.account.email}] {self.provider_type.value} операция успешна")

    def record_failure(self, error: str):
        """Записать неудачную операцию"""
        self._health.record_failure(error)
        self._last_error = error

        # Проверить, нужно ли отключить
        if self._health.should_disable(self.config.health_failure_threshold):
            self._health.disable(self.config.health_disable_duration)
            logger.warning(
                f"[{self.account.email}] {self.provider_type.value} отключён на "
                f"{self.config.health_disable_duration} секунд, причина: {error}"
            )
        else:
            logger.warning(
                f"[{self.account.email}] {self.provider_type.value} операция не удалась "
                f"({self._health.failure_count}/{self.config.health_failure_threshold}): {error}"
            )

    def check_health(self) -> bool:
        """
        Проверить состояние здоровья

        Returns:
            Здоров ли и доступен
        """
        # Проверить, отключён ли
        if self._health.is_disabled():
            logger.debug(
                f"[{self.account.email}] {self.provider_type.value} отключён, "
                f"восстановится после {self._health.disabled_until}"
            )
            return False

        return self._health.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)

    def __enter__(self):
        """Вход в контекстный менеджер"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        self.disconnect()
        return False

    def __str__(self) -> str:
        """Строковое представление"""
        return f"{self.__class__.__name__}({self.account.email})"

    def __repr__(self) -> str:
        return self.__str__()
