"""
Определения моделей SQLAlchemy ORM
"""

from datetime import datetime
from typing import Optional, Dict, Any
import json
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship

Base = declarative_base()


class JSONEncodedDict(TypeDecorator):
    """Тип словаря с JSON кодированием"""
    impl = Text

    def process_bind_param(self, value: Optional[Dict[str, Any]], dialect):
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: Optional[str], dialect):
        if value is None:
            return None
        return json.loads(value)


class Account(Base):
    """Таблица зарегистрированных аккаунтов"""
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password = Column(String(255))  # Пароль регистрации (хранится в открытом виде)
    access_token = Column(Text)
    refresh_token = Column(Text)
    id_token = Column(Text)
    session_token = Column(Text)  # Токен сессии (приоритетный метод обновления)
    client_id = Column(String(255))  # OAuth Client ID
    account_id = Column(String(255))
    workspace_id = Column(String(255))
    email_service = Column(String(50), nullable=False)  # 'tempmail', 'outlook', 'custom_domain'
    email_service_id = Column(String(255))  # ID в почтовом сервисе
    proxy_used = Column(String(255))
    registered_at = Column(DateTime, default=datetime.utcnow)
    last_refresh = Column(DateTime)  # Время последнего обновления
    expires_at = Column(DateTime)  # Время истечения токена
    status = Column(String(20), default='active')  # 'active', 'expired', 'banned', 'failed'
    extra_data = Column(JSONEncodedDict)  # Хранение дополнительной информации
    cpa_uploaded = Column(Boolean, default=False)  # Загружено ли в CPA
    cpa_uploaded_at = Column(DateTime)  # Время загрузки
    source = Column(String(20), default='register')  # 'register' или 'login', различение источника аккаунта
    subscription_type = Column(String(20))  # None / 'plus' / 'team'
    subscription_at = Column(DateTime)  # Время оформления подписки
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        return {
            'id': self.id,
            'email': self.email,
            'password': self.password,
            'client_id': self.client_id,
            'email_service': self.email_service,
            'account_id': self.account_id,
            'workspace_id': self.workspace_id,
            'registered_at': self.registered_at.isoformat() if self.registered_at else None,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'status': self.status,
            'proxy_used': self.proxy_used,
            'cpa_uploaded': self.cpa_uploaded,
            'cpa_uploaded_at': self.cpa_uploaded_at.isoformat() if self.cpa_uploaded_at else None,
            'source': self.source,
            'subscription_type': self.subscription_type,
            'subscription_at': self.subscription_at.isoformat() if self.subscription_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class EmailService(Base):
    """Таблица конфигурации почтовых сервисов"""
    __tablename__ = 'email_services'

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_type = Column(String(50), nullable=False)  # 'outlook', 'custom_domain'
    name = Column(String(100), nullable=False)
    config = Column(JSONEncodedDict, nullable=False)  # Конфигурация сервиса (зашифрованное хранение)
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Приоритет использования
    last_used = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RegistrationTask(Base):
    """Таблица задач регистрации"""
    __tablename__ = 'registration_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_uuid = Column(String(36), unique=True, nullable=False, index=True)  # Уникальный идентификатор задачи
    status = Column(String(20), default='pending')  # 'pending', 'running', 'completed', 'failed', 'cancelled'
    email_service_id = Column(Integer, ForeignKey('email_services.id'), index=True)  # Используемый почтовый сервис
    proxy = Column(String(255))  # Используемый прокси
    logs = Column(Text)  # Логи процесса регистрации
    result = Column(JSONEncodedDict)  # Результат регистрации
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Связи
    email_service = relationship('EmailService')


class Setting(Base):
    """Таблица системных настроек"""
    __tablename__ = 'settings'

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    description = Column(Text)
    category = Column(String(50), default='general')  # 'general', 'email', 'proxy', 'openai'
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Proxy(Base):
    """Таблица списка прокси"""
    __tablename__ = 'proxies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # Название прокси
    type = Column(String(20), nullable=False, default='http')  # http, socks5
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100))
    password = Column(String(255))
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Приоритет (зарезервированное поле)
    last_used = Column(DateTime)  # Время последнего использования
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_password: bool = False) -> Dict[str, Any]:
        """Преобразование в словарь"""
        result = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'enabled': self.enabled,
            'priority': self.priority,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_password:
            result['password'] = self.password
        else:
            result['has_password'] = bool(self.password)
        return result

    @property
    def proxy_url(self) -> str:
        """Получение полного URL прокси"""
        if self.type == "http":
            scheme = "http"
        elif self.type == "socks5":
            scheme = "socks5"
        else:
            scheme = self.type

        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"

        return f"{scheme}://{auth}{self.host}:{self.port}"