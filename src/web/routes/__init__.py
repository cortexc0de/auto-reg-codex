"""
Модуль маршрутов API
"""

from fastapi import APIRouter

from .accounts import router as accounts_router
from .registration import router as registration_router
from .settings import router as settings_router
from .email_services import router as email_services_router
from .payment import router as payment_router
from .workspace import router as workspace_router

api_router = APIRouter()

# Регистрация маршрутов модулей
api_router.include_router(accounts_router, prefix="/accounts", tags=["accounts"])
api_router.include_router(registration_router, prefix="/registration", tags=["registration"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(email_services_router, prefix="/email-services", tags=["email-services"])
api_router.include_router(payment_router, prefix="/payment", tags=["payment"])
api_router.include_router(workspace_router, prefix="/workspaces", tags=["workspaces"])
