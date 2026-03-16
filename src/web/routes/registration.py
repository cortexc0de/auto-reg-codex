"""
Маршруты API задач регистрации
"""

import asyncio
import logging
import uuid
import random
from datetime import datetime
from typing import List, Optional, Dict, Tuple

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from ...database import crud
from ...database.session import get_db
from ...database.models import RegistrationTask, Proxy
from ...core.register import RegistrationEngine, RegistrationResult
from ...services import EmailServiceFactory, EmailServiceType
from ...config.settings import get_settings
from ..task_manager import task_manager

logger = logging.getLogger(__name__)
router = APIRouter()

# Хранилище задач (простое хранилище в памяти, для продакшена следует использовать Redis)
running_tasks: dict = {}
# Хранилище пакетных задач
batch_tasks: Dict[str, dict] = {}


# ============== Proxy Helper Functions ==============

def get_proxy_for_registration(db) -> Tuple[Optional[str], Optional[int]]:
    """
    Получение прокси для регистрации

    Стратегия:
    1. Приоритетно выбираем случайный включённый прокси из списка
    2. Если список прокси пуст и включён динамический прокси, запрашиваем через API динамического прокси
    3. Иначе используем статический прокси по умолчанию из системных настроек

    Returns:
        Tuple[proxy_url, proxy_id]: URL прокси и ID прокси (если из списка прокси)
    """
    # Сначала пытаемся получить из списка прокси
    proxy = crud.get_random_proxy(db)
    if proxy:
        return proxy.proxy_url, proxy.id

    # Список прокси пуст, пробуем динамический или статический прокси
    from ...core.dynamic_proxy import get_proxy_url_for_task
    proxy_url = get_proxy_url_for_task()
    if proxy_url:
        return proxy_url, None

    return None, None


def update_proxy_usage(db, proxy_id: Optional[int]):
    """Обновление времени использования прокси"""
    if proxy_id:
        crud.update_proxy_last_used(db, proxy_id)


# ============== Pydantic Models ==============

class RegistrationTaskCreate(BaseModel):
    """Запрос на создание задачи регистрации"""
    email_service_type: str = "tempmail"
    proxy: Optional[str] = None
    email_service_config: Optional[dict] = None
    email_service_id: Optional[int] = None  # ID настроенного почтового сервиса из базы данных


class BatchRegistrationRequest(BaseModel):
    """Запрос пакетной регистрации"""
    count: int = 1  # Количество регистраций
    email_service_type: str = "tempmail"
    proxy: Optional[str] = None
    email_service_config: Optional[dict] = None
    email_service_id: Optional[int] = None  # ID настроенного почтового сервиса из базы данных
    interval_min: int = 5  # Минимальный интервал в секундах
    interval_max: int = 30  # Максимальный интервал в секундах
    concurrency: int = 1   # Количество параллельных потоков (1-50)
    mode: str = "pipeline"  # Режим выполнения: "parallel" или "pipeline"


class RegistrationTaskResponse(BaseModel):
    """Ответ задачи регистрации"""
    id: int
    task_uuid: str
    status: str
    email_service_id: Optional[int] = None
    proxy: Optional[str] = None
    logs: Optional[str] = None
    result: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    class Config:
        from_attributes = True


class BatchRegistrationResponse(BaseModel):
    """Ответ пакетной регистрации"""
    batch_id: str
    count: int
    tasks: List[RegistrationTaskResponse]


class TaskListResponse(BaseModel):
    """Ответ со списком задач"""
    total: int
    tasks: List[RegistrationTaskResponse]


# ============== Модели пакетной регистрации Outlook ==============

class OutlookAccountForRegistration(BaseModel):
    """Аккаунт Outlook, доступный для регистрации"""
    id: int                      # ID из таблицы EmailService
    email: str
    name: str
    has_oauth: bool              # Есть ли OAuth конфигурация
    is_registered: bool          # Зарегистрирован ли
    registered_account_id: Optional[int] = None


class OutlookAccountsListResponse(BaseModel):
    """Ответ со списком аккаунтов Outlook"""
    total: int
    registered_count: int        # Количество зарегистрированных
    unregistered_count: int      # Количество незарегистрированных
    accounts: List[OutlookAccountForRegistration]


class OutlookBatchRegistrationRequest(BaseModel):
    """Запрос пакетной регистрации Outlook"""
    service_ids: List[int]       # Выбранные ID EmailService
    skip_registered: bool = True  # Автоматический пропуск уже зарегистрированных
    proxy: Optional[str] = None
    interval_min: int = 5
    interval_max: int = 30
    concurrency: int = 1   # Количество параллельных потоков (1-50)
    mode: str = "pipeline"  # Режим выполнения: "parallel" или "pipeline"


class OutlookBatchRegistrationResponse(BaseModel):
    """Ответ пакетной регистрации Outlook"""
    batch_id: str
    total: int                   # Всего
    skipped: int                 # Пропущено (уже зарегистрированы)
    to_register: int             # Ожидают регистрации
    service_ids: List[int]       # ID сервисов для фактической регистрации


