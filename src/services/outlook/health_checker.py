"""
Проверка здоровья и управление переключением при сбоях
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from .base import ProviderType, ProviderHealth, ProviderStatus
from .providers.base import OutlookProvider


logger = logging.getLogger(__name__)


class HealthChecker:
    """
    Менеджер проверки здоровья
    Отслеживает состояние здоровья каждого провайдера, управляет переключением при сбоях
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        disable_duration: int = 300,
        recovery_check_interval: int = 60,
    ):
        """
        Инициализация проверки здоровья

        Args:
            failure_threshold: Порог последовательных неудач, после превышения — отключение
            disable_duration: Длительность отключения (в секундах)
            recovery_check_interval: Интервал проверки восстановления (в секундах)
        """
        self.failure_threshold = failure_threshold
        self.disable_duration = disable_duration
        self.recovery_check_interval = recovery_check_interval

        # Состояние здоровья провайдеров: ProviderType -> ProviderHealth
        self._health_status: Dict[ProviderType, ProviderHealth] = {}
        self._lock = threading.Lock()

        # Инициализация состояния здоровья всех провайдеров
        for provider_type in ProviderType:
            self._health_status[provider_type] = ProviderHealth(
                provider_type=provider_type
            )

    def get_health(self, provider_type: ProviderType) -> ProviderHealth:
        """Получить состояние здоровья провайдера"""
        with self._lock:
            return self._health_status.get(provider_type, ProviderHealth(provider_type=provider_type))

    def record_success(self, provider_type: ProviderType):
        """Записать успешную операцию"""
        with self._lock:
            health = self._health_status.get(provider_type)
            if health:
                health.record_success()
                logger.debug(f"{provider_type.value} успех записан")

    def record_failure(self, provider_type: ProviderType, error: str):
        """Записать неудачную операцию"""
        with self._lock:
            health = self._health_status.get(provider_type)
            if health:
                health.record_failure(error)

                # Проверить, нужно ли отключить
                if health.should_disable(self.failure_threshold):
                    health.disable(self.disable_duration)
                    logger.warning(
                        f"{provider_type.value} отключён на {self.disable_duration} секунд, "
                        f"причина: {error}"
                    )

    def is_available(self, provider_type: ProviderType) -> bool:
        """
        Проверить, доступен ли провайдер

        Args:
            provider_type: Тип провайдера

        Returns:
            Доступен ли
        """
        health = self.get_health(provider_type)

        # Проверить, отключён ли
        if health.is_disabled():
            remaining = (health.disabled_until - datetime.now()).total_seconds()
            logger.debug(
                f"{provider_type.value} отключён, осталось {int(remaining)} секунд"
            )
            return False

        return health.status != ProviderStatus.DISABLED

    def get_available_providers(
        self,
        priority_order: Optional[List[ProviderType]] = None,
    ) -> List[ProviderType]:
        """
        Получить список доступных провайдеров

        Args:
            priority_order: Порядок приоритета, по умолчанию [IMAP_NEW, IMAP_OLD, GRAPH_API]

        Returns:
            Список доступных провайдеров
        """
        if priority_order is None:
            priority_order = [
                ProviderType.IMAP_NEW,
                ProviderType.IMAP_OLD,
                ProviderType.GRAPH_API,
            ]

        available = []
        for provider_type in priority_order:
            if self.is_available(provider_type):
                available.append(provider_type)

        return available

    def get_next_available_provider(
        self,
        priority_order: Optional[List[ProviderType]] = None,
    ) -> Optional[ProviderType]:
        """
        Получить следующий доступный провайдер

        Args:
            priority_order: Порядок приоритета

        Returns:
            Тип доступного провайдера, None если нет доступных
        """
        available = self.get_available_providers(priority_order)
        return available[0] if available else None

    def force_disable(self, provider_type: ProviderType, duration: Optional[int] = None):
        """
        Принудительно отключить провайдер

        Args:
            provider_type: Тип провайдера
            duration: Длительность отключения (в секундах), по умолчанию используется значение из конфигурации
        """
        with self._lock:
            health = self._health_status.get(provider_type)
            if health:
                health.disable(duration or self.disable_duration)
                logger.warning(f"{provider_type.value} принудительно отключён")

    def force_enable(self, provider_type: ProviderType):
        """
        Принудительно включить провайдер

        Args:
            provider_type: Тип провайдера
        """
        with self._lock:
            health = self._health_status.get(provider_type)
            if health:
                health.enable()
                logger.info(f"{provider_type.value} включён")

    def get_all_health_status(self) -> Dict[str, Any]:
        """
        Получить состояние здоровья всех провайдеров

        Returns:
            Словарь состояния здоровья
        """
        with self._lock:
            return {
                provider_type.value: health.to_dict()
                for provider_type, health in self._health_status.items()
            }

    def check_and_recover(self):
        """
        Проверить и восстановить отключённые провайдеры

        Если время отключения истекло, автоматически восстановить провайдер
        """
        with self._lock:
            for provider_type, health in self._health_status.items():
                if health.is_disabled():
                    # Проверить, можно ли восстановить
                    if health.disabled_until and datetime.now() >= health.disabled_until:
                        health.enable()
                        logger.info(f"{provider_type.value} автоматически восстановлен")

    def reset_all(self):
        """Сбросить состояние здоровья всех провайдеров"""
        with self._lock:
            for provider_type in ProviderType:
                self._health_status[provider_type] = ProviderHealth(
                    provider_type=provider_type
                )
            logger.info("Состояние здоровья всех провайдеров сброшено")


