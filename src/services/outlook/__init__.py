"""
Модуль почтового сервиса Outlook
Поддержка нескольких способов подключения IMAP/API, автоматическое переключение при сбоях
"""

from .service import OutlookService

__all__ = ['OutlookService']
