"""
Маршруты API управления аккаунтами
"""

import json
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...database import crud
from ...database.session import get_db
from ...database.models import Account
from ...config.constants import AccountStatus
from ...config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== Pydantic Models ==============

class AccountResponse(BaseModel):
    """Модель ответа аккаунта"""
    id: int
    email: str
    password: Optional[str] = None
    client_id: Optional[str] = None
    email_service: str
    account_id: Optional[str] = None
    workspace_id: Optional[str] = None
    registered_at: Optional[str] = None
    last_refresh: Optional[str] = None
    expires_at: Optional[str] = None
    status: str
    proxy_used: Optional[str] = None
    cpa_uploaded: bool = False
    cpa_uploaded_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class AccountListResponse(BaseModel):
    """Ответ со списком аккаунтов"""
    total: int
    accounts: List[AccountResponse]


class AccountUpdateRequest(BaseModel):
    """Запрос на обновление аккаунта"""
    status: Optional[str] = None
    metadata: Optional[dict] = None


class BatchDeleteRequest(BaseModel):
    """Запрос на пакетное удаление"""
    ids: List[int] = []
    select_all: bool = False
    status_filter: Optional[str] = None
    email_service_filter: Optional[str] = None
    search_filter: Optional[str] = None


class BatchUpdateRequest(BaseModel):
    """Запрос на пакетное обновление"""
    ids: List[int]
    status: str


# ============== Helper Functions ==============

def resolve_account_ids(
    db,
    ids: List[int],
    select_all: bool = False,
    status_filter: Optional[str] = None,
    email_service_filter: Optional[str] = None,
    search_filter: Optional[str] = None,
) -> List[int]:
    """При select_all=True запрашивает все подходящие ID, иначе возвращает переданные ids"""
    if not select_all:
        return ids
    query = db.query(Account.id)
    if status_filter:
        query = query.filter(Account.status == status_filter)
    if email_service_filter:
        query = query.filter(Account.email_service == email_service_filter)
    if search_filter:
        pattern = f"%{search_filter}%"
        query = query.filter(
            (Account.email.ilike(pattern)) | (Account.account_id.ilike(pattern))
        )
    return [row[0] for row in query.all()]


def account_to_response(account: Account) -> AccountResponse:
    """Преобразование модели Account в модель ответа"""
    return AccountResponse(
        id=account.id,
        email=account.email,
        password=account.password,
        client_id=account.client_id,
        email_service=account.email_service,
        account_id=account.account_id,
        workspace_id=account.workspace_id,
        registered_at=account.registered_at.isoformat() if account.registered_at else None,
        last_refresh=account.last_refresh.isoformat() if account.last_refresh else None,
        expires_at=account.expires_at.isoformat() if account.expires_at else None,
        status=account.status,
        proxy_used=account.proxy_used,
        cpa_uploaded=account.cpa_uploaded or False,
        cpa_uploaded_at=account.cpa_uploaded_at.isoformat() if account.cpa_uploaded_at else None,
        created_at=account.created_at.isoformat() if account.created_at else None,
        updated_at=account.updated_at.isoformat() if account.updated_at else None,
    )


# ============== API Endpoints ==============

@router.get("", response_model=AccountListResponse)
async def list_accounts(
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=1, le=100, description="Количество на странице"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    email_service: Optional[str] = Query(None, description="Фильтр по почтовому сервису"),
    search: Optional[str] = Query(None, description="Ключевое слово поиска"),
):
    """
    Получение списка аккаунтов

    Поддерживает пагинацию, фильтрацию по статусу, почтовому сервису и поиск
    """
    with get_db() as db:
        # Построение запроса
        query = db.query(Account)

        # Фильтр по статусу
        if status:
            query = query.filter(Account.status == status)

        # Фильтр по почтовому сервису
        if email_service:
            query = query.filter(Account.email_service == email_service)

        # Поиск
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Account.email.ilike(search_pattern)) |
                (Account.account_id.ilike(search_pattern))
            )

        # Подсчёт общего количества
        total = query.count()

        # Пагинация
        offset = (page - 1) * page_size
        accounts = query.order_by(Account.created_at.desc()).offset(offset).limit(page_size).all()

        return AccountListResponse(
            total=total,
            accounts=[account_to_response(acc) for acc in accounts]
        )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(account_id: int):
    """Получение деталей отдельного аккаунта"""
    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Аккаунт не существует")
        return account_to_response(account)


