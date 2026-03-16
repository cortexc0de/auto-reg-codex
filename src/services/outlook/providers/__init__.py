"""
Модуль провайдеров Outlook
"""

from .base import OutlookProvider, ProviderConfig
from .imap_old import IMAPOldProvider
from .imap_new import IMAPNewProvider
from .graph_api import GraphAPIProvider

__all__ = [
    'OutlookProvider',
    'ProviderConfig',
    'IMAPOldProvider',
    'IMAPNewProvider',
    'GraphAPIProvider',
]


# Реестр провайдеров
PROVIDER_REGISTRY = {
    'imap_old': IMAPOldProvider,
    'imap_new': IMAPNewProvider,
    'graph_api': GraphAPIProvider,
}


def get_provider_class(provider_type: str):
    """Получить класс провайдера"""
    return PROVIDER_REGISTRY.get(provider_type)
