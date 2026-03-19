"""
Background Scheduler для мониторинга рабочих областей
Запускается при старте приложения, работает в фоне
"""

import asyncio
import logging
from typing import Optional, List, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkspaceScheduler:
    """Фоновый планировщик мониторинга workspace"""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._log_buffer: List[dict] = []  # For WebSocket consumers
        self._max_log_buffer = 500
        self._websockets = []  # Connected WebSocket clients
        self._cycle_count = 0
        self._last_cycle_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_status(self) -> dict:
        """Get scheduler status for API"""
        return {
            "running": self.is_running,
            "cycle_count": self._cycle_count,
            "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            "last_error": self._last_error,
            "connected_clients": len(self._websockets),
        }

    def get_logs(self, since: int = 0) -> List[dict]:
        """Get buffered logs, optionally since index"""
        return self._log_buffer[since:]

    async def _broadcast(self, message: str, level: str = "info"):
        """Send log to all connected WebSocket clients and buffer"""
        entry = {
            "type": "workspace_log",
            "message": message,
            "level": level,
            "timestamp": datetime.utcnow().isoformat(),
            "index": len(self._log_buffer),
        }
        self._log_buffer.append(entry)
        if len(self._log_buffer) > self._max_log_buffer:
            self._log_buffer = self._log_buffer[-self._max_log_buffer:]

        # Broadcast to connected WebSocket clients
        dead = []
        for ws in self._websockets:
            try:
                await ws.send_json(entry)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._websockets.remove(ws)

    def register_websocket(self, ws):
        if ws not in self._websockets:
            self._websockets.append(ws)

    def unregister_websocket(self, ws):
        if ws in self._websockets:
            self._websockets.remove(ws)

    async def start(self):
        """Start the monitoring loop"""
        if self.is_running:
            logger.warning("Scheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Workspace scheduler started")

    async def stop(self):
        """Stop the monitoring loop"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Workspace scheduler stopped")

    async def _run_loop(self):
        """Main monitoring loop"""
        await self._broadcast("🚀 Мониторинг workspace запущен")

        while self._running:
            try:
                from ..config.settings import get_settings
                settings = get_settings()

                if not settings.workspace_monitoring_enabled:
                    await self._broadcast("⏸ Мониторинг отключён в настройках, ожидание...")
                    await asyncio.sleep(30)  # Check again in 30 sec
                    continue

                interval = settings.workspace_monitoring_interval

                await self._broadcast(f"🔄 Запуск цикла мониторинга #{self._cycle_count + 1}")

                # Run the sync monitoring cycle in a thread pool
                from .workspace_manager import WorkspaceManager
                manager = WorkspaceManager()

                # Add broadcast callback
                def log_callback(msg, lvl="info"):
                    asyncio.get_event_loop().call_soon_threadsafe(
                        asyncio.ensure_future,
                        self._broadcast(msg, lvl)
                    )
                manager.add_log_callback(log_callback)

                # Run blocking I/O in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, manager.run_monitoring_cycle)

                self._cycle_count += 1
                self._last_cycle_at = datetime.utcnow()
                self._last_error = None

                await self._broadcast(
                    f"✅ Цикл #{self._cycle_count} завершён. "
                    f"Результат: {result.get('workspaces_checked', 0)} workspace проверено"
                )

                await self._broadcast(f"⏳ Следующий цикл через {interval} сек...")
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._last_error = str(e)
                logger.exception("Scheduler cycle error")
                await self._broadcast(f"❌ Ошибка цикла: {e}", "error")
                await asyncio.sleep(60)  # Wait 1 min on error

        await self._broadcast("🛑 Мониторинг workspace остановлен")


# Singleton instance
workspace_scheduler = WorkspaceScheduler()