@router.get("/{account_id}/tokens")
async def get_account_tokens(account_id: int):
    """Получение информации о токенах аккаунта"""
    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Аккаунт не существует")

        return {
            "id": account.id,
            "email": account.email,
            "access_token": account.access_token,
            "refresh_token": account.refresh_token,
            "id_token": account.id_token,
            "has_tokens": bool(account.access_token and account.refresh_token),
        }


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(account_id: int, request: AccountUpdateRequest):
    """Обновление статуса аккаунта"""
    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Аккаунт не существует")

        update_data = {}
        if request.status:
            if request.status not in [e.value for e in AccountStatus]:
                raise HTTPException(status_code=400, detail="Недопустимое значение статуса")
            update_data["status"] = request.status

        if request.metadata:
            current_metadata = account.metadata or {}
            current_metadata.update(request.metadata)
            update_data["metadata"] = current_metadata

        account = crud.update_account(db, account_id, **update_data)
        return account_to_response(account)


@router.delete("/{account_id}")
async def delete_account(account_id: int):
    """Удаление отдельного аккаунта"""
    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Аккаунт не существует")

        crud.delete_account(db, account_id)
        return {"success": True, "message": f"Аккаунт {account.email} удалён"}


@router.post("/batch-delete")
async def batch_delete_accounts(request: BatchDeleteRequest):
    """Пакетное удаление аккаунтов"""
    with get_db() as db:
        ids = resolve_account_ids(
            db, request.ids, request.select_all,
            request.status_filter, request.email_service_filter, request.search_filter
        )
        deleted_count = 0
        errors = []

        for account_id in ids:
            try:
                account = crud.get_account_by_id(db, account_id)
                if account:
                    crud.delete_account(db, account_id)
                    deleted_count += 1
            except Exception as e:
                errors.append(f"ID {account_id}: {str(e)}")

        return {
            "success": True,
            "deleted_count": deleted_count,
            "errors": errors if errors else None
        }


@router.post("/batch-update")
async def batch_update_accounts(request: BatchUpdateRequest):
    """Пакетное обновление статуса аккаунтов"""
    if request.status not in [e.value for e in AccountStatus]:
        raise HTTPException(status_code=400, detail="Недопустимое значение статуса")

    with get_db() as db:
        updated_count = 0
        errors = []

        for account_id in request.ids:
            try:
                account = crud.get_account_by_id(db, account_id)
                if account:
                    crud.update_account(db, account_id, status=request.status)
                    updated_count += 1
            except Exception as e:
                errors.append(f"ID {account_id}: {str(e)}")

        return {
            "success": True,
            "updated_count": updated_count,
            "errors": errors if errors else None
        }


class BatchExportRequest(BaseModel):
    """Запрос на пакетный экспорт"""
    ids: List[int] = []
    select_all: bool = False
    status_filter: Optional[str] = None
    email_service_filter: Optional[str] = None
    search_filter: Optional[str] = None


@router.post("/export/json")
async def export_accounts_json(request: BatchExportRequest):
    """Экспорт аккаунтов в формате JSON"""
    with get_db() as db:
        ids = resolve_account_ids(
            db, request.ids, request.select_all,
            request.status_filter, request.email_service_filter, request.search_filter
        )
        accounts = db.query(Account).filter(Account.id.in_(ids)).all()

        export_data = []
        for acc in accounts:
            export_data.append({
                "email": acc.email,
                "password": acc.password,
                "client_id": acc.client_id,
                "account_id": acc.account_id,
                "workspace_id": acc.workspace_id,
                "access_token": acc.access_token,
                "refresh_token": acc.refresh_token,
                "id_token": acc.id_token,
                "session_token": acc.session_token,
                "email_service": acc.email_service,
                "registered_at": acc.registered_at.isoformat() if acc.registered_at else None,
                "last_refresh": acc.last_refresh.isoformat() if acc.last_refresh else None,
                "expires_at": acc.expires_at.isoformat() if acc.expires_at else None,
                "status": acc.status,
            })

        # Генерация имени файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"accounts_{timestamp}.json"

        # Возврат JSON ответа
        content = json.dumps(export_data, ensure_ascii=False, indent=2)

        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@router.post("/export/csv")
