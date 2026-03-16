"""
Менеджер задач
Отвечает за управление фоновыми задачами, очередями логов и отправку через WebSocket
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, List, Callable, Any
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

# Глобальный пул потоков (поддержка до 50 параллельных задач регистрации)
_executor = ThreadPoolExecutor(max_workers=50, thread_name_prefix="reg_worker")

# Глобальный мета-блокировщик: защищает первое создание ключа defaultdict (избегает гонки потоков)
_meta_lock = threading.Lock()

# Очереди логов задач (task_uuid -> list of logs)
_log_queues: Dict[str, List[str]] = defaultdict(list)
_log_locks: Dict[str, threading.Lock] = {}

# Управление WebSocket соединениями (task_uuid -> list of websockets)
_ws_connections: Dict[str, List] = defaultdict(list)
_ws_lock = threading.Lock()

# Индекс отправленных логов WebSocket (task_uuid -> {websocket: sent_count})
_ws_sent_index: Dict[str, Dict] = defaultdict(dict)

# Статус задач
_task_status: Dict[str, dict] = {}

# Флаги отмены задач
_task_cancelled: Dict[str, bool] = {}

# Статус пакетных задач (batch_id -> dict)
_batch_status: Dict[str, dict] = {}
_batch_logs: Dict[str, List[str]] = defaultdict(list)
_batch_locks: Dict[str, threading.Lock] = {}


def _get_log_lock(task_uuid: str) -> threading.Lock:
    """Потокобезопасное получение или создание блокировки логов задачи"""
    if task_uuid not in _log_locks:
        with _meta_lock:
            if task_uuid not in _log_locks:
                _log_locks[task_uuid] = threading.Lock()
    return _log_locks[task_uuid]


def _get_batch_lock(batch_id: str) -> threading.Lock:
    """Потокобезопасное получение или создание блокировки логов пакетной задачи"""
    if batch_id not in _batch_locks:
        with _meta_lock:
            if batch_id not in _batch_locks:
                _batch_locks[batch_id] = threading.Lock()
    return _batch_locks[batch_id]


class TaskManager:
    """Менеджер задач"""

    def __init__(self):
        self.executor = _executor
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Установка цикла событий (вызывается при запуске FastAPI)"""
        self._loop = loop

    def get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Получение цикла событий"""
        return self._loop

    def is_cancelled(self, task_uuid: str) -> bool:
        """Проверка, отменена ли задача"""
        return _task_cancelled.get(task_uuid, False)

    def cancel_task(self, task_uuid: str):
        """Отмена задачи"""
        _task_cancelled[task_uuid] = True
        logger.info(f"Задача {task_uuid} помечена как отменённая")

    def add_log(self, task_uuid: str, log_message: str):
        """Добавление лога и отправка через WebSocket (потокобезопасно)"""
        # Сначала отправляем через WebSocket для обеспечения отправки в реальном времени
        # Затем добавляем в очередь, чтобы get_unsent_logs не получил этот лог
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_log(task_uuid, log_message),
                    self._loop
                )
            except Exception as e:
                logger.warning(f"Ошибка отправки лога через WebSocket: {e}")

        # После отправки добавляем в очередь
        with _get_log_lock(task_uuid):
            _log_queues[task_uuid].append(log_message)

    async def _broadcast_log(self, task_uuid: str, log_message: str):
        """Трансляция лога всем WebSocket соединениям"""
        with _ws_lock:
            connections = _ws_connections.get(task_uuid, []).copy()
            # Примечание: не обновляем sent_index здесь, так как лог уже добавлен в очередь через add_log
            # sent_index следует обновлять только в get_unsent_logs или при отправке исторических логов
            # Это позволяет избежать состояния гонки

        for ws in connections:
            try:
                await ws.send_json({
                    "type": "log",
                    "task_uuid": task_uuid,
                    "message": log_message,
                    "timestamp": datetime.utcnow().isoformat()
                })
                # После успешной отправки обновляем sent_index
                with _ws_lock:
                    ws_id = id(ws)
                    if task_uuid in _ws_sent_index and ws_id in _ws_sent_index[task_uuid]:
                        _ws_sent_index[task_uuid][ws_id] += 1
            except Exception as e:
                logger.warning(f"Ошибка отправки через WebSocket: {e}")

    async def broadcast_status(self, task_uuid: str, status: str, **kwargs):
        """Трансляция обновления статуса задачи"""
        with _ws_lock:
            connections = _ws_connections.get(task_uuid, []).copy()

        message = {
            "type": "status",
            "task_uuid": task_uuid,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs
        }

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"Ошибка отправки статуса через WebSocket: {e}")

    def register_websocket(self, task_uuid: str, websocket):
        """Регистрация WebSocket соединения"""
        with _ws_lock:
            if task_uuid not in _ws_connections:
                _ws_connections[task_uuid] = []
            # Избегаем повторной регистрации одного и того же соединения
            if websocket not in _ws_connections[task_uuid]:
                _ws_connections[task_uuid].append(websocket)
                # Запоминаем количество отправленных логов для избежания дублирования при отправке истории
                with _get_log_lock(task_uuid):
                    _ws_sent_index[task_uuid][id(websocket)] = len(_log_queues.get(task_uuid, []))
                logger.info(f"WebSocket соединение зарегистрировано: {task_uuid}")
            else:
                logger.warning(f"WebSocket соединение уже существует, пропуск повторной регистрации: {task_uuid}")

    def get_unsent_logs(self, task_uuid: str, websocket) -> List[str]:
        """Получение логов, не отправленных данному WebSocket"""
        with _ws_lock:
            ws_id = id(websocket)
            sent_count = _ws_sent_index.get(task_uuid, {}).get(ws_id, 0)

        with _get_log_lock(task_uuid):
            all_logs = _log_queues.get(task_uuid, [])
            unsent_logs = all_logs[sent_count:]
            # Обновляем индекс отправленных
            _ws_sent_index[task_uuid][ws_id] = len(all_logs)
            return unsent_logs

    def unregister_websocket(self, task_uuid: str, websocket):
        """Отмена регистрации WebSocket соединения"""
        with _ws_lock:
            if task_uuid in _ws_connections:
                try:
                    _ws_connections[task_uuid].remove(websocket)
                except ValueError:
                    pass
            # Очистка индекса отправленных
            if task_uuid in _ws_sent_index:
                _ws_sent_index[task_uuid].pop(id(websocket), None)
        logger.info(f"WebSocket соединение отменено: {task_uuid}")

    def get_logs(self, task_uuid: str) -> List[str]:
        """Получение всех логов задачи"""
        with _get_log_lock(task_uuid):
            return _log_queues.get(task_uuid, []).copy()

    def update_status(self, task_uuid: str, status: str, **kwargs):
        """Обновление статуса задачи"""
        if task_uuid not in _task_status:
            _task_status[task_uuid] = {}

        _task_status[task_uuid]["status"] = status
        _task_status[task_uuid].update(kwargs)

    def get_status(self, task_uuid: str) -> Optional[dict]:
        """Получение статуса задачи"""
        return _task_status.get(task_uuid)

    def cleanup_task(self, task_uuid: str):
        """Очистка данных задачи"""
        # Сохраняем очередь логов на некоторое время для последующих запросов
        # Очищаем только флаг отмены
        if task_uuid in _task_cancelled:
            del _task_cancelled[task_uuid]

    # ============== Управление пакетными задачами ==============

    def init_batch(self, batch_id: str, total: int):
        """Инициализация пакетной задачи"""
        _batch_status[batch_id] = {
            "status": "running",
            "total": total,
            "completed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "current_index": 0,
            "finished": False
        }
        logger.info(f"Пакетная задача {batch_id} инициализирована, всего: {total}")

    def add_batch_log(self, batch_id: str, log_message: str):
        """Добавление лога пакетной задачи и отправка"""
        # Сначала отправляем через WebSocket для обеспечения отправки в реальном времени
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_batch_log(batch_id, log_message),
                    self._loop
                )
            except Exception as e:
                logger.warning(f"Ошибка отправки пакетного лога через WebSocket: {e}")

        # После отправки добавляем в очередь
        with _get_batch_lock(batch_id):
            _batch_logs[batch_id].append(log_message)

    async def _broadcast_batch_log(self, batch_id: str, log_message: str):
        """Трансляция лога пакетной задачи"""
        key = f"batch_{batch_id}"
        with _ws_lock:
            connections = _ws_connections.get(key, []).copy()
            # Примечание: не обновляем sent_index здесь, чтобы избежать состояния гонки

        for ws in connections:
            try:
                await ws.send_json({
                    "type": "log",
                    "batch_id": batch_id,
                    "message": log_message,
                    "timestamp": datetime.utcnow().isoformat()
                })
                # После успешной отправки обновляем sent_index
                with _ws_lock:
                    ws_id = id(ws)
                    if key in _ws_sent_index and ws_id in _ws_sent_index[key]:
                        _ws_sent_index[key][ws_id] += 1
            except Exception as e:
                logger.warning(f"Ошибка отправки пакетного лога через WebSocket: {e}")

    def update_batch_status(self, batch_id: str, **kwargs):
        """Обновление статуса пакетной задачи"""
        if batch_id not in _batch_status:
            logger.warning(f"Пакетная задача {batch_id} не существует")
            return

        _batch_status[batch_id].update(kwargs)

        # Асинхронная трансляция обновления статуса
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_batch_status(batch_id),
                    self._loop
                )
            except Exception as e:
                logger.warning(f"Ошибка трансляции пакетного статуса: {e}")

    async def _broadcast_batch_status(self, batch_id: str):
        """Трансляция статуса пакетной задачи"""
        with _ws_lock:
            connections = _ws_connections.get(f"batch_{batch_id}", []).copy()

        status = _batch_status.get(batch_id, {})

        for ws in connections:
            try:
                await ws.send_json({
                    "type": "status",
                    "batch_id": batch_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    **status
                })
            except Exception as e:
                logger.warning(f"Ошибка отправки пакетного статуса через WebSocket: {e}")

    def get_batch_status(self, batch_id: str) -> Optional[dict]:
        """Получение статуса пакетной задачи"""
        return _batch_status.get(batch_id)

    def get_batch_logs(self, batch_id: str) -> List[str]:
        """Получение логов пакетной задачи"""
        with _get_batch_lock(batch_id):
            return _batch_logs.get(batch_id, []).copy()

    def is_batch_cancelled(self, batch_id: str) -> bool:
        """Проверка, отменена ли пакетная задача"""
        status = _batch_status.get(batch_id, {})
        return status.get("cancelled", False)

    def cancel_batch(self, batch_id: str):
        """Отмена пакетной задачи"""
        if batch_id in _batch_status:
            _batch_status[batch_id]["cancelled"] = True
            _batch_status[batch_id]["status"] = "cancelling"
            logger.info(f"Пакетная задача {batch_id} помечена как отменённая")

    def register_batch_websocket(self, batch_id: str, websocket):
        """Регистрация WebSocket соединения пакетной задачи"""
        key = f"batch_{batch_id}"
        with _ws_lock:
            if key not in _ws_connections:
                _ws_connections[key] = []
            # Избегаем повторной регистрации одного и того же соединения
            if websocket not in _ws_connections[key]:
                _ws_connections[key].append(websocket)
                # Запоминаем количество отправленных логов для избежания дублирования при отправке истории
                with _get_batch_lock(batch_id):
                    _ws_sent_index[key][id(websocket)] = len(_batch_logs.get(batch_id, []))
                logger.info(f"WebSocket соединение пакетной задачи зарегистрировано: {batch_id}")
            else:
                logger.warning(f"WebSocket соединение пакетной задачи уже существует, пропуск повторной регистрации: {batch_id}")

    def get_unsent_batch_logs(self, batch_id: str, websocket) -> List[str]:
        """Получение логов пакетной задачи, не отправленных данному WebSocket"""
        key = f"batch_{batch_id}"
        with _ws_lock:
            ws_id = id(websocket)
            sent_count = _ws_sent_index.get(key, {}).get(ws_id, 0)

        with _get_batch_lock(batch_id):
            all_logs = _batch_logs.get(batch_id, [])
            unsent_logs = all_logs[sent_count:]
            # Обновляем индекс отправленных
            _ws_sent_index[key][ws_id] = len(all_logs)
            return unsent_logs

    def unregister_batch_websocket(self, batch_id: str, websocket):
        """Отмена регистрации WebSocket соединения пакетной задачи"""
        key = f"batch_{batch_id}"
        with _ws_lock:
            if key in _ws_connections:
                try:
                    _ws_connections[key].remove(websocket)
                except ValueError:
                    pass
            # Очистка индекса отправленных
            if key in _ws_sent_index:
                _ws_sent_index[key].pop(id(websocket), None)
        logger.info(f"WebSocket соединение пакетной задачи отменено: {batch_id}")

    def create_log_callback(self, task_uuid: str, prefix: str = "", batch_id: str = "") -> Callable[[str], None]:
        """Создание функции обратного вызова для логов, с возможностью добавления префикса номера задачи и одновременной отправки в канал пакетной задачи"""
        def callback(msg: str):
            full_msg = f"{prefix} {msg}" if prefix else msg
            self.add_log(task_uuid, full_msg)
            # Если принадлежит пакетной задаче, синхронно отправляем в канал batch, чтобы фронтенд видел подробные шаги в смешанных логах
            if batch_id:
                self.add_batch_log(batch_id, full_msg)
        return callback

    def create_check_cancelled_callback(self, task_uuid: str) -> Callable[[], bool]:
        """Создание функции обратного вызова для проверки отмены"""
        def callback() -> bool:
            return self.is_cancelled(task_uuid)
        return callback


# Глобальный экземпляр
task_manager = TaskManager()
