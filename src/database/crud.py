"""
CRUD операции с базой данных
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func

from .models import Account, EmailService, RegistrationTask, Setting, Proxy


# ============================================================================
# CRUD аккаунтов
# ============================================================================

def create_account(
    db: Session,
    email: str,
    email_service: str,
    password: Optional[str] = None,
    client_id: Optional[str] = None,
    session_token: Optional[str] = None,
    email_service_id: Optional[str] = None,
    account_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    id_token: Optional[str] = None,
    proxy_used: Optional[str] = None,
    expires_at: Optional['datetime'] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
    source: Optional[str] = None
) -> Account:
    """Создание нового аккаунта"""
    db_account = Account(
        email=email,
        password=password,
        client_id=client_id,
        session_token=session_token,
        email_service=email_service,
        email_service_id=email_service_id,
        account_id=account_id,
        workspace_id=workspace_id,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=id_token,
        proxy_used=proxy_used,
        expires_at=expires_at,
        extra_data=extra_data or {},
        status=status or 'active',
        source=source or 'register',
        registered_at=datetime.utcnow()
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def get_account_by_id(db: Session, account_id: int) -> Optional[Account]:
    """Получение аккаунта по ID"""
    return db.query(Account).filter(Account.id == account_id).first()


def get_account_by_email(db: Session, email: str) -> Optional[Account]:
    """Получение аккаунта по email"""
    return db.query(Account).filter(Account.email == email).first()


def get_accounts(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    email_service: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
) -> List[Account]:
    """Получение списка аккаунтов (поддержка пагинации, фильтрации)"""
    query = db.query(Account)

    if email_service:
        query = query.filter(Account.email_service == email_service)

    if status:
        query = query.filter(Account.status == status)

    if search:
        search_filter = or_(
            Account.email.ilike(f"%{search}%"),
            Account.account_id.ilike(f"%{search}%"),
            Account.workspace_id.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)

    query = query.order_by(desc(Account.created_at)).offset(skip).limit(limit)
    return query.all()


def update_account(
    db: Session,
    account_id: int,
    **kwargs
) -> Optional[Account]:
    """Обновление информации об аккаунте"""
    db_account = get_account_by_id(db, account_id)
    if not db_account:
        return None

    for key, value in kwargs.items():
        if hasattr(db_account, key) and value is not None:
            setattr(db_account, key, value)

    db.commit()
    db.refresh(db_account)
    return db_account


def delete_account(db: Session, account_id: int) -> bool:
    """Удаление аккаунта"""
    db_account = get_account_by_id(db, account_id)
    if not db_account:
        return False

    db.delete(db_account)
    db.commit()
    return True


def delete_accounts_batch(db: Session, account_ids: List[int]) -> int:
    """Пакетное удаление аккаунтов"""
    result = db.query(Account).filter(Account.id.in_(account_ids)).delete(synchronize_session=False)
    db.commit()
    return result


def get_accounts_count(
    db: Session,
    email_service: Optional[str] = None,
    status: Optional[str] = None
) -> int:
    """Получение количества аккаунтов"""
    query = db.query(func.count(Account.id))

    if email_service:
        query = query.filter(Account.email_service == email_service)

    if status:
        query = query.filter(Account.status == status)

    return query.scalar()


# ============================================================================
# CRUD почтовых сервисов
# ============================================================================

def create_email_service(
    db: Session,
    service_type: str,
    name: str,
    config: Dict[str, Any],
    enabled: bool = True,
    priority: int = 0
) -> EmailService:
    """Создание конфигурации почтового сервиса"""
    db_service = EmailService(
        service_type=service_type,
        name=name,
        config=config,
        enabled=enabled,
        priority=priority
    )
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service


def get_email_service_by_id(db: Session, service_id: int) -> Optional[EmailService]:
    """Получение почтового сервиса по ID"""
    return db.query(EmailService).filter(EmailService.id == service_id).first()


def get_email_services(
    db: Session,
    service_type: Optional[str] = None,
    enabled: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100
) -> List[EmailService]:
    """Получение списка почтовых сервисов"""
    query = db.query(EmailService)

    if service_type:
        query = query.filter(EmailService.service_type == service_type)

    if enabled is not None:
        query = query.filter(EmailService.enabled == enabled)

    query = query.order_by(
        asc(EmailService.priority),
        desc(EmailService.last_used)
    ).offset(skip).limit(limit)

    return query.all()


def update_email_service(
    db: Session,
    service_id: int,
    **kwargs
) -> Optional[EmailService]:
    """Обновление конфигурации почтового сервиса"""
    db_service = get_email_service_by_id(db, service_id)
    if not db_service:
        return None

    for key, value in kwargs.items():
        if hasattr(db_service, key) and value is not None:
            setattr(db_service, key, value)

    db.commit()
    db.refresh(db_service)
    return db_service


def delete_email_service(db: Session, service_id: int) -> bool:
    """Удаление конфигурации почтового сервиса"""
    db_service = get_email_service_by_id(db, service_id)
    if not db_service:
        return False

    db.delete(db_service)
    db.commit()
    return True


# ============================================================================
# CRUD задач регистрации
# ============================================================================

def create_registration_task(
    db: Session,
    task_uuid: str,
    email_service_id: Optional[int] = None,
    proxy: Optional[str] = None
) -> RegistrationTask:
    """Создание задачи регистрации"""
    db_task = RegistrationTask(
        task_uuid=task_uuid,
        email_service_id=email_service_id,
        proxy=proxy,
        status='pending'
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def get_registration_task_by_uuid(db: Session, task_uuid: str) -> Optional[RegistrationTask]:
    """Получение задачи регистрации по UUID"""
    return db.query(RegistrationTask).filter(RegistrationTask.task_uuid == task_uuid).first()


def get_registration_tasks(
    db: Session,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> List[RegistrationTask]:
    """Получение списка задач регистрации"""
    query = db.query(RegistrationTask)

    if status:
        query = query.filter(RegistrationTask.status == status)

    query = query.order_by(desc(RegistrationTask.created_at)).offset(skip).limit(limit)
    return query.all()


def update_registration_task(
    db: Session,
    task_uuid: str,
    **kwargs
) -> Optional[RegistrationTask]:
    """Обновление статуса задачи регистрации"""
    db_task = get_registration_task_by_uuid(db, task_uuid)
    if not db_task:
        return None

    for key, value in kwargs.items():
        if hasattr(db_task, key):
            setattr(db_task, key, value)

    db.commit()
    db.refresh(db_task)
    return db_task


def append_task_log(db: Session, task_uuid: str, log_message: str) -> bool:
    """Добавление лога задачи"""
    db_task = get_registration_task_by_uuid(db, task_uuid)
    if not db_task:
        return False

    if db_task.logs:
        db_task.logs += f"\n{log_message}"
    else:
        db_task.logs = log_message

    db.commit()
    return True


def delete_registration_task(db: Session, task_uuid: str) -> bool:
    """Удаление задачи регистрации"""
    db_task = get_registration_task_by_uuid(db, task_uuid)
    if not db_task:
        return False

    db.delete(db_task)
    db.commit()
    return True


# Добавление псевдонимов для маршрутов API
get_account = get_account_by_id
get_registration_task = get_registration_task_by_uuid


# ============================================================================
# CRUD настроек
# ============================================================================

def get_setting(db: Session, key: str) -> Optional[Setting]:
    """Получение настройки"""
    return db.query(Setting).filter(Setting.key == key).first()


def get_settings_by_category(db: Session, category: str) -> List[Setting]:
    """Получение настроек по категории"""
    return db.query(Setting).filter(Setting.category == category).all()


def set_setting(
    db: Session,
    key: str,
    value: str,
    description: Optional[str] = None,
    category: str = 'general'
) -> Setting:
    """Установка или обновление элемента конфигурации"""
    db_setting = get_setting(db, key)
    if db_setting:
        db_setting.value = value
        db_setting.description = description or db_setting.description
        db_setting.category = category
        db_setting.updated_at = datetime.utcnow()
    else:
        db_setting = Setting(
            key=key,
            value=value,
            description=description,
            category=category
        )
        db.add(db_setting)

    db.commit()
    db.refresh(db_setting)
    return db_setting


def delete_setting(db: Session, key: str) -> bool:
    """Удаление настройки"""
    db_setting = get_setting(db, key)
    if not db_setting:
        return False

    db.delete(db_setting)
    db.commit()
    return True


# ============================================================================
# CRUD прокси
# ============================================================================

def create_proxy(
    db: Session,
    name: str,
    type: str,
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    enabled: bool = True,
    priority: int = 0
) -> Proxy:
    """Создание конфигурации прокси"""
    db_proxy = Proxy(
        name=name,
        type=type,
        host=host,
        port=port,
        username=username,
        password=password,
        enabled=enabled,
        priority=priority
    )
    db.add(db_proxy)
    db.commit()
    db.refresh(db_proxy)
    return db_proxy


def get_proxy_by_id(db: Session, proxy_id: int) -> Optional[Proxy]:
    """Получение прокси по ID"""
    return db.query(Proxy).filter(Proxy.id == proxy_id).first()


def get_proxies(
    db: Session,
    enabled: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Proxy]:
    """Получение списка прокси"""
    query = db.query(Proxy)

    if enabled is not None:
        query = query.filter(Proxy.enabled == enabled)

    query = query.order_by(desc(Proxy.created_at)).offset(skip).limit(limit)
    return query.all()


def get_enabled_proxies(db: Session) -> List[Proxy]:
    """Получение всех включённых прокси"""
    return db.query(Proxy).filter(Proxy.enabled == True).all()


def update_proxy(
    db: Session,
    proxy_id: int,
    **kwargs
) -> Optional[Proxy]:
    """Обновление конфигурации прокси"""
    db_proxy = get_proxy_by_id(db, proxy_id)
    if not db_proxy:
        return None

    for key, value in kwargs.items():
        if hasattr(db_proxy, key):
            setattr(db_proxy, key, value)

    db.commit()
    db.refresh(db_proxy)
    return db_proxy


def delete_proxy(db: Session, proxy_id: int) -> bool:
    """Удаление конфигурации прокси"""
    db_proxy = get_proxy_by_id(db, proxy_id)
    if not db_proxy:
        return False

    db.delete(db_proxy)
    db.commit()
    return True


def update_proxy_last_used(db: Session, proxy_id: int) -> bool:
    """Обновление времени последнего использования прокси"""
    db_proxy = get_proxy_by_id(db, proxy_id)
    if not db_proxy:
        return False

    db_proxy.last_used = datetime.utcnow()
    db.commit()
    return True


def get_random_proxy(db: Session) -> Optional[Proxy]:
    """Случайное получение одного включённого прокси"""
    import random
    proxies = get_enabled_proxies(db)
    if not proxies:
        return None
    return random.choice(proxies)


def get_proxies_count(db: Session, enabled: Optional[bool] = None) -> int:
    """Получение количества прокси"""
    query = db.query(func.count(Proxy.id))
    if enabled is not None:
        query = query.filter(Proxy.enabled == enabled)
    return query.scalar()