async def export_accounts_csv(request: BatchExportRequest):
    """Экспорт аккаунтов в формате CSV"""
    import csv
    import io

    with get_db() as db:
        ids = resolve_account_ids(
            db, request.ids, request.select_all,
            request.status_filter, request.email_service_filter, request.search_filter
        )
        accounts = db.query(Account).filter(Account.id.in_(ids)).all()

        # Создание содержимого CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Запись заголовков
        writer.writerow([
            "ID", "Email", "Password", "Client ID",
            "Account ID", "Workspace ID",
            "Access Token", "Refresh Token", "ID Token", "Session Token",
            "Email Service", "Status", "Registered At", "Last Refresh", "Expires At"
        ])

        # Запись данных
        for acc in accounts:
            writer.writerow([
                acc.id,
                acc.email,
                acc.password or "",
                acc.client_id or "",
                acc.account_id or "",
                acc.workspace_id or "",
                acc.access_token or "",
                acc.refresh_token or "",
                acc.id_token or "",
                acc.session_token or "",
                acc.email_service,
                acc.status,
                acc.registered_at.isoformat() if acc.registered_at else "",
                acc.last_refresh.isoformat() if acc.last_refresh else "",
                acc.expires_at.isoformat() if acc.expires_at else ""
            ])

        # Генерация имени файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"accounts_{timestamp}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@router.post("/export/cpa")
async def export_accounts_cpa(request: BatchExportRequest):
    """Экспорт аккаунтов в формате CPA Token JSON (каждый аккаунт в отдельном JSON файле, упакованные в ZIP)"""
    import io
    import zipfile
    from ...core.cpa_upload import generate_token_json

    with get_db() as db:
        ids = resolve_account_ids(
            db, request.ids, request.select_all,
            request.status_filter, request.email_service_filter, request.search_filter
        )
        accounts = db.query(Account).filter(Account.id.in_(ids)).all()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if len(accounts) == 1:
            # Один аккаунт — возвращаем JSON файл напрямую
            acc = accounts[0]
            token_data = generate_token_json(acc)
            content = json.dumps(token_data, ensure_ascii=False, indent=2)
            filename = f"{acc.email}.json"
            return StreamingResponse(
                iter([content]),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )

        # Несколько аккаунтов — упаковываем в ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for acc in accounts:
                token_data = generate_token_json(acc)
                content = json.dumps(token_data, ensure_ascii=False, indent=2)
                zf.writestr(f"{acc.email}.json", content)

        zip_buffer.seek(0)
        zip_filename = f"cpa_tokens_{timestamp}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
        )


@router.get("/stats/summary")
async def get_accounts_stats():
    """Получение статистики аккаунтов"""
    with get_db() as db:
        from sqlalchemy import func

        # Всего
        total = db.query(func.count(Account.id)).scalar()

        # Статистика по статусам
        status_stats = db.query(
            Account.status,
            func.count(Account.id)
        ).group_by(Account.status).all()

        # Статистика по почтовым сервисам
        service_stats = db.query(
            Account.email_service,
            func.count(Account.id)
        ).group_by(Account.email_service).all()

        return {
            "total": total,
            "by_status": {status: count for status, count in status_stats},
            "by_email_service": {service: count for service, count in service_stats}
        }


# ============== Обновление токенов ==============

class TokenRefreshRequest(BaseModel):
    """Запрос на обновление токена"""
    proxy: Optional[str] = None


class BatchRefreshRequest(BaseModel):
    """Запрос на пакетное обновление"""
    ids: List[int] = []
    proxy: Optional[str] = None
    select_all: bool = False
    status_filter: Optional[str] = None
    email_service_filter: Optional[str] = None
    search_filter: Optional[str] = None


class TokenValidateRequest(BaseModel):
    """Запрос на проверку токена"""
    proxy: Optional[str] = None


class BatchValidateRequest(BaseModel):
    """Запрос на пакетную проверку"""
    ids: List[int] = []
    proxy: Optional[str] = None
    select_all: bool = False
    status_filter: Optional[str] = None
    email_service_filter: Optional[str] = None
    search_filter: Optional[str] = None


@router.post("/{account_id}/refresh")
async def refresh_account_token(account_id: int, request: TokenRefreshRequest = None):
    """Обновление токена отдельного аккаунта"""
    from ...core.token_refresh import refresh_account_token as do_refresh

    # Использование переданного прокси или глобальной конфигурации прокси
    proxy = request.proxy if request and request.proxy else get_settings().proxy_url
    result = do_refresh(account_id, proxy)

    if result.success:
        return {
            "success": True,
            "message": "Токен успешно обновлён",
            "expires_at": result.expires_at.isoformat() if result.expires_at else None
        }
    else:
        return {
            "success": False,
            "error": result.error_message
        }


