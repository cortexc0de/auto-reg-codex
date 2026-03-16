"""
Основной класс почтового сервиса Outlook
Поддержка нескольких способов подключения IMAP/API, автоматическое переключение при сбоях
"""

import logging
import threading
import time
from typing import Optional, Dict, Any, List

from ..base import BaseEmailService, EmailServiceError, EmailServiceStatus, EmailServiceType
from ...config.constants import EmailServiceType as ServiceType
from ...config.settings import get_settings
from .account import OutlookAccount
from .base import ProviderType, EmailMessage
from .email_parser import EmailParser, get_email_parser
from .health_checker import HealthChecker, FailoverManager
from .providers.base import OutlookProvider, ProviderConfig
from .providers.imap_old import IMAPOldProvider
from .providers.imap_new import IMAPNewProvider
from .providers.graph_api import GraphAPIProvider


logger = logging.getLogger(__name__)


# Приоритет провайдеров по умолчанию
# IMAP_OLD наиболее совместимый (нужен только токен login.live.com), IMAP_NEW на втором месте, Graph API последний
# Причина: у некоторых client_id нет прав Graph API, но есть права IMAP
DEFAULT_PROVIDER_PRIORITY = [
    ProviderType.IMAP_OLD,
    ProviderType.IMAP_NEW,
    ProviderType.GRAPH_API,
]


def get_email_code_settings() -> dict:
    """Получить настройки ожидания кода подтверждения"""
    settings = get_settings()
    return {
        "timeout": settings.email_code_timeout,
        "poll_interval": settings.email_code_poll_interval,
    }


