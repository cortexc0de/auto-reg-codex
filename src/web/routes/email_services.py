"""
Маршруты API конфигурации почтовых сервисов
"""

import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...database import crud
from ...database.session import get_db
from ...database.models import EmailService as EmailServiceModel
from ...services import EmailServiceFactory, EmailServiceType

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== Pydantic Models ==============

class EmailServiceCreate(BaseModel):
    """Запрос на создание почтового сервиса"""
    service_type: str
    name: str
    config: Dict[str, Any]
    enabled: bool = True
    priority: int = 0


class EmailServiceUpdate(BaseModel):
    """Запрос на обновление почтового сервиса"""
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class EmailServiceResponse(BaseModel):
    """Ответ почтового сервиса"""
    id: int
    service_type: str
    name: str
    enabled: bool
    priority: int
    config: Optional[Dict[str, Any]] = None  # Конфигурация с отфильтрованными чувствительными данными
    last_used: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class EmailServiceListResponse(BaseModel):
    """Ответ со списком почтовых сервисов"""
    total: int
    services: List[EmailServiceResponse]


class ServiceTestResult(BaseModel):
    """Результат тестирования сервиса"""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class OutlookBatchImportRequest(BaseModel):
    """Запрос на пакетный импорт Outlook"""
    data: str  # Многострочные данные, формат каждой строки: email----пароль или email----пароль----client_id----refresh_token
    enabled: bool = True
    priority: int = 0


class OutlookBatchImportResponse(BaseModel):
    """Ответ пакетного импорта Outlook"""
    total: int
    success: int
    failed: int
    accounts: List[Dict[str, Any]]
    errors: List[str]


# ============== Helper Functions ==============

# Список чувствительных полей, которые нужно фильтровать при возврате ответа
SENSITIVE_FIELDS = {'password', 'api_key', 'refresh_token', 'access_token'}