@router.post("/batch-refresh")
async def batch_refresh_tokens(request: BatchRefreshRequest, background_tasks: BackgroundTasks):
    """Пакетное обновление токенов аккаунтов"""
    from ...core.token_refresh import refresh_account_token as do_refresh

    # Использование переданного прокси или глобальной конфигурации прокси
    proxy = request.proxy if request.proxy else get_settings().proxy_url

    results = {
        "success_count": 0,
        "failed_count": 0,
        "errors": []
    }

    with get_db() as db:
        ids = resolve_account_ids(
            db, request.ids, request.select_all,
            request.status_filter, request.email_service_filter, request.search_filter
        )

    for account_id in ids:
        try:
            result = do_refresh(account_id, proxy)
            if result.success:
                results["success_count"] += 1
            else:
                results["failed_count"] += 1
                results["errors"].append({"id": account_id, "error": result.error_message})
        except Exception as e:
            results["failed_count"] += 1
            results["errors"].append({"id": account_id, "error": str(e)})

    return results


@router.post("/{account_id}/validate")
async def validate_account_token(account_id: int, request: TokenValidateRequest = None):
    """Проверка валидности токена отдельного аккаунта"""
    from ...core.token_refresh import validate_account_token as do_validate

    # Использование переданного прокси или глобальной конфигурации прокси
    proxy = request.proxy if request and request.proxy else get_settings().proxy_url
    is_valid, error = do_validate(account_id, proxy)

    return {
        "id": account_id,
        "valid": is_valid,
        "error": error
    }


@router.post("/batch-validate")
async def batch_validate_tokens(request: BatchValidateRequest):
    """Пакетная проверка валидности токенов аккаунтов"""
    from ...core.token_refresh import validate_account_token as do_validate

    # Использование переданного прокси или глобальной конфигурации прокси
    proxy = request.proxy if request.proxy else get_settings().proxy_url

    results = {
        "valid_count": 0,
        "invalid_count": 0,
        "details": []
    }

    with get_db() as db:
        ids = resolve_account_ids(
            db, request.ids, request.select_all,
            request.status_filter, request.email_service_filter, request.search_filter
        )

    for account_id in ids:
        try:
            is_valid, error = do_validate(account_id, proxy)
            results["details"].append({
                "id": account_id,
                "valid": is_valid,
                "error": error
            })
            if is_valid:
                results["valid_count"] += 1
            else:
                results["invalid_count"] += 1
        except Exception as e:
            results["invalid_count"] += 1
            results["details"].append({
                "id": account_id,
                "valid": False,
                "error": str(e)
            })

    return results


# ============== Загрузка CPA ==============

class CPAUploadRequest(BaseModel):
    """Запрос на загрузку CPA"""
    proxy: Optional[str] = None


class BatchCPAUploadRequest(BaseModel):
    """Запрос на пакетную загрузку CPA"""
    ids: List[int] = []
    proxy: Optional[str] = None
    select_all: bool = False
    status_filter: Optional[str] = None
    email_service_filter: Optional[str] = None
    search_filter: Optional[str] = None


@router.post("/{account_id}/upload-cpa")
async def upload_account_to_cpa(account_id: int, request: CPAUploadRequest = None):
    """Загрузка отдельного аккаунта в CPA"""
    from ...core.cpa_upload import upload_to_cpa, generate_token_json

    # Использование переданного прокси или глобальной конфигурации прокси
    proxy = request.proxy if request and request.proxy else get_settings().proxy_url

    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Аккаунт не существует")

        if not account.access_token:
            return {
                "success": False,
                "error": "У аккаунта отсутствует токен, загрузка невозможна"
            }

        # Генерация Token JSON
        token_data = generate_token_json(account)

        # Загрузка
        success, message = upload_to_cpa(token_data, proxy)

        if success:
            # Обновление статуса в базе данных
            account.cpa_uploaded = True
            account.cpa_uploaded_at = datetime.utcnow()
            db.commit()

            return {
                "success": True,
                "message": message
            }
        else:
            return {
                "success": False,
                "error": message
            }


@router.post("/batch-upload-cpa")
async def batch_upload_accounts_to_cpa(request: BatchCPAUploadRequest):
    """Пакетная загрузка аккаунтов в CPA"""
    from ...core.cpa_upload import batch_upload_to_cpa

    # Использование переданного прокси или глобальной конфигурации прокси
    proxy = request.proxy if request.proxy else get_settings().proxy_url

    with get_db() as db:
        ids = resolve_account_ids(
            db, request.ids, request.select_all,
            request.status_filter, request.email_service_filter, request.search_filter
        )

    results = batch_upload_to_cpa(ids, proxy)

    return results
