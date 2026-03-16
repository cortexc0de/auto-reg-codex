"""
Главный файл приложения FastAPI
Легковесный Web UI, поддержка регистрации, управления аккаунтами, настроек
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from ..config.settings import get_settings
from .routes import api_router
from .routes.websocket import router as ws_router
from .task_manager import task_manager

logger = logging.getLogger(__name__)

# Получение корневой директории проекта
# После упаковки PyInstaller статические ресурсы находятся в sys._MEIPASS, при разработке — в корне исходников
if getattr(sys, 'frozen', False):
    _RESOURCE_ROOT = Path(sys._MEIPASS)
else:
    _RESOURCE_ROOT = Path(__file__).parent.parent.parent

# Директории статических файлов и шаблонов
STATIC_DIR = _RESOURCE_ROOT / "static"
TEMPLATES_DIR = _RESOURCE_ROOT / "templates"


def create_app() -> FastAPI:
    """Создание экземпляра приложения FastAPI"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Система автоматической регистрации OpenAI/Codex CLI Web UI",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # Промежуточное ПО CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Монтирование статических файлов
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
        logger.info(f"Директория статических файлов: {STATIC_DIR}")
    else:
        # Создание директории статических файлов
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
        logger.info(f"Создана директория статических файлов: {STATIC_DIR}")

    # Создание директории шаблонов
    if not TEMPLATES_DIR.exists():
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Создана директория шаблонов: {TEMPLATES_DIR}")

    # Регистрация маршрутов API
    app.include_router(api_router, prefix="/api")

    # Регистрация маршрутов WebSocket
    app.include_router(ws_router, prefix="/api")

    # Шаблонизатор
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """Главная страница — страница регистрации"""
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/accounts", response_class=HTMLResponse)
    async def accounts_page(request: Request):
        """Страница управления аккаунтами"""
        return templates.TemplateResponse("accounts.html", {"request": request})

    @app.get("/email-services", response_class=HTMLResponse)
    async def email_services_page(request: Request):
        """Страница управления почтовыми сервисами"""
        return templates.TemplateResponse("email_services.html", {"request": request})

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        """Страница настроек"""
        return templates.TemplateResponse("settings.html", {"request": request})

    @app.get("/payment", response_class=HTMLResponse)
    async def payment_page(request: Request):
        """Страница оплаты"""
        return templates.TemplateResponse("payment.html", {"request": request})

    @app.on_event("startup")
    async def startup_event():
        """Событие запуска приложения"""
        import asyncio

        # Установка цикла событий для TaskManager
        loop = asyncio.get_event_loop()
        task_manager.set_loop(loop)

        logger.info("=" * 50)
        logger.info(f"{settings.app_name} v{settings.app_version} запускается...")
        logger.info(f"Режим отладки: {settings.debug}")
        logger.info(f"База данных: {settings.database_url}")
        logger.info("=" * 50)

    @app.on_event("shutdown")
    async def shutdown_event():
        """Событие завершения приложения"""
        logger.info("Приложение завершено")

    return app


# Создание глобального экземпляра приложения
app = create_app()