def filter_sensitive_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Фильтрация чувствительной конфигурационной информации"""
    if not config:
        return {}

    filtered = {}
    for key, value in config.items():
        if key in SENSITIVE_FIELDS:
            # Чувствительные поля не возвращаются, но помечается их наличие
            filtered[f"has_{key}"] = bool(value)
        else:
            filtered[key] = value

    # Вычисление наличия OAuth для Outlook
    if config.get('client_id') and config.get('refresh_token'):
        filtered['has_oauth'] = True

    return filtered


def service_to_response(service: EmailServiceModel) -> EmailServiceResponse:
    """Преобразование модели сервиса в ответ"""
    return EmailServiceResponse(
        id=service.id,
        service_type=service.service_type,
        name=service.name,
        enabled=service.enabled,
        priority=service.priority,
        config=filter_sensitive_config(service.config),
        last_used=service.last_used.isoformat() if service.last_used else None,
        created_at=service.created_at.isoformat() if service.created_at else None,
        updated_at=service.updated_at.isoformat() if service.updated_at else None,
    )


# ============== API Endpoints ==============

@router.get("/stats")
async def get_email_services_stats():
    """Получение статистики почтовых сервисов"""
    with get_db() as db:
        from sqlalchemy import func

        # Статистика по типам
        type_stats = db.query(
            EmailServiceModel.service_type,
            func.count(EmailServiceModel.id)
        ).group_by(EmailServiceModel.service_type).all()

        # Количество включённых
        enabled_count = db.query(func.count(EmailServiceModel.id)).filter(
            EmailServiceModel.enabled == True
        ).scalar()

        stats = {
            'outlook_count': 0,
            'custom_count': 0,
            'tempmail_available': True,  # Временная почта всегда доступна
            'enabled_count': enabled_count
        }

        for service_type, count in type_stats:
            if service_type == 'outlook':
                stats['outlook_count'] = count
            elif service_type == 'custom_domain':
                stats['custom_count'] = count

        return stats


@router.get("/types")
async def get_service_types():
    """Получение поддерживаемых типов почтовых сервисов"""
    return {
        "types": [
            {
                "value": "tempmail",
                "label": "Tempmail.lol",
                "description": "Сервис временной почты, настройка не требуется",
                "config_fields": [
                    {"name": "base_url", "label": "Адрес API", "default": "https://api.tempmail.lol/v2", "required": False},
                    {"name": "timeout", "label": "Таймаут", "default": 30, "required": False},
                ]
            },
            {
                "value": "outlook",
                "label": "Outlook",
                "description": "Почта Outlook, требуется настройка данных аккаунта",
                "config_fields": [
                    {"name": "email", "label": "Адрес электронной почты", "required": True},
                    {"name": "password", "label": "Пароль", "required": True},
                    {"name": "client_id", "label": "OAuth Client ID", "required": False},
                    {"name": "refresh_token", "label": "OAuth Refresh Token", "required": False},
                ]
            },
            {
                "value": "custom_domain",
                "label": "Пользовательский домен",
                "description": "Почтовый сервис с пользовательским доменом",
                "config_fields": [
                    {"name": "base_url", "label": "Адрес API", "required": True},
                    {"name": "api_key", "label": "API Key", "required": True},
                    {"name": "default_domain", "label": "Домен по умолчанию", "required": False},
                ]
            }
        ]
    }


@router.get("", response_model=EmailServiceListResponse)
async def list_email_services(
    service_type: Optional[str] = Query(None, description="Фильтр по типу сервиса"),
    enabled_only: bool = Query(False, description="Показывать только включённые сервисы"),
):
    """Получение списка почтовых сервисов"""
    with get_db() as db:
        query = db.query(EmailServiceModel)

        if service_type:
            query = query.filter(EmailServiceModel.service_type == service_type)

        if enabled_only:
            query = query.filter(EmailServiceModel.enabled == True)

        services = query.order_by(EmailServiceModel.priority.asc(), EmailServiceModel.id.asc()).all()

        return EmailServiceListResponse(
            total=len(services),
            services=[service_to_response(s) for s in services]
        )


@router.get("/{service_id}", response_model=EmailServiceResponse)
async def get_email_service(service_id: int):
    """Получение деталей отдельного почтового сервиса"""
    with get_db() as db:
        service = db.query(EmailServiceModel).filter(EmailServiceModel.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Сервис не существует")
        return service_to_response(service)


@router.get("/{service_id}/full")
async def get_email_service_full(service_id: int):
    """Получение полных деталей почтового сервиса (включая чувствительные поля, для редактирования)"""
    with get_db() as db:
        service = db.query(EmailServiceModel).filter(EmailServiceModel.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Сервис не существует")

        return {
            "id": service.id,
            "service_type": service.service_type,
            "name": service.name,
            "enabled": service.enabled,
            "priority": service.priority,
            "config": service.config or {},  # Возврат полной конфигурации
            "last_used": service.last_used.isoformat() if service.last_used else None,
            "created_at": service.created_at.isoformat() if service.created_at else None,
            "updated_at": service.updated_at.isoformat() if service.updated_at else None,
        }


@router.post("", response_model=EmailServiceResponse)
async def create_email_service(request: EmailServiceCreate):
    """Создание конфигурации почтового сервиса"""
    # Валидация типа сервиса
    try:
        EmailServiceType(request.service_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Недопустимый тип сервиса: {request.service_type}")

    with get_db() as db:
        # Проверка уникальности имени
        existing = db.query(EmailServiceModel).filter(EmailServiceModel.name == request.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Имя сервиса уже существует")

        service = EmailServiceModel(
            service_type=request.service_type,
            name=request.name,
            config=request.config,
            enabled=request.enabled,
            priority=request.priority
        )
        db.add(service)
        db.commit()
        db.refresh(service)

        return service_to_response(service)


@router.patch("/{service_id}", response_model=EmailServiceResponse)
async def update_email_service(service_id: int, request: EmailServiceUpdate):
    """Обновление конфигурации почтового сервиса"""
    with get_db() as db:
        service = db.query(EmailServiceModel).filter(EmailServiceModel.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Сервис не существует")

        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.config is not None:
            # Слияние конфигурации вместо замены
            current_config = service.config or {}
            merged_config = {**current_config, **request.config}
            # Удаление пустых значений
            merged_config = {k: v for k, v in merged_config.items() if v}
            update_data["config"] = merged_config
        if request.enabled is not None:
            update_data["enabled"] = request.enabled
        if request.priority is not None:
            update_data["priority"] = request.priority

        for key, value in update_data.items():
            setattr(service, key, value)

        db.commit()
        db.refresh(service)

        return service_to_response(service)


@router.delete("/{service_id}")
async def delete_email_service(service_id: int):
    """Удаление конфигурации почтового сервиса"""
    with get_db() as db:
        service = db.query(EmailServiceModel).filter(EmailServiceModel.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Сервис не существует")

        db.delete(service)
        db.commit()

        return {"success": True, "message": f"Сервис {service.name} удалён"}


@router.post("/{service_id}/test", response_model=ServiceTestResult)
async def test_email_service(service_id: int):
    """Тестирование доступности почтового сервиса"""
    with get_db() as db:
        service = db.query(EmailServiceModel).filter(EmailServiceModel.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Сервис не существует")

        try:
            service_type = EmailServiceType(service.service_type)
            email_service = EmailServiceFactory.create(service_type, service.config, name=service.name)

            health = email_service.check_health()

            if health:
                return ServiceTestResult(
                    success=True,
                    message="Подключение к сервису в норме",
                    details=email_service.get_service_info() if hasattr(email_service, 'get_service_info') else None
                )
            else:
                return ServiceTestResult(
                    success=False,
                    message="Ошибка подключения к сервису"
                )

        except Exception as e:
            logger.error(f"Ошибка тестирования почтового сервиса: {e}")
            return ServiceTestResult(
                success=False,
                message=f"Ошибка тестирования: {str(e)}"
            )


@router.post("/{service_id}/enable")
async def enable_email_service(service_id: int):
    """Включение почтового сервиса"""
    with get_db() as db:
        service = db.query(EmailServiceModel).filter(EmailServiceModel.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Сервис не существует")

        service.enabled = True
        db.commit()

        return {"success": True, "message": f"Сервис {service.name} включён"}


@router.post("/{service_id}/disable")
async def disable_email_service(service_id: int):
    """Отключение почтового сервиса"""
    with get_db() as db:
        service = db.query(EmailServiceModel).filter(EmailServiceModel.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Сервис не существует")

        service.enabled = False
        db.commit()

        return {"success": True, "message": f"Сервис {service.name} отключён"}


@router.post("/reorder")
async def reorder_services(service_ids: List[int]):
    """Изменение порядка приоритетов почтовых сервисов"""
    with get_db() as db:
        for index, service_id in enumerate(service_ids):
            service = db.query(EmailServiceModel).filter(EmailServiceModel.id == service_id).first()
            if service:
                service.priority = index

        db.commit()

        return {"success": True, "message": "Приоритеты обновлены"}


@router.post("/outlook/batch-import", response_model=OutlookBatchImportResponse)
async def batch_import_outlook(request: OutlookBatchImportRequest):
    """
    Пакетный импорт аккаунтов Outlook

    Поддерживаются два формата:
    - Формат 1 (аутентификация по паролю): email----пароль
    - Формат 2 (аутентификация XOAUTH2): email----пароль----client_id----refresh_token

    Каждый аккаунт на отдельной строке, поля разделены четырьмя дефисами (----)
    """
    lines = request.data.strip().split("\n")
    total = len(lines)
    success = 0
    failed = 0
    accounts = []
    errors = []

    with get_db() as db:
        for i, line in enumerate(lines):
            line = line.strip()

            # Пропуск пустых строк и комментариев
            if not line or line.startswith("#"):
                continue

            parts = line.split("----")

            # Проверка формата
            if len(parts) < 2:
                failed += 1
                errors.append(f"Строка {i+1}: ошибка формата, требуется как минимум email и пароль")
                continue

            email = parts[0].strip()
            password = parts[1].strip()

            # Проверка формата email
            if "@" not in email:
                failed += 1
                errors.append(f"Строка {i+1}: недопустимый адрес электронной почты: {email}")
                continue

            # Проверка существования
            existing = db.query(EmailServiceModel).filter(
                EmailServiceModel.service_type == "outlook",
                EmailServiceModel.name == email
            ).first()

            if existing:
                failed += 1
                errors.append(f"Строка {i+1}: email уже существует: {email}")
                continue

            # Построение конфигурации
            config = {
                "email": email,
                "password": password
            }

            # Проверка наличия OAuth информации (формат 2)
            if len(parts) >= 4:
                client_id = parts[2].strip()
                refresh_token = parts[3].strip()
                if client_id and refresh_token:
                    config["client_id"] = client_id
                    config["refresh_token"] = refresh_token

            # Создание записи сервиса
            try:
                service = EmailServiceModel(
                    service_type="outlook",
                    name=email,
                    config=config,
                    enabled=request.enabled,
                    priority=request.priority
                )
                db.add(service)
                db.commit()
                db.refresh(service)

                accounts.append({
                    "id": service.id,
                    "email": email,
                    "has_oauth": bool(config.get("client_id")),
                    "name": email
                })
                success += 1

            except Exception as e:
                failed += 1
                errors.append(f"Строка {i+1}: ошибка создания: {str(e)}")
                db.rollback()

    return OutlookBatchImportResponse(
        total=total,
        success=success,
        failed=failed,
        accounts=accounts,
        errors=errors
    )


@router.delete("/outlook/batch")
async def batch_delete_outlook(service_ids: List[int]):
    """Пакетное удаление почтовых сервисов Outlook"""
    deleted = 0
    with get_db() as db:
        for service_id in service_ids:
            service = db.query(EmailServiceModel).filter(
                EmailServiceModel.id == service_id,
                EmailServiceModel.service_type == "outlook"
            ).first()
            if service:
                db.delete(service)
                deleted += 1
        db.commit()

    return {"success": True, "deleted": deleted, "message": f"Удалено {deleted} сервисов"}


# ============== Тестирование временной почты ==============

class TempmailTestRequest(BaseModel):
    """Запрос на тестирование временной почты"""
    api_url: Optional[str] = None


@router.post("/test-tempmail")
async def test_tempmail_service(request: TempmailTestRequest):
    """Тестирование доступности сервиса временной почты"""
    try:
        from ...services import EmailServiceFactory, EmailServiceType
        from ...config.settings import get_settings

        settings = get_settings()
        base_url = request.api_url or settings.tempmail_base_url

        config = {"base_url": base_url}
        tempmail = EmailServiceFactory.create(EmailServiceType.TEMPMAIL, config)

        # Проверка состояния сервиса
        health = tempmail.check_health()

        if health:
            return {"success": True, "message": "Подключение к временной почте в норме"}
        else:
            return {"success": False, "message": "Ошибка подключения к временной почте"}

    except Exception as e:
        logger.error(f"Ошибка тестирования временной почты: {e}")
        return {"success": False, "message": f"Ошибка тестирования: {str(e)}"}
