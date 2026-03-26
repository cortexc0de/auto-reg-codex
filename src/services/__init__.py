"""
Модуль почтовых сервисов
"""

from .base import (
    BaseEmailService,
    EmailServiceError,
    EmailServiceStatus,
    EmailServiceFactory,
    create_email_service,
    EmailServiceType
)
from .tempmail import TempmailService
from .outlook import OutlookService
from .custom_domain import CustomDomainEmailService
from .abuzovo import AbuzovEmailService
from .axiomlauncher import AxiomLauncherEmailService

# Регистрация сервисов
EmailServiceFactory.register(EmailServiceType.TEMPMAIL, TempmailService)
EmailServiceFactory.register(EmailServiceType.OUTLOOK, OutlookService)
EmailServiceFactory.register(EmailServiceType.CUSTOM_DOMAIN, CustomDomainEmailService)
EmailServiceFactory.register(EmailServiceType.ABUZOVO, AbuzovEmailService)
EmailServiceFactory.register(EmailServiceType.AXIOMLAUNCHER, AxiomLauncherEmailService)

# Экспорт дополнительного содержимого модуля Outlook
from .outlook.base import (
    ProviderType,
    EmailMessage,
    TokenInfo,
    ProviderHealth,
    ProviderStatus,
)
from .outlook.account import OutlookAccount
from .outlook.providers import (
    OutlookProvider,
    IMAPOldProvider,
    IMAPNewProvider,
    GraphAPIProvider,
)

__all__ = [
    # Базовые классы
    'BaseEmailService',
    'EmailServiceError',
    'EmailServiceStatus',
    'EmailServiceFactory',
    'create_email_service',
    'EmailServiceType',
    # Классы сервисов
    'TempmailService',
    'OutlookService',
    'CustomDomainEmailService',
    'AbuzovEmailService',
    'AxiomLauncherEmailService',
    # Модуль Outlook
    'ProviderType',
    'EmailMessage',
    'TokenInfo',
    'ProviderHealth',
    'ProviderStatus',
    'OutlookAccount',
    'OutlookProvider',
    'IMAPOldProvider',
    'IMAPNewProvider',
    'GraphAPIProvider',
]