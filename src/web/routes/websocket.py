"""
Маршруты WebSocket
Обеспечивают отправку логов в реальном времени и обновление статуса задач
"""

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..task_manager import task_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/task/{task_uuid}")
async def task_websocket(websocket: WebSocket, task_uuid: str):
    """
    WebSocket логов задачи

    Формат сообщений:
    - Сервер отправляет: {"type": "log", "task_uuid": "xxx", "message": "...", "timestamp": "..."}
    - Сервер отправляет: {"type": "status", "task_uuid": "xxx", "status": "running|completed|failed|cancelled", ...}
    - Клиент отправляет: {"type": "ping"} - пульс
    - Клиент отправляет: {"type": "cancel"} - отмена задачи
    """
    await websocket.accept()

    # Регистрация соединения (запоминает текущее количество логов для избежания дублирования исторических логов)
    task_manager.register_websocket(task_uuid, websocket)
    logger.info(f"WebSocket соединение установлено: {task_uuid}")

    try:
        # Отправка текущего статуса
        status = task_manager.get_status(task_uuid)
        if status:
            await websocket.send_json({
                "type": "status",
                "task_uuid": task_uuid,
                **status
            })

        # Отправка исторических логов (только логи, существовавшие при регистрации, для избежания дублирования с отправкой в реальном времени)
        history_logs = task_manager.get_unsent_logs(task_uuid, websocket)
        for log in history_logs:
            await websocket.send_json({
                "type": "log",
                "task_uuid": task_uuid,
                "message": log
            })

        # Поддержание соединения, ожидание сообщений клиента
        while True:
            try:
                # Использование wait_for для таймаута, но не для разрыва соединения
                # а для отправки проверки пульса
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0  # таймаут 30 секунд
                )

                # Обработка пульса
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

                # Обработка запроса отмены
                elif data.get("type") == "cancel":
                    task_manager.cancel_task(task_uuid)
                    await websocket.send_json({
                        "type": "status",
                        "task_uuid": task_uuid,
                        "status": "cancelling",
                        "message": "Запрос на отмену отправлен"
                    })

            except asyncio.TimeoutError:
                # Таймаут, отправка проверки пульса
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    # Ошибка отправки, возможно соединение разорвано
                    logger.info(f"Проверка пульса WebSocket не удалась: {task_uuid}")
                    break

    except WebSocketDisconnect:
        logger.info(f"WebSocket отключён: {task_uuid}")

    except Exception as e:
        logger.error(f"Ошибка WebSocket: {e}")

    finally:
        task_manager.unregister_websocket(task_uuid, websocket)


@router.websocket("/ws/batch/{batch_id}")
async def batch_websocket(websocket: WebSocket, batch_id: str):
    """
    WebSocket пакетной задачи

    Используется для обновления статуса пакетных задач регистрации в реальном времени

    Формат сообщений:
    - Сервер отправляет: {"type": "log", "batch_id": "xxx", "message": "...", "timestamp": "..."}
    - Сервер отправляет: {"type": "status", "batch_id": "xxx", "status": "running|completed|cancelled", ...}
    - Клиент отправляет: {"type": "ping"} - пульс
    - Клиент отправляет: {"type": "cancel"} - отмена пакетной задачи
    """
    await websocket.accept()

    # Регистрация соединения (запоминает текущее количество логов для избежания дублирования исторических логов)
    task_manager.register_batch_websocket(batch_id, websocket)
    logger.info(f"WebSocket пакетной задачи соединение установлено: {batch_id}")

    try:
        # Отправка текущего статуса
        status = task_manager.get_batch_status(batch_id)
        if status:
            await websocket.send_json({
                "type": "status",
                "batch_id": batch_id,
                **status
            })

        # Отправка исторических логов (только логи, существовавшие при регистрации, для избежания дублирования с отправкой в реальном времени)
        history_logs = task_manager.get_unsent_batch_logs(batch_id, websocket)
        for log in history_logs:
            await websocket.send_json({
                "type": "log",
                "batch_id": batch_id,
                "message": log
            })

        # Поддержание соединения, ожидание сообщений клиента
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0
                )

                # Обработка пульса
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

                # Обработка запроса отмены
                elif data.get("type") == "cancel":
                    task_manager.cancel_batch(batch_id)
                    await websocket.send_json({
                        "type": "status",
                        "batch_id": batch_id,
                        "status": "cancelling",
                        "message": "Запрос на отмену отправлен"
                    })

            except asyncio.TimeoutError:
                # Таймаут, отправка проверки пульса
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    logger.info(f"Проверка пульса WebSocket пакетной задачи не удалась: {batch_id}")
                    break

    except WebSocketDisconnect:
        logger.info(f"WebSocket пакетной задачи отключён: {batch_id}")

    except Exception as e:
        logger.error(f"Ошибка WebSocket пакетной задачи: {e}")

    finally:
        task_manager.unregister_batch_websocket(batch_id, websocket)