# ============== Helper Functions ==============

def task_to_response(task: RegistrationTask) -> RegistrationTaskResponse:
    """Преобразование модели задачи в ответ"""
    return RegistrationTaskResponse(
        id=task.id,
        task_uuid=task.task_uuid,
        status=task.status,
        email_service_id=task.email_service_id,
        proxy=task.proxy,
        logs=task.logs,
        result=task.result,
        error_message=task.error_message,
        created_at=task.created_at.isoformat() if task.created_at else None,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


def _run_sync_registration_task(task_uuid: str, email_service_type: str, proxy: Optional[str], email_service_config: Optional[dict], email_service_id: Optional[int] = None, log_prefix: str = "", batch_id: str = ""):
    """
    Синхронная задача регистрации, выполняемая в пуле потоков

    Эта функция вызывается через run_in_executor, работает в отдельном потоке
    """
    with get_db() as db:
        try:
            # Проверка отмены
            if task_manager.is_cancelled(task_uuid):
                logger.info(f"Задача {task_uuid} отменена, пропуск выполнения")
                return

            # Обновление статуса задачи на "выполняется"
            task = crud.update_registration_task(
                db, task_uuid,
                status="running",
                started_at=datetime.utcnow()
            )

            if not task:
                logger.error(f"Задача не существует: {task_uuid}")
                return

            # Обновление статуса в TaskManager
            task_manager.update_status(task_uuid, "running")

            # Определение используемого прокси
            # Если прокси передан с фронтенда, используем его
            # Иначе получаем из списка прокси или системных настроек
            actual_proxy_url = proxy
            proxy_id = None

            if not actual_proxy_url:
                actual_proxy_url, proxy_id = get_proxy_for_registration(db)
                if actual_proxy_url:
                    logger.info(f"Задача {task_uuid} использует прокси: {actual_proxy_url[:50]}...")

            # Обновление записи прокси задачи
            crud.update_registration_task(db, task_uuid, proxy=actual_proxy_url)

            # Создание почтового сервиса
            service_type = EmailServiceType(email_service_type)
            settings = get_settings()

            # Приоритетно используем настроенный почтовый сервис из базы данных
            if email_service_id:
                from ...database.models import EmailService as EmailServiceModel
                db_service = db.query(EmailServiceModel).filter(
                    EmailServiceModel.id == email_service_id,
                    EmailServiceModel.enabled == True
                ).first()

                if db_service:
                    config = db_service.config.copy() if db_service.config else {}
                    # Совместимость со старыми именами полей api_url -> base_url
                    if 'api_url' in config and 'base_url' not in config:
                        config['base_url'] = config.pop('api_url')
                    if 'domain' in config and 'default_domain' not in config:
                        config['default_domain'] = config.pop('domain')
                    # Обновление привязки почтового сервиса задачи
                    crud.update_registration_task(db, task_uuid, email_service_id=db_service.id)
                    logger.info(f"Используется почтовый сервис из БД: {db_service.name} (ID: {db_service.id})")
                else:
                    raise ValueError(f"Почтовый сервис не существует или отключён: {email_service_id}")
            else:
                # Использование конфигурации по умолчанию или переданной конфигурации
                if service_type == EmailServiceType.TEMPMAIL:
                    config = {
                        "base_url": settings.tempmail_base_url,
                        "timeout": settings.tempmail_timeout,
                        "max_retries": settings.tempmail_max_retries,
                        "proxy_url": actual_proxy_url,
                    }
                elif service_type == EmailServiceType.CUSTOM_DOMAIN:
                    # Проверка наличия доступного сервиса пользовательского домена в БД
                    from ...database.models import EmailService as EmailServiceModel
                    db_service = db.query(EmailServiceModel).filter(
                        EmailServiceModel.service_type == "custom_domain",
                        EmailServiceModel.enabled == True
                    ).order_by(EmailServiceModel.priority.asc()).first()

                    if db_service and db_service.config:
                        config = db_service.config.copy()
                        # Совместимость со старыми именами полей api_url -> base_url
                        if 'api_url' in config and 'base_url' not in config:
                            config['base_url'] = config.pop('api_url')
                        if 'domain' in config and 'default_domain' not in config:
                            config['default_domain'] = config.pop('domain')
                        crud.update_registration_task(db, task_uuid, email_service_id=db_service.id)
                        logger.info(f"Используется сервис пользовательского домена из БД: {db_service.name}")
                    elif settings.custom_domain_base_url and settings.custom_domain_api_key:
                        config = {
                            "base_url": settings.custom_domain_base_url,
                            "api_key": settings.custom_domain_api_key.get_secret_value() if settings.custom_domain_api_key else "",
                            "proxy_url": actual_proxy_url,
                        }
                    else:
                        raise ValueError("Нет доступного сервиса почты с пользовательским доменом, сначала настройте его в настройках")
                elif service_type == EmailServiceType.OUTLOOK:
                    # Проверка наличия доступного аккаунта Outlook в БД
                    from ...database.models import EmailService as EmailServiceModel, Account
                    # Получение всех включённых сервисов Outlook
                    outlook_services = db.query(EmailServiceModel).filter(
                        EmailServiceModel.service_type == "outlook",
                        EmailServiceModel.enabled == True
                    ).order_by(EmailServiceModel.priority.asc()).all()

                    if not outlook_services:
                        raise ValueError("Нет доступных аккаунтов Outlook, сначала импортируйте аккаунты в настройках")

                    # Поиск незарегистрированного аккаунта Outlook
                    selected_service = None
                    for svc in outlook_services:
                        email = svc.config.get("email") if svc.config else None
                        if not email:
                            continue
                        # Проверка, зарегистрирован ли уже в таблице accounts
                        existing = db.query(Account).filter(Account.email == email).first()
                        if not existing:
                            selected_service = svc
                            logger.info(f"Выбран незарегистрированный аккаунт Outlook: {email}")
                            break
                        else:
                            logger.info(f"Пропуск уже зарегистрированного аккаунта Outlook: {email}")

                    if selected_service and selected_service.config:
                        config = selected_service.config.copy()
                        crud.update_registration_task(db, task_uuid, email_service_id=selected_service.id)
                        logger.info(f"Используется аккаунт Outlook из БД: {selected_service.name}")
                    else:
                        raise ValueError("Все аккаунты Outlook уже зарегистрированы в OpenAI, добавьте новые аккаунты Outlook")
                else:
                    config = email_service_config or {}

            email_service = EmailServiceFactory.create(service_type, config)

            # Создание движка регистрации — используем callback логов TaskManager
            log_callback = task_manager.create_log_callback(task_uuid, prefix=log_prefix, batch_id=batch_id)

            engine = RegistrationEngine(
                email_service=email_service,
                proxy_url=actual_proxy_url,
                callback_logger=log_callback,
                task_uuid=task_uuid
            )

            # Выполнение регистрации
            result = engine.run()

            if result.success:
                # Обновление времени использования прокси
                update_proxy_usage(db, proxy_id)

                # Сохранение в базу данных
                engine.save_to_database(result)

                # Обновление статуса задачи
                crud.update_registration_task(
                    db, task_uuid,
                    status="completed",
                    completed_at=datetime.utcnow(),
                    result=result.to_dict()
                )

                # Обновление статуса в TaskManager
                task_manager.update_status(task_uuid, "completed", email=result.email)

                logger.info(f"Задача регистрации завершена: {task_uuid}, почта: {result.email}")
            else:
                # Обновление статуса задачи на "ошибка"
                crud.update_registration_task(
                    db, task_uuid,
                    status="failed",
                    completed_at=datetime.utcnow(),
                    error_message=result.error_message
                )

                # Обновление статуса в TaskManager
                task_manager.update_status(task_uuid, "failed", error=result.error_message)

                logger.warning(f"Задача регистрации не удалась: {task_uuid}, причина: {result.error_message}")

        except Exception as e:
            logger.error(f"Исключение в задаче регистрации: {task_uuid}, ошибка: {e}")

            try:
                with get_db() as db:
                    crud.update_registration_task(
                        db, task_uuid,
                        status="failed",
                        completed_at=datetime.utcnow(),
                        error_message=str(e)
                    )

                # Обновление статуса в TaskManager
                task_manager.update_status(task_uuid, "failed", error=str(e))
            except:
                pass


async def run_registration_task(task_uuid: str, email_service_type: str, proxy: Optional[str], email_service_config: Optional[dict], email_service_id: Optional[int] = None, log_prefix: str = "", batch_id: str = ""):
    """
    Асинхронное выполнение задачи регистрации

    Использует run_in_executor для помещения синхронной задачи в пул потоков, чтобы не блокировать основной цикл событий
    """
    loop = task_manager.get_loop()
    if loop is None:
        loop = asyncio.get_event_loop()
        task_manager.set_loop(loop)

    # Инициализация статуса в TaskManager
    task_manager.update_status(task_uuid, "pending")
    task_manager.add_log(task_uuid, f"{log_prefix} [Система] Задача {task_uuid[:8]} добавлена в очередь" if log_prefix else f"[Система] Задача {task_uuid[:8]} добавлена в очередь")

    try:
        # Выполнение синхронной задачи в пуле потоков (передаём log_prefix и batch_id для callback)
        await loop.run_in_executor(
            task_manager.executor,
            _run_sync_registration_task,
            task_uuid,
            email_service_type,
            proxy,
            email_service_config,
            email_service_id,
            log_prefix,
            batch_id
        )
    except Exception as e:
        logger.error(f"Исключение в пуле потоков: {task_uuid}, ошибка: {e}")
        task_manager.add_log(task_uuid, f"[Ошибка] Исключение в пуле потоков: {str(e)}")
        task_manager.update_status(task_uuid, "failed", error=str(e))


def _init_batch_state(batch_id: str, task_uuids: List[str]):
    """Инициализация состояния пакетной задачи в памяти"""
    task_manager.init_batch(batch_id, len(task_uuids))
    batch_tasks[batch_id] = {
        "total": len(task_uuids),
        "completed": 0,
        "success": 0,
        "failed": 0,
        "cancelled": False,
        "task_uuids": task_uuids,
        "current_index": 0,
        "logs": [],
        "finished": False
    }


def _make_batch_helpers(batch_id: str):
    """Возвращает вспомогательные функции add_batch_log и update_batch_status"""
    def add_batch_log(msg: str):
        batch_tasks[batch_id]["logs"].append(msg)
        task_manager.add_batch_log(batch_id, msg)

    def update_batch_status(**kwargs):
        for key, value in kwargs.items():
            if key in batch_tasks[batch_id]:
                batch_tasks[batch_id][key] = value
        task_manager.update_batch_status(batch_id, **kwargs)

    return add_batch_log, update_batch_status


async def run_batch_parallel(
    batch_id: str,
    task_uuids: List[str],
    email_service_type: str,
    proxy: Optional[str],
    email_service_config: Optional[dict],
    email_service_id: Optional[int],
    concurrency: int
):
    """
    Параллельный режим: все задачи отправляются одновременно, Semaphore контролирует максимальный параллелизм
    """
    _init_batch_state(batch_id, task_uuids)
    add_batch_log, update_batch_status = _make_batch_helpers(batch_id)
    semaphore = asyncio.Semaphore(concurrency)
    counter_lock = asyncio.Lock()
    add_batch_log(f"[Система] Параллельный режим запущен, параллелизм: {concurrency}, всего задач: {len(task_uuids)}")

    async def _run_one(idx: int, uuid: str):
        prefix = f"[Задача{idx + 1}]"
        async with semaphore:
            await run_registration_task(
                uuid, email_service_type, proxy, email_service_config, email_service_id,
                log_prefix=prefix, batch_id=batch_id
            )
        with get_db() as db:
            t = crud.get_registration_task(db, uuid)
            if t:
                async with counter_lock:
                    new_completed = batch_tasks[batch_id]["completed"] + 1
                    new_success = batch_tasks[batch_id]["success"]
                    new_failed = batch_tasks[batch_id]["failed"]
                    if t.status == "completed":
                        new_success += 1
                        add_batch_log(f"{prefix} [Успех] Регистрация успешна")
                    elif t.status == "failed":
                        new_failed += 1
                        add_batch_log(f"{prefix} [Неудача] Регистрация не удалась: {t.error_message}")
                    update_batch_status(completed=new_completed, success=new_success, failed=new_failed)

    try:
        await asyncio.gather(*[_run_one(i, u) for i, u in enumerate(task_uuids)], return_exceptions=True)
        if not task_manager.is_batch_cancelled(batch_id):
            add_batch_log(f"[Завершено] Пакетная задача завершена! Успешно: {batch_tasks[batch_id]['success']}, Неудач: {batch_tasks[batch_id]['failed']}")
            update_batch_status(finished=True, status="completed")
        else:
            update_batch_status(finished=True, status="cancelled")
    except Exception as e:
        logger.error(f"Исключение в пакетной задаче {batch_id}: {e}")
        add_batch_log(f"[Ошибка] Исключение в пакетной задаче: {str(e)}")
        update_batch_status(finished=True, status="failed")
    finally:
        batch_tasks[batch_id]["finished"] = True


async def run_batch_pipeline(
    batch_id: str,
    task_uuids: List[str],
    email_service_type: str,
    proxy: Optional[str],
    email_service_config: Optional[dict],
    email_service_id: Optional[int],
    interval_min: int,
    interval_max: int,
    concurrency: int
):
    """
    Конвейерный режим: каждые interval секунд запускается новая задача, Semaphore ограничивает максимальный параллелизм
    """
    _init_batch_state(batch_id, task_uuids)
    add_batch_log, update_batch_status = _make_batch_helpers(batch_id)
    semaphore = asyncio.Semaphore(concurrency)
    counter_lock = asyncio.Lock()
    running_tasks_list = []
    add_batch_log(f"[Система] Конвейерный режим запущен, параллелизм: {concurrency}, всего задач: {len(task_uuids)}")

    async def _run_and_release(idx: int, uuid: str, pfx: str):
        try:
            await run_registration_task(
                uuid, email_service_type, proxy, email_service_config, email_service_id,
                log_prefix=pfx, batch_id=batch_id
            )
            with get_db() as db:
                t = crud.get_registration_task(db, uuid)
                if t:
                    async with counter_lock:
                        new_completed = batch_tasks[batch_id]["completed"] + 1
                        new_success = batch_tasks[batch_id]["success"]
                        new_failed = batch_tasks[batch_id]["failed"]
                        if t.status == "completed":
                            new_success += 1
                            add_batch_log(f"{pfx} [Успех] Регистрация успешна")
                        elif t.status == "failed":
                            new_failed += 1
                            add_batch_log(f"{pfx} [Неудача] Регистрация не удалась: {t.error_message}")
                        update_batch_status(completed=new_completed, success=new_success, failed=new_failed)
        finally:
            semaphore.release()

    try:
        for i, task_uuid in enumerate(task_uuids):
            if task_manager.is_batch_cancelled(batch_id) or batch_tasks[batch_id]["cancelled"]:
                with get_db() as db:
                    for remaining_uuid in task_uuids[i:]:
                        crud.update_registration_task(db, remaining_uuid, status="cancelled")
                add_batch_log("[Отмена] Пакетная задача отменена")
                update_batch_status(finished=True, status="cancelled")
                break

            update_batch_status(current_index=i)
            await semaphore.acquire()
            prefix = f"[Задача{i + 1}]"
            add_batch_log(f"{prefix} Начало регистрации...")
            t = asyncio.create_task(_run_and_release(i, task_uuid, prefix))
            running_tasks_list.append(t)

            if i < len(task_uuids) - 1 and not task_manager.is_batch_cancelled(batch_id):
                wait_time = random.randint(interval_min, interval_max)
                logger.info(f"Пакетная задача {batch_id}: ожидание {wait_time} сек перед запуском следующей задачи")
                await asyncio.sleep(wait_time)

        if running_tasks_list:
            await asyncio.gather(*running_tasks_list, return_exceptions=True)

        if not task_manager.is_batch_cancelled(batch_id):
            add_batch_log(f"[Завершено] Пакетная задача завершена! Успешно: {batch_tasks[batch_id]['success']}, Неудач: {batch_tasks[batch_id]['failed']}")
            update_batch_status(finished=True, status="completed")
    except Exception as e:
        logger.error(f"Исключение в пакетной задаче {batch_id}: {e}")
        add_batch_log(f"[Ошибка] Исключение в пакетной задаче: {str(e)}")
        update_batch_status(finished=True, status="failed")
    finally:
        batch_tasks[batch_id]["finished"] = True


async def run_batch_registration(
    batch_id: str,
    task_uuids: List[str],
    email_service_type: str,
    proxy: Optional[str],
    email_service_config: Optional[dict],
    email_service_id: Optional[int],
    interval_min: int,
    interval_max: int,
    concurrency: int = 1,
    mode: str = "pipeline"
):
    """Распределение по режиму: параллельный или конвейерный"""
    if mode == "parallel":
        await run_batch_parallel(
            batch_id, task_uuids, email_service_type, proxy,
            email_service_config, email_service_id, concurrency
        )
    else:
        await run_batch_pipeline(
            batch_id, task_uuids, email_service_type, proxy,
            email_service_config, email_service_id,
            interval_min, interval_max, concurrency
        )


# ============== API Endpoints ==============

@router.post("/start", response_model=RegistrationTaskResponse)
async def start_registration(
    request: RegistrationTaskCreate,
    background_tasks: BackgroundTasks
):
    """
    Запуск задачи регистрации

    - email_service_type: тип почтового сервиса (tempmail, outlook, custom_domain)
    - proxy: адрес прокси
    - email_service_config: конфигурация почтового сервиса (для outlook необходимо предоставить данные аккаунта)
    """
    # Валидация типа почтового сервиса
    try:
        EmailServiceType(request.email_service_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип почтового сервиса: {request.email_service_type}"
        )

    # Создание задачи
    task_uuid = str(uuid.uuid4())

    with get_db() as db:
        task = crud.create_registration_task(
            db,
            task_uuid=task_uuid,
            proxy=request.proxy
        )

    # Запуск задачи регистрации в фоне
    background_tasks.add_task(
        run_registration_task,
        task_uuid,
        request.email_service_type,
        request.proxy,
        request.email_service_config,
        request.email_service_id
    )

    return task_to_response(task)


@router.post("/batch", response_model=BatchRegistrationResponse)
async def start_batch_registration(
    request: BatchRegistrationRequest,
    background_tasks: BackgroundTasks
):
    """
    Запуск пакетной регистрации

    - count: количество регистраций (1-100)
    - email_service_type: тип почтового сервиса
    - proxy: адрес прокси
    - interval_min: минимальный интервал в секундах
    - interval_max: максимальный интервал в секундах
    """
    # Валидация параметров
    if request.count < 1 or request.count > 100:
        raise HTTPException(status_code=400, detail="Количество регистраций должно быть от 1 до 100")

    try:
        EmailServiceType(request.email_service_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип почтового сервиса: {request.email_service_type}"
        )

    if request.interval_min < 0 or request.interval_max < request.interval_min:
        raise HTTPException(status_code=400, detail="Неверные параметры интервала")

    if not 1 <= request.concurrency <= 50:
        raise HTTPException(status_code=400, detail="Параллелизм должен быть от 1 до 50")

    if request.mode not in ("parallel", "pipeline"):
        raise HTTPException(status_code=400, detail="Режим должен быть parallel или pipeline")

    # Создание пакетной задачи
    batch_id = str(uuid.uuid4())
    task_uuids = []

    with get_db() as db:
        for _ in range(request.count):
            task_uuid = str(uuid.uuid4())
            task = crud.create_registration_task(
                db,
                task_uuid=task_uuid,
                proxy=request.proxy
            )
            task_uuids.append(task_uuid)

    # Получение всех задач
    with get_db() as db:
        tasks = [crud.get_registration_task(db, uuid) for uuid in task_uuids]

    # Запуск пакетной регистрации в фоне
    background_tasks.add_task(
        run_batch_registration,
        batch_id,
        task_uuids,
        request.email_service_type,
        request.proxy,
        request.email_service_config,
        request.email_service_id,
        request.interval_min,
        request.interval_max,
        request.concurrency,
        request.mode
    )

    return BatchRegistrationResponse(
        batch_id=batch_id,
        count=request.count,
        tasks=[task_to_response(t) for t in tasks if t]
    )


@router.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Получение статуса пакетной задачи"""
    if batch_id not in batch_tasks:
        raise HTTPException(status_code=404, detail="Пакетная задача не существует")

    batch = batch_tasks[batch_id]
    return {
        "batch_id": batch_id,
        "total": batch["total"],
        "completed": batch["completed"],
        "success": batch["success"],
        "failed": batch["failed"],
        "current_index": batch["current_index"],
        "cancelled": batch["cancelled"],
        "finished": batch.get("finished", False),
        "progress": f"{batch['completed']}/{batch['total']}"
    }


@router.post("/batch/{batch_id}/cancel")
async def cancel_batch(batch_id: str):
    """Отмена пакетной задачи"""
    if batch_id not in batch_tasks:
        raise HTTPException(status_code=404, detail="Пакетная задача не существует")

    batch = batch_tasks[batch_id]
    if batch.get("finished"):
        raise HTTPException(status_code=400, detail="Пакетная задача уже завершена")

    batch["cancelled"] = True
    task_manager.cancel_batch(batch_id)
    return {"success": True, "message": "Запрос на отмену пакетной задачи отправлен"}


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
):
    """Получение списка задач"""
    with get_db() as db:
        query = db.query(RegistrationTask)

        if status:
            query = query.filter(RegistrationTask.status == status)

        total = query.count()
        offset = (page - 1) * page_size
        tasks = query.order_by(RegistrationTask.created_at.desc()).offset(offset).limit(page_size).all()

        return TaskListResponse(
            total=total,
            tasks=[task_to_response(t) for t in tasks]
        )


@router.get("/tasks/{task_uuid}", response_model=RegistrationTaskResponse)
async def get_task(task_uuid: str):
    """Получение деталей задачи"""
    with get_db() as db:
        task = crud.get_registration_task(db, task_uuid)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не существует")
        return task_to_response(task)


@router.get("/tasks/{task_uuid}/logs")
async def get_task_logs(task_uuid: str):
    """Получение логов задачи"""
    with get_db() as db:
        task = crud.get_registration_task(db, task_uuid)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не существует")

        logs = task.logs or ""
        return {
            "task_uuid": task_uuid,
            "status": task.status,
            "logs": logs.split("\n") if logs else []
        }


@router.post("/tasks/{task_uuid}/cancel")
async def cancel_task(task_uuid: str):
    """Отмена задачи"""
    with get_db() as db:
        task = crud.get_registration_task(db, task_uuid)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не существует")

        if task.status not in ["pending", "running"]:
            raise HTTPException(status_code=400, detail="Задача уже завершена или отменена")

        task = crud.update_registration_task(db, task_uuid, status="cancelled")

        return {"success": True, "message": "Задача отменена"}


@router.delete("/tasks/{task_uuid}")
async def delete_task(task_uuid: str):
    """Удаление задачи"""
    with get_db() as db:
        task = crud.get_registration_task(db, task_uuid)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не существует")

        if task.status == "running":
            raise HTTPException(status_code=400, detail="Невозможно удалить выполняющуюся задачу")

        crud.delete_registration_task(db, task_uuid)

        return {"success": True, "message": "Задача удалена"}


@router.get("/stats")
async def get_registration_stats():
    """Получение статистики регистрации"""
    with get_db() as db:
        from sqlalchemy import func

        # Статистика по статусам
        status_stats = db.query(
            RegistrationTask.status,
            func.count(RegistrationTask.id)
        ).group_by(RegistrationTask.status).all()

        # Количество регистраций за сегодня
        today = datetime.utcnow().date()
        today_count = db.query(func.count(RegistrationTask.id)).filter(
            func.date(RegistrationTask.created_at) == today
        ).scalar()

        return {
            "by_status": {status: count for status, count in status_stats},
            "today_count": today_count
        }


@router.get("/available-services")
async def get_available_email_services():
    """
    Получение списка доступных почтовых сервисов для регистрации

    Возвращает все включённые почтовые сервисы, включая:
    - tempmail: временная почта (не требует настройки)
    - outlook: импортированные аккаунты Outlook
    - custom_domain: настроенные сервисы пользовательских доменов
    """
    from ...database.models import EmailService as EmailServiceModel
    from ...config.settings import get_settings

    settings = get_settings()
    result = {
        "tempmail": {
            "available": True,
            "count": 1,
            "services": [{
                "id": None,
                "name": "Tempmail.lol",
                "type": "tempmail",
                "description": "Временная почта, автоматическое создание"
            }]
        },
        "outlook": {
            "available": False,
            "count": 0,
            "services": []
        },
        "custom_domain": {
            "available": False,
            "count": 0,
            "services": []
        }
    }

    with get_db() as db:
        # Получение аккаунтов Outlook
        outlook_services = db.query(EmailServiceModel).filter(
            EmailServiceModel.service_type == "outlook",
            EmailServiceModel.enabled == True
        ).order_by(EmailServiceModel.priority.asc()).all()

        for service in outlook_services:
            config = service.config or {}
            result["outlook"]["services"].append({
                "id": service.id,
                "name": service.name,
                "type": "outlook",
                "has_oauth": bool(config.get("client_id") and config.get("refresh_token")),
                "priority": service.priority
            })

        result["outlook"]["count"] = len(outlook_services)
        result["outlook"]["available"] = len(outlook_services) > 0

        # Получение сервисов пользовательских доменов
        custom_services = db.query(EmailServiceModel).filter(
            EmailServiceModel.service_type == "custom_domain",
            EmailServiceModel.enabled == True
        ).order_by(EmailServiceModel.priority.asc()).all()

        for service in custom_services:
            config = service.config or {}
            result["custom_domain"]["services"].append({
                "id": service.id,
                "name": service.name,
                "type": "custom_domain",
                "default_domain": config.get("default_domain"),
                "priority": service.priority
            })

        result["custom_domain"]["count"] = len(custom_services)
        result["custom_domain"]["available"] = len(custom_services) > 0

        # Если в БД нет сервисов пользовательских доменов, проверяем settings
        if not result["custom_domain"]["available"]:
            if settings.custom_domain_base_url and settings.custom_domain_api_key:
                result["custom_domain"]["available"] = True
                result["custom_domain"]["count"] = 1
                result["custom_domain"]["services"].append({
                    "id": None,
                    "name": "Сервис пользовательского домена по умолчанию",
                    "type": "custom_domain",
                    "from_settings": True
                })

    return result


# ============== API пакетной регистрации Outlook ==============

@router.get("/outlook-accounts", response_model=OutlookAccountsListResponse)
async def get_outlook_accounts_for_registration():
    """
    Получение списка аккаунтов Outlook для регистрации

    Возвращает все включённые сервисы Outlook и проверяет, зарегистрирован ли каждый email в таблице accounts
    """
    from ...database.models import EmailService as EmailServiceModel
    from ...database.models import Account

    with get_db() as db:
        # Получение всех включённых сервисов Outlook
        outlook_services = db.query(EmailServiceModel).filter(
            EmailServiceModel.service_type == "outlook",
            EmailServiceModel.enabled == True
        ).order_by(EmailServiceModel.priority.asc()).all()

        accounts = []
        registered_count = 0
        unregistered_count = 0

        for service in outlook_services:
            config = service.config or {}
            email = config.get("email") or service.name

            # Проверка регистрации (запрос таблицы accounts)
            existing_account = db.query(Account).filter(
                Account.email == email
            ).first()

            is_registered = existing_account is not None
            if is_registered:
                registered_count += 1
            else:
                unregistered_count += 1

            accounts.append(OutlookAccountForRegistration(
                id=service.id,
                email=email,
                name=service.name,
                has_oauth=bool(config.get("client_id") and config.get("refresh_token")),
                is_registered=is_registered,
                registered_account_id=existing_account.id if existing_account else None
            ))

        return OutlookAccountsListResponse(
            total=len(accounts),
            registered_count=registered_count,
            unregistered_count=unregistered_count,
            accounts=accounts
        )


async def run_outlook_batch_registration(
    batch_id: str,
    service_ids: List[int],
    skip_registered: bool,
    proxy: Optional[str],
    interval_min: int,
    interval_max: int,
    concurrency: int = 1,
    mode: str = "pipeline"
):
    """
    Асинхронное выполнение пакетной регистрации Outlook, с использованием общей логики параллелизма

    Каждый service_id сопоставляется с отдельным task_uuid, затем вызывается
    логика параллелизма run_batch_registration
    """
    loop = task_manager.get_loop()
    if loop is None:
        loop = asyncio.get_event_loop()
        task_manager.set_loop(loop)

    # Предварительное создание записей задач регистрации для каждого service_id
    task_uuids = []
    with get_db() as db:
        for service_id in service_ids:
            task_uuid = str(uuid.uuid4())
            crud.create_registration_task(
                db,
                task_uuid=task_uuid,
                proxy=proxy,
                email_service_id=service_id
            )
            task_uuids.append(task_uuid)

    # Использование общей логики параллелизма (тип сервиса outlook, каждая задача привязана к своему email_service_id)
    await run_batch_registration(
        batch_id=batch_id,
        task_uuids=task_uuids,
        email_service_type="outlook",
        proxy=proxy,
        email_service_config=None,
        email_service_id=None,   # Каждая задача уже привязана к своему email_service_id
        interval_min=interval_min,
        interval_max=interval_max,
        concurrency=concurrency,
        mode=mode
    )


@router.post("/outlook-batch", response_model=OutlookBatchRegistrationResponse)
async def start_outlook_batch_registration(
    request: OutlookBatchRegistrationRequest,
    background_tasks: BackgroundTasks
):
    """
    Запуск пакетной регистрации Outlook

    - service_ids: список выбранных ID EmailService
    - skip_registered: автоматический пропуск уже зарегистрированных (по умолчанию True)
    - proxy: адрес прокси
    - interval_min: минимальный интервал в секундах
    - interval_max: максимальный интервал в секундах
    """
    from ...database.models import EmailService as EmailServiceModel
    from ...database.models import Account

    # Валидация параметров
    if not request.service_ids:
        raise HTTPException(status_code=400, detail="Выберите хотя бы один аккаунт Outlook")

    if request.interval_min < 0 or request.interval_max < request.interval_min:
        raise HTTPException(status_code=400, detail="Неверные параметры интервала")

    if not 1 <= request.concurrency <= 50:
        raise HTTPException(status_code=400, detail="Параллелизм должен быть от 1 до 50")

    if request.mode not in ("parallel", "pipeline"):
        raise HTTPException(status_code=400, detail="Режим должен быть parallel или pipeline")

    # Фильтрация уже зарегистрированных
    actual_service_ids = request.service_ids
    skipped_count = 0

    if request.skip_registered:
        actual_service_ids = []
        with get_db() as db:
            for service_id in request.service_ids:
                service = db.query(EmailServiceModel).filter(
                    EmailServiceModel.id == service_id
                ).first()

                if not service:
                    continue

                config = service.config or {}
                email = config.get("email") or service.name

                # Проверка регистрации
                existing_account = db.query(Account).filter(
                    Account.email == email
                ).first()

                if existing_account:
                    skipped_count += 1
                else:
                    actual_service_ids.append(service_id)

    if not actual_service_ids:
        return OutlookBatchRegistrationResponse(
            batch_id="",
            total=len(request.service_ids),
            skipped=skipped_count,
            to_register=0,
            service_ids=[]
        )

    # Создание пакетной задачи
    batch_id = str(uuid.uuid4())

    # Инициализация статуса пакетной задачи
    batch_tasks[batch_id] = {
        "total": len(actual_service_ids),
        "completed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "cancelled": False,
        "service_ids": actual_service_ids,
        "current_index": 0,
        "logs": [],
        "finished": False
    }

    # Запуск пакетной регистрации в фоне
    background_tasks.add_task(
        run_outlook_batch_registration,
        batch_id,
        actual_service_ids,
        request.skip_registered,
        request.proxy,
        request.interval_min,
        request.interval_max,
        request.concurrency,
        request.mode
    )

    return OutlookBatchRegistrationResponse(
        batch_id=batch_id,
        total=len(request.service_ids),
        skipped=skipped_count,
        to_register=len(actual_service_ids),
        service_ids=actual_service_ids
    )


@router.get("/outlook-batch/{batch_id}")
async def get_outlook_batch_status(batch_id: str):
    """Получение статуса пакетной задачи Outlook"""
    if batch_id not in batch_tasks:
        raise HTTPException(status_code=404, detail="Пакетная задача не существует")

    batch = batch_tasks[batch_id]
    return {
        "batch_id": batch_id,
        "total": batch["total"],
        "completed": batch["completed"],
        "success": batch["success"],
        "failed": batch["failed"],
        "skipped": batch.get("skipped", 0),
        "current_index": batch["current_index"],
        "cancelled": batch["cancelled"],
        "finished": batch.get("finished", False),
        "logs": batch.get("logs", []),
        "progress": f"{batch['completed']}/{batch['total']}"
    }


@router.post("/outlook-batch/{batch_id}/cancel")
async def cancel_outlook_batch(batch_id: str):
    """Отмена пакетной задачи Outlook"""
    if batch_id not in batch_tasks:
        raise HTTPException(status_code=404, detail="Пакетная задача не существует")

    batch = batch_tasks[batch_id]
    if batch.get("finished"):
        raise HTTPException(status_code=400, detail="Пакетная задача уже завершена")

    # Обновляем статус отмены в обеих системах
    batch["cancelled"] = True
    task_manager.cancel_batch(batch_id)

    return {"success": True, "message": "Запрос на отмену пакетной задачи отправлен"}