class OutlookService(BaseEmailService):
    """
    Почтовый сервис Outlook
    Поддержка нескольких способов подключения IMAP/API, автоматическое переключение при сбоях
    """

    def __init__(self, config: Dict[str, Any] = None, name: str = None):
        """
        Инициализация сервиса Outlook

        Args:
            config: Словарь конфигурации, поддерживает следующие ключи:
                - accounts: Список учётных записей Outlook
                - provider_priority: Список приоритетов провайдеров
                - health_failure_threshold: Порог последовательных неудач
                - health_disable_duration: Длительность отключения (в секундах)
                - timeout: Таймаут запроса
                - proxy_url: URL прокси
            name: Название сервиса
        """
        super().__init__(ServiceType.OUTLOOK, name)

        # Конфигурация по умолчанию
        default_config = {
            "accounts": [],
            "provider_priority": [p.value for p in DEFAULT_PROVIDER_PRIORITY],
            "health_failure_threshold": 5,
            "health_disable_duration": 60,
            "timeout": 30,
            "proxy_url": None,
        }

        self.config = {**default_config, **(config or {})}

        # Разбор приоритета провайдеров
        self.provider_priority = [
            ProviderType(p) for p in self.config.get("provider_priority", [])
        ]
        if not self.provider_priority:
            self.provider_priority = DEFAULT_PROVIDER_PRIORITY

        # Конфигурация провайдера
        self.provider_config = ProviderConfig(
            timeout=self.config.get("timeout", 30),
            proxy_url=self.config.get("proxy_url"),
            health_failure_threshold=self.config.get("health_failure_threshold", 3),
            health_disable_duration=self.config.get("health_disable_duration", 300),
        )

        # Получить client_id по умолчанию (для учётных записей без client_id)
        try:
            _default_client_id = get_settings().outlook_default_client_id
        except Exception:
            _default_client_id = "24d9a0ed-8787-4584-883c-2fd79308940a"

        # Разбор учётных записей
        self.accounts: List[OutlookAccount] = []
        self._current_account_index = 0
        self._account_lock = threading.Lock()

        # Поддержка двух форматов конфигурации
        if "email" in self.config and "password" in self.config:
            account = OutlookAccount.from_config(self.config)
            if not account.client_id and _default_client_id:
                account.client_id = _default_client_id
            if account.validate():
                self.accounts.append(account)
        else:
            for account_config in self.config.get("accounts", []):
                account = OutlookAccount.from_config(account_config)
                if not account.client_id and _default_client_id:
                    account.client_id = _default_client_id
                if account.validate():
                    self.accounts.append(account)

        if not self.accounts:
            logger.warning("Не настроены действительные учётные записи Outlook")

        # Проверка здоровья и менеджер переключения при сбоях
        self.health_checker = HealthChecker(
            failure_threshold=self.provider_config.health_failure_threshold,
            disable_duration=self.provider_config.health_disable_duration,
        )
        self.failover_manager = FailoverManager(
            health_checker=self.health_checker,
            priority_order=self.provider_priority,
        )

        # Парсер писем
        self.email_parser = get_email_parser()

        # Кэш экземпляров провайдеров: (email, provider_type) -> OutlookProvider
        self._providers: Dict[tuple, OutlookProvider] = {}
        self._provider_lock = threading.Lock()

        # Ограничение IMAP-подключений (предотвращение ограничения скорости)
        self._imap_semaphore = threading.Semaphore(5)

        # Механизм дедупликации кодов подтверждения
        self._used_codes: Dict[str, set] = {}

    def _get_provider(
        self,
        account: OutlookAccount,
        provider_type: ProviderType,
    ) -> OutlookProvider:
        """
        Получить или создать экземпляр провайдера

        Args:
            account: Учётная запись Outlook
            provider_type: Тип провайдера

        Returns:
            Экземпляр провайдера
        """
        cache_key = (account.email.lower(), provider_type)

        with self._provider_lock:
            if cache_key not in self._providers:
                provider = self._create_provider(account, provider_type)
                self._providers[cache_key] = provider

            return self._providers[cache_key]

    def _create_provider(
        self,
        account: OutlookAccount,
        provider_type: ProviderType,
    ) -> OutlookProvider:
        """
        Создать экземпляр провайдера

        Args:
            account: Учётная запись Outlook
            provider_type: Тип провайдера

        Returns:
            Экземпляр провайдера
        """
        if provider_type == ProviderType.IMAP_OLD:
            return IMAPOldProvider(account, self.provider_config)
        elif provider_type == ProviderType.IMAP_NEW:
            return IMAPNewProvider(account, self.provider_config)
        elif provider_type == ProviderType.GRAPH_API:
            return GraphAPIProvider(account, self.provider_config)
        else:
            raise ValueError(f"Неизвестный тип провайдера: {provider_type}")

    def _get_provider_priority_for_account(self, account: OutlookAccount) -> List[ProviderType]:
        """Вернуть подходящий список приоритетов провайдеров в зависимости от наличия OAuth у учётной записи"""
        if account.has_oauth():
            return self.provider_priority
        else:
            # Без OAuth используем старый IMAP (аутентификация по паролю), пропуская провайдеры, требующие OAuth
            return [ProviderType.IMAP_OLD]

    def _try_providers_for_emails(
        self,
        account: OutlookAccount,
        count: int = 20,
        only_unseen: bool = True,
    ) -> List[EmailMessage]:
        """
        Попытаться получить письма через несколько провайдеров

        Args:
            account: Учётная запись Outlook
            count: Количество для получения
            only_unseen: Только непрочитанные

        Returns:
            Список писем
        """
        errors = []

        # Выбрать подходящий приоритет провайдеров по типу учётной записи
        priority = self._get_provider_priority_for_account(account)

        # Попытка по каждому провайдеру в порядке приоритета
        for provider_type in priority:
            # Проверить доступность провайдера
            if not self.health_checker.is_available(provider_type):
                logger.debug(
                    f"[{account.email}] {provider_type.value} недоступен, пропуск"
                )
                continue

            try:
                provider = self._get_provider(account, provider_type)

                with self._imap_semaphore:
                    with provider:
                        emails = provider.get_recent_emails(count, only_unseen)

                        if emails:
                            # Успешное получение писем
                            self.health_checker.record_success(provider_type)
                            logger.debug(
                                f"[{account.email}] {provider_type.value} получено {len(emails)} писем"
                            )
                            return emails

            except Exception as e:
                error_msg = str(e)
                errors.append(f"{provider_type.value}: {error_msg}")
                self.health_checker.record_failure(provider_type, error_msg)
                logger.warning(
                    f"[{account.email}] {provider_type.value} не удалось получить письма: {e}"
                )

        logger.error(
            f"[{account.email}] Все провайдеры не удались: {'; '.join(errors)}"
        )
        return []

    def create_email(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Выбрать доступную учётную запись Outlook

        Args:
            config: Параметры конфигурации (не используются)

        Returns:
            Словарь с информацией о почте
        """
        if not self.accounts:
            self.update_status(False, EmailServiceError("Нет доступных учётных записей Outlook"))
            raise EmailServiceError("Нет доступных учётных записей Outlook")

        # Циклический выбор учётной записи
        with self._account_lock:
            account = self.accounts[self._current_account_index]
            self._current_account_index = (self._current_account_index + 1) % len(self.accounts)

        email_info = {
            "email": account.email,
            "service_id": account.email,
            "account": {
                "email": account.email,
                "has_oauth": account.has_oauth()
            }
        }

        logger.info(f"Выбрана учётная запись Outlook: {account.email}")
        self.update_status(True)
        return email_info

    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = None,
        pattern: str = None,
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        """
        Получить код подтверждения из почтового ящика Outlook

        Args:
            email: Почтовый адрес
            email_id: Не используется
            timeout: Таймаут (в секундах)
            pattern: Регулярное выражение для кода подтверждения (не используется)
            otp_sent_at: Временная метка отправки OTP

        Returns:
            Строка с кодом подтверждения
        """
        # Найти соответствующую учётную запись
        account = None
        for acc in self.accounts:
            if acc.email.lower() == email.lower():
                account = acc
                break

        if not account:
            self.update_status(False, EmailServiceError(f"Не найдена учётная запись для почтового ящика: {email}"))
            return None

        # Получить настройки ожидания кода подтверждения
        code_settings = get_email_code_settings()
        actual_timeout = timeout or code_settings["timeout"]
        poll_interval = code_settings["poll_interval"]

        logger.info(
            f"[{email}] Начало получения кода подтверждения, таймаут {actual_timeout}с, "
            f"приоритет провайдеров: {[p.value for p in self.provider_priority]}"
        )

        # Инициализация набора для дедупликации кодов подтверждения
        if email not in self._used_codes:
            self._used_codes[email] = set()
        used_codes = self._used_codes[email]

        # Вычисление минимальной временной метки (с запасом 60 секунд на расхождение часов)
        min_timestamp = (otp_sent_at - 60) if otp_sent_at else 0

        start_time = time.time()
        poll_count = 0

        while time.time() - start_time < actual_timeout:
            poll_count += 1

            # Прогрессивная проверка писем: первые 3 раза только непрочитанные
            only_unseen = poll_count <= 3

            try:
                # Попытка получить письма через несколько провайдеров
                emails = self._try_providers_for_emails(
                    account,
                    count=15,
                    only_unseen=only_unseen,
                )

                if emails:
                    logger.debug(
                        f"[{email}] {poll_count}-й опрос получил {len(emails)} писем"
                    )

                    # Поиск кода подтверждения в письмах
                    code = self.email_parser.find_verification_code_in_emails(
                        emails,
                        target_email=email,
                        min_timestamp=min_timestamp,
                        used_codes=used_codes,
                    )

                    if code:
                        used_codes.add(code)
                        elapsed = int(time.time() - start_time)
                        logger.info(
                            f"[{email}] Найден код подтверждения: {code}, "
                            f"общее время {elapsed}с, опросов {poll_count}"
                        )
                        self.update_status(True)
                        return code

            except Exception as e:
                logger.warning(f"[{email}] Ошибка проверки: {e}")

            # Ожидание следующего опроса
            time.sleep(poll_interval)

        elapsed = int(time.time() - start_time)
        logger.warning(f"[{email}] Таймаут кода подтверждения ({actual_timeout}с), всего опросов {poll_count}")
        return None

    def list_emails(self, **kwargs) -> List[Dict[str, Any]]:
        """Показать все доступные учётные записи Outlook"""
        return [
            {
                "email": account.email,
                "id": account.email,
                "has_oauth": account.has_oauth(),
                "type": "outlook"
            }
            for account in self.accounts
        ]

    def delete_email(self, email_id: str) -> bool:
        """Удалить почтовый ящик (Outlook не поддерживает удаление учётных записей)"""
        logger.warning(f"Сервис Outlook не поддерживает удаление учётных записей: {email_id}")
        return False

    def check_health(self) -> bool:
        """Проверить доступность сервиса Outlook"""
        if not self.accounts:
            self.update_status(False, EmailServiceError("Нет настроенных учётных записей"))
            return False

        # Тестирование подключения первой учётной записи
        test_account = self.accounts[0]

        # Попытка подключения через любой провайдер
        for provider_type in self.provider_priority:
            try:
                provider = self._get_provider(test_account, provider_type)
                if provider.test_connection():
                    self.update_status(True)
                    return True
            except Exception as e:
                logger.warning(
                    f"Проверка здоровья Outlook не пройдена ({test_account.email}, {provider_type.value}): {e}"
                )

        self.update_status(False, EmailServiceError("Проверка здоровья не пройдена"))
        return False

    def get_provider_status(self) -> Dict[str, Any]:
        """Получить статус провайдеров"""
        return self.failover_manager.get_status()

    def get_account_stats(self) -> Dict[str, Any]:
        """Получить статистику учётных записей"""
        total = len(self.accounts)
        oauth_count = sum(1 for acc in self.accounts if acc.has_oauth())

        return {
            "total_accounts": total,
            "oauth_accounts": oauth_count,
            "password_accounts": total - oauth_count,
            "accounts": [acc.to_dict() for acc in self.accounts],
            "provider_status": self.get_provider_status(),
        }

    def add_account(self, account_config: Dict[str, Any]) -> bool:
        """Добавить новую учётную запись Outlook"""
        try:
            account = OutlookAccount.from_config(account_config)
            if not account.validate():
                return False

            self.accounts.append(account)
            logger.info(f"Добавлена учётная запись Outlook: {account.email}")
            return True
        except Exception as e:
            logger.error(f"Не удалось добавить учётную запись Outlook: {e}")
            return False

    def remove_account(self, email: str) -> bool:
        """Удалить учётную запись Outlook"""
        for i, acc in enumerate(self.accounts):
            if acc.email.lower() == email.lower():
                self.accounts.pop(i)
                logger.info(f"Удалена учётная запись Outlook: {email}")
                return True
        return False

    def reset_provider_health(self):
        """Сбросить состояние здоровья всех провайдеров"""
        self.health_checker.reset_all()
        logger.info("Состояние здоровья всех провайдеров сброшено")

    def force_provider(self, provider_type: ProviderType):
        """Принудительно использовать указанный провайдер"""
        self.health_checker.force_enable(provider_type)
        # Отключить остальные провайдеры
        for pt in ProviderType:
            if pt != provider_type:
                self.health_checker.force_disable(pt, 60)
        logger.info(f"Принудительно используется провайдер: {provider_type.value}")