class FailoverManager:
    """
    Менеджер переключения при сбоях
    Управляет автоматическим переключением между провайдерами
    """

    def __init__(
        self,
        health_checker: HealthChecker,
        priority_order: Optional[List[ProviderType]] = None,
    ):
        """
        Инициализация менеджера переключения при сбоях

        Args:
            health_checker: Проверка здоровья
            priority_order: Порядок приоритета провайдеров
        """
        self.health_checker = health_checker
        self.priority_order = priority_order or [
            ProviderType.IMAP_NEW,
            ProviderType.IMAP_OLD,
            ProviderType.GRAPH_API,
        ]

        # Индекс текущего используемого провайдера
        self._current_index = 0
        self._lock = threading.Lock()

    def get_current_provider(self) -> Optional[ProviderType]:
        """
        Получить текущий провайдер

        Returns:
            Тип текущего провайдера, None если нет доступных
        """
        available = self.health_checker.get_available_providers(self.priority_order)
        if not available:
            return None

        with self._lock:
            # Попытаться использовать текущий индекс
            if self._current_index < len(available):
                return available[self._current_index]
            return available[0]

    def switch_to_next(self) -> Optional[ProviderType]:
        """
        Переключиться на следующий провайдер

        Returns:
            Тип следующего провайдера, None если нет доступных
        """
        available = self.health_checker.get_available_providers(self.priority_order)
        if not available:
            return None

        with self._lock:
            self._current_index = (self._current_index + 1) % len(available)
            next_provider = available[self._current_index]
            logger.info(f"Переключение на провайдер: {next_provider.value}")
            return next_provider

    def on_provider_success(self, provider_type: ProviderType):
        """
        Вызывается при успехе провайдера

        Args:
            provider_type: Тип провайдера
        """
        self.health_checker.record_success(provider_type)

        # Сбросить индекс на успешный провайдер
        with self._lock:
            available = self.health_checker.get_available_providers(self.priority_order)
            if provider_type in available:
                self._current_index = available.index(provider_type)

    def on_provider_failure(self, provider_type: ProviderType, error: str):
        """
        Вызывается при неудаче провайдера

        Args:
            provider_type: Тип провайдера
            error: Сообщение об ошибке
        """
        self.health_checker.record_failure(provider_type, error)

    def get_status(self) -> Dict[str, Any]:
        """
        Получить статус переключения при сбоях

        Returns:
            Словарь статуса
        """
        current = self.get_current_provider()
        return {
            "current_provider": current.value if current else None,
            "priority_order": [p.value for p in self.priority_order],
            "available_providers": [
                p.value for p in self.health_checker.get_available_providers(self.priority_order)
            ],
            "health_status": self.health_checker.get_all_health_status(),
        }
