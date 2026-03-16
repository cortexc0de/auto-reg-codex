"""
Базовые определения сервиса Outlook
Содержит перечисления и классы данных
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List


class ProviderType(str, Enum):
    """Тип провайдера Outlook"""
    IMAP_OLD = "imap_old"      # Старая версия IMAP (outlook.office365.com)
    IMAP_NEW = "imap_new"      # Новая версия IMAP (outlook.live.com)
    GRAPH_API = "graph_api"    # Microsoft Graph API


class TokenEndpoint(str, Enum):
    """Конечная точка Token"""
    LIVE = "https://login.live.com/oauth20_token.srf"
    CONSUMERS = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    COMMON = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


class IMAPServer(str, Enum):
    """IMAP-сервер"""
    OLD = "outlook.office365.com"
    NEW = "outlook.live.com"


class ProviderStatus(str, Enum):
    """Статус провайдера"""
    HEALTHY = "healthy"        # Здоров
    DEGRADED = "degraded"      # Деградирован
    DISABLED = "disabled"      # Отключён


@dataclass
class EmailMessage:
    """Класс данных почтового сообщения"""
    id: str                                    # ID сообщения
    subject: str                               # Тема
    sender: str                                # Отправитель
    recipients: List[str] = field(default_factory=list)  # Список получателей
    body: str = ""                             # Содержимое тела
    body_preview: str = ""                     # Предпросмотр тела
    received_at: Optional[datetime] = None     # Время получения
    received_timestamp: int = 0                # Временная метка получения
    is_read: bool = False                      # Прочитано ли
    has_attachments: bool = False              # Есть ли вложения
    raw_data: Optional[bytes] = None           # Необработанные данные (для отладки)

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь"""
        return {
            "id": self.id,
            "subject": self.subject,
            "sender": self.sender,
            "recipients": self.recipients,
            "body": self.body,
            "body_preview": self.body_preview,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "received_timestamp": self.received_timestamp,
            "is_read": self.is_read,
            "has_attachments": self.has_attachments,
        }


@dataclass
class TokenInfo:
    """Класс данных информации о Token"""
    access_token: str
    expires_at: float              # Временная метка истечения
    token_type: str = "Bearer"
    scope: str = ""
    refresh_token: Optional[str] = None

    def is_expired(self, buffer_seconds: int = 120) -> bool:
        """Проверить, истёк ли Token"""
        import time
        return time.time() >= (self.expires_at - buffer_seconds)

    @classmethod
    def from_response(cls, data: Dict[str, Any], scope: str = "") -> "TokenInfo":
        """Создать из ответа API"""
        import time
        return cls(
            access_token=data.get("access_token", ""),
            expires_at=time.time() + data.get("expires_in", 3600),
            token_type=data.get("token_type", "Bearer"),
            scope=scope or data.get("scope", ""),
            refresh_token=data.get("refresh_token"),
        )


@dataclass
class ProviderHealth:
    """Состояние здоровья провайдера"""
    provider_type: ProviderType
    status: ProviderStatus = ProviderStatus.HEALTHY
    failure_count: int = 0                       # Количество последовательных неудач
    last_success: Optional[datetime] = None      # Время последнего успеха
    last_failure: Optional[datetime] = None      # Время последней неудачи
    last_error: str = ""                         # Последнее сообщение об ошибке
    disabled_until: Optional[datetime] = None    # Время окончания отключения

    def record_success(self):
        """Записать успех"""
        self.status = ProviderStatus.HEALTHY
        self.failure_count = 0
        self.last_success = datetime.now()
        self.disabled_until = None

    def record_failure(self, error: str):
        """Записать неудачу"""
        self.failure_count += 1
        self.last_failure = datetime.now()
        self.last_error = error

    def should_disable(self, threshold: int = 3) -> bool:
        """Определить, следует ли отключить"""
        return self.failure_count >= threshold

    def is_disabled(self) -> bool:
        """Проверить, отключён ли"""
        if self.disabled_until and datetime.now() < self.disabled_until:
            return True
        return False

    def disable(self, duration_seconds: int = 300):
        """Отключить провайдер"""
        from datetime import timedelta
        self.status = ProviderStatus.DISABLED
        self.disabled_until = datetime.now() + timedelta(seconds=duration_seconds)

    def enable(self):
        """Включить провайдер"""
        self.status = ProviderStatus.HEALTHY
        self.disabled_until = None
        self.failure_count = 0

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь"""
        return {
            "provider_type": self.provider_type.value,
            "status": self.status.value,
            "failure_count": self.failure_count,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "last_error": self.last_error,
            "disabled_until": self.disabled_until.isoformat() if self.disabled_until else None,
        }
