"""
Движок процесса регистрации
Извлечён и рефакторен из main.py
"""

import re
import json
import time
import logging
import secrets
import string
from typing import Optional, Dict, Any, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime

from curl_cffi import requests as cffi_requests

from .oauth import OAuthManager, OAuthStart
from .http_client import OpenAIHTTPClient, HTTPClientError
from ..services import EmailServiceFactory, BaseEmailService, EmailServiceType
from ..database import crud
from ..database.session import get_db
from ..config.constants import (
    OPENAI_API_ENDPOINTS,
    OPENAI_PAGE_TYPES,
    generate_random_user_info,
    OTP_CODE_PATTERN,
    DEFAULT_PASSWORD_LENGTH,
    PASSWORD_CHARSET,
    AccountStatus,
    TaskStatus,
)
from ..config.settings import get_settings


logger = logging.getLogger(__name__)


@dataclass
class RegistrationResult:
    """Результат регистрации"""
    success: bool
    email: str = ""
    password: str = ""  # Пароль регистрации
    account_id: str = ""
    workspace_id: str = ""
    access_token: str = ""
    refresh_token: str = ""
    id_token: str = ""
    session_token: str = ""  # Токен сессии
    error_message: str = ""
    logs: list = None
    metadata: dict = None
    source: str = "register"  # 'register' или 'login', источник аккаунта

    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        return {
            "success": self.success,
            "email": self.email,
            "password": self.password,
            "account_id": self.account_id,
            "workspace_id": self.workspace_id,
            "access_token": self.access_token[:20] + "..." if self.access_token else "",
            "refresh_token": self.refresh_token[:20] + "..." if self.refresh_token else "",
            "id_token": self.id_token[:20] + "..." if self.id_token else "",
            "session_token": self.session_token[:20] + "..." if self.session_token else "",
            "error_message": self.error_message,
            "logs": self.logs or [],
            "metadata": self.metadata or {},
            "source": self.source,
        }


@dataclass
class SignupFormResult:
    """Результат отправки формы регистрации"""
    success: bool
    page_type: str = ""  # Поле page.type в ответе
    is_existing_account: bool = False  # Существующий аккаунт
    response_data: Dict[str, Any] = None  # Полные данные ответа
    error_message: str = ""


class RegistrationEngine:
    """
    Движок регистрации
    Координирует почтовый сервис, OAuth процесс и вызовы OpenAI API
    """

    def __init__(
        self,
        email_service: BaseEmailService,
        proxy_url: Optional[str] = None,
        callback_logger: Optional[Callable[[str], None]] = None,
        task_uuid: Optional[str] = None
    ):
        """
        Инициализация движка регистрации

        Args:
            email_service: Экземпляр почтового сервиса
            proxy_url: URL прокси
            callback_logger: Callback-функция логирования
            task_uuid: UUID задачи (для записи в БД)
        """
        self.email_service = email_service
        self.proxy_url = proxy_url
        self.callback_logger = callback_logger or (lambda msg: logger.info(msg))
        self.task_uuid = task_uuid

        # Создание HTTP клиента
        self.http_client = OpenAIHTTPClient(proxy_url=proxy_url)

        # Создание OAuth менеджера
        settings = get_settings()
        self.oauth_manager = OAuthManager(
            client_id=settings.openai_client_id,
            auth_url=settings.openai_auth_url,
            token_url=settings.openai_token_url,
            redirect_uri=settings.openai_redirect_uri,
            scope=settings.openai_scope,
            proxy_url=proxy_url  # Передача конфигурации прокси
        )

        # Переменные состояния
        self.email: Optional[str] = None
        self.password: Optional[str] = None  # Пароль регистрации
        self.email_info: Optional[Dict[str, Any]] = None
        self.oauth_start: Optional[OAuthStart] = None
        self.session: Optional[cffi_requests.Session] = None
        self.session_token: Optional[str] = None  # Токен сессии
        self.logs: list = []
        self._otp_sent_at: Optional[float] = None  # Временная метка отправки OTP
        self._is_existing_account: bool = False  # Существующий аккаунт (для автоматической авторизации)
        self._create_account_response: Dict[str, Any] = {}  # Ответ create_account

    def _log(self, message: str, level: str = "info"):
        """Запись лога"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"

        # Добавление в список логов
        self.logs.append(log_message)

        # Вызов callback
        if self.callback_logger:
            self.callback_logger(log_message)

        # Запись в БД (если есть связанная задача)
        if self.task_uuid:
            try:
                with get_db() as db:
                    crud.append_task_log(db, self.task_uuid, log_message)
            except Exception as e:
                logger.warning(f"Ошибка записи лога задачи: {e}")

        # Запись в систему логирования по уровню
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def _generate_password(self, length: int = DEFAULT_PASSWORD_LENGTH) -> str:
        """Генерация случайного пароля"""
        return ''.join(secrets.choice(PASSWORD_CHARSET) for _ in range(length))

    def _check_ip_location(self) -> Tuple[bool, Optional[str]]:
        """Проверка геолокации IP"""
        try:
            return self.http_client.check_ip_location()
        except Exception as e:
            self._log(f"Ошибка проверки геолокации IP: {e}", "error")
            return False, None

    def _create_email(self) -> bool:
        """Создание почтового ящика"""
        try:
            self._log(f"Создание почтового ящика {self.email_service.service_type.value}...")
            self.email_info = self.email_service.create_email()

            if not self.email_info or "email" not in self.email_info:
                self._log("Ошибка создания почтового ящика: Неполная информация в ответе", "error")
                return False

            self.email = self.email_info["email"]
            self._log(f"Почтовый ящик создан: {self.email}")
            return True

        except Exception as e:
            self._log(f"Ошибка создания почтового ящика: {e}", "error")
            return False

    def _start_oauth(self) -> bool:
        """Начало OAuth авторизации"""
        try:
            self._log("Начало OAuth авторизации...")
            self.oauth_start = self.oauth_manager.start_oauth()
            self._log(f"OAuth URL сгенерирован: {self.oauth_start.auth_url[:80]}...")
            return True
        except Exception as e:
            self._log(f"Ошибка генерации OAuth URL: {e}", "error")
            return False

    def _init_session(self) -> bool:
        """Инициализация сессии"""
        try:
            self.session = self.http_client.session
            return True
        except Exception as e:
            self._log(f"Ошибка инициализации сессии: {e}", "error")
            return False

    def _get_device_id(self) -> Optional[str]:
        """Получение Device ID"""
        try:
            if not self.oauth_start:
                return None

            response = self.session.get(
                self.oauth_start.auth_url,
                timeout=15
            )
            did = self.session.cookies.get("oai-did")
            self._log(f"Device ID: {did}")
            return did

        except Exception as e:
            self._log(f"Ошибка получения Device ID: {e}", "error")
            return None

    def _check_sentinel(self, did: str) -> Optional[str]:
        """Проверка Sentinel"""
        try:
            sen_req_body = f'{{"p":"","id":"{did}","flow":"authorize_continue"}}'

            response = self.http_client.post(
                OPENAI_API_ENDPOINTS["sentinel"],
                headers={
                    "origin": "https://sentinel.openai.com",
                    "referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html?sv=20260219f9f6",
                    "content-type": "text/plain;charset=UTF-8",
                },
                data=sen_req_body,
            )

            if response.status_code == 200:
                sen_token = response.json().get("token")
                self._log(f"Sentinel token получен")
                return sen_token
            else:
                self._log(f"Ошибка проверки Sentinel: {response.status_code}", "warning")
                return None

        except Exception as e:
            self._log(f"Исключение проверки Sentinel: {e}", "warning")
            return None

    def _submit_signup_form(self, did: str, sen_token: Optional[str]) -> SignupFormResult:
        """
        Отправка формы регистрации

        Returns:
            SignupFormResult: Результат отправки с определением статуса аккаунта
        """
        try:
            signup_body = f'{{"username":{{"value":"{self.email}","kind":"email"}},"screen_hint":"signup"}}'

            headers = {
                "referer": "https://auth.openai.com/create-account",
                "accept": "application/json",
                "content-type": "application/json",
            }

            if sen_token:
                sentinel = f'{{"p": "", "t": "", "c": "{sen_token}", "id": "{did}", "flow": "authorize_continue"}}'
                headers["openai-sentinel-token"] = sentinel

            response = self.session.post(
                OPENAI_API_ENDPOINTS["signup"],
                headers=headers,
                data=signup_body,
            )

            self._log(f"Статус отправки формы: {response.status_code}")

            if response.status_code != 200:
                return SignupFormResult(
                    success=False,
                    error_message=f"HTTP {response.status_code}: {response.text[:200]}"
                )

            # Парсинг ответа для определения статуса аккаунта
            try:
                response_data = response.json()
                page_type = response_data.get("page", {}).get("type", "")
                self._log(f"Тип страницы ответа: {page_type}")

                # Проверка существующего аккаунта
                is_existing = page_type == OPENAI_PAGE_TYPES["EMAIL_OTP_VERIFICATION"]

                if is_existing:
                    self._log(f"Обнаружен существующий аккаунт, переход к авторизации")
                    self._is_existing_account = True

                return SignupFormResult(
                    success=True,
                    page_type=page_type,
                    is_existing_account=is_existing,
                    response_data=response_data
                )

            except Exception as parse_error:
                self._log(f"Ошибка парсинга ответа: {parse_error}", "warning")
                # Невозможно распарсить, считаем успешным
                return SignupFormResult(success=True)

        except Exception as e:
            self._log(f"Ошибка отправки формы: {e}", "error")
            return SignupFormResult(success=False, error_message=str(e))

    def _register_password(self) -> Tuple[bool, Optional[str]]:
        """Регистрация пароля"""
        try:
            # Генерация пароля
            password = self._generate_password()
            self.password = password  # Сохранение пароля в переменную экземпляра
            self._log(f"Сгенерирован пароль: {password}")

            # Отправка пароля для регистрации
            register_body = json.dumps({
                "password": password,
                "username": self.email
            })

            response = self.session.post(
                OPENAI_API_ENDPOINTS["register"],
                headers={
                    "referer": "https://auth.openai.com/create-account/password",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                data=register_body,
            )

            self._log(f"Статус отправки пароля: {response.status_code}")

            if response.status_code != 200:
                error_text = response.text[:500]
                self._log(f"Ошибка регистрации пароля: {error_text}", "warning")

                # Парсинг ошибки, проверка зарегистрирован ли email
                try:
                    error_json = response.json()
                    error_msg = error_json.get("error", {}).get("message", "")
                    error_code = error_json.get("error", {}).get("code", "")

                    # Обнаружение ситуации, когда email уже зарегистрирован
                    if "already" in error_msg.lower() or "exists" in error_msg.lower() or error_code == "user_exists":
                        self._log(f"Email {self.email} возможно уже зарегистрирован в OpenAI", "error")
                        # Пометка email как зарегистрированного
                        self._mark_email_as_registered()
                except Exception:
                    pass

                return False, None

            return True, password

        except Exception as e:
            self._log(f"Ошибка регистрации пароля: {e}", "error")
            return False, None

    def _mark_email_as_registered(self):
        """Пометка email как зарегистрированного (для предотвращения повторных попыток)"""
        try:
            with get_db() as db:
                # Проверка существования записи для данного email
                existing = crud.get_account_by_email(db, self.email)
                if not existing:
                    # Создание записи о неудаче, пометка email как зарегистрированного
                    crud.create_account(
                        db,
                        email=self.email,
                        password="",  # Пустой пароль означает неуспешную регистрацию
                        email_service=self.email_service.service_type.value,
                        email_service_id=self.email_info.get("service_id") if self.email_info else None,
                        status="failed",
                        extra_data={"register_failed_reason": "email_already_registered_on_openai"}
                    )
                    self._log(f"Email {self.email} помечен как зарегистрированный в БД")
        except Exception as e:
            logger.warning(f"Ошибка пометки email: {e}")

    def _send_verification_code(self) -> bool:
        """Отправка кода подтверждения"""
        try:
            # Запись временной метки отправки
            self._otp_sent_at = time.time()

            response = self.session.get(
                OPENAI_API_ENDPOINTS["send_otp"],
                headers={
                    "referer": "https://auth.openai.com/create-account/password",
                    "accept": "application/json",
                },
            )

            self._log(f"Статус отправки кода: {response.status_code}")
            return response.status_code == 200

        except Exception as e:
            self._log(f"Ошибка отправки кода: {e}", "error")
            return False

    def _get_verification_code(self) -> Optional[str]:
        """Получение кода подтверждения"""
        try:
            self._log(f"Ожидание кода подтверждения для {self.email}...")

            email_id = self.email_info.get("service_id") if self.email_info else None
            code = self.email_service.get_verification_code(
                email=self.email,
                email_id=email_id,
                timeout=120,
                pattern=OTP_CODE_PATTERN,
                otp_sent_at=self._otp_sent_at,
            )

            if code:
                self._log(f"Код подтверждения получен: {code}")
                return code
            else:
                self._log("Таймаут ожидания кода", "error")
                return None

        except Exception as e:
            self._log(f"Ошибка получения кода: {e}", "error")
            return None

    def _validate_verification_code(self, code: str) -> bool:
        """Проверка кода подтверждения"""
        try:
            code_body = f'{{"code":"{code}"}}'

            response = self.session.post(
                OPENAI_API_ENDPOINTS["validate_otp"],
                headers={
                    "referer": "https://auth.openai.com/email-verification",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                data=code_body,
            )

            self._log(f"Статус проверки кода: {response.status_code}")
            return response.status_code == 200

        except Exception as e:
            self._log(f"Ошибка проверки кода: {e}", "error")
            return False

    def _create_user_account(self) -> bool:
        """Создание аккаунта"""
        try:
            user_info = generate_random_user_info()
            self._log(f"Сгенерирована информация: {user_info['name']}, дата рождения: {user_info['birthdate']}")
            create_account_body = json.dumps(user_info)

            response = self.session.post(
                OPENAI_API_ENDPOINTS["create_account"],
                headers={
                    "referer": "https://auth.openai.com/about-you",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                data=create_account_body,
            )

            self._log(f"Статус создания аккаунта: {response.status_code}")

            if response.status_code != 200:
                self._log(f"Ошибка создания аккаунта: {response.text[:200]}", "warning")
                return False

            # Сохраняем ответ — может содержать continue_url или workspace info
            try:
                self._create_account_response = response.json()
                self._log(f"Ответ create_account: {str(self._create_account_response)[:200]}")
            except Exception:
                self._create_account_response = {}

            return True

        except Exception as e:
            self._log(f"Ошибка создания аккаунта: {e}", "error")
            return False

    def _get_workspace_id(self) -> Optional[str]:
        """Получение Workspace ID из cookie или через API"""
        import base64
        import json as json_module

        # Метод 1: из cookie oai-client-auth-session
        auth_cookie = self.session.cookies.get("oai-client-auth-session")
        if auth_cookie:
            try:
                # Пробуем все сегменты JWT (payload обычно [1], но бывает [0])
                segments = auth_cookie.split(".")
                for idx in (1, 0, 2):
                    if idx >= len(segments):
                        continue
                    try:
                        payload = segments[idx]
                        pad = "=" * ((4 - (len(payload) % 4)) % 4)
                        decoded = base64.urlsafe_b64decode((payload + pad).encode("ascii"))
                        auth_json = json_module.loads(decoded.decode("utf-8"))

                        # Вариант 1: поле "workspaces"
                        workspaces = auth_json.get("workspaces") or []
                        if workspaces:
                            wid = str((workspaces[0] or {}).get("id") or "").strip()
                            if wid:
                                self._log(f"Workspace ID (cookie/workspaces): {wid}")
                                return wid

                        # Вариант 2: поле "workspace_id" напрямую
                        wid = str(auth_json.get("workspace_id") or "").strip()
                        if wid:
                            self._log(f"Workspace ID (cookie/workspace_id): {wid}")
                            return wid

                        # Вариант 3: вложенный auth-объект OpenAI
                        auth_data = auth_json.get("https://api.openai.com/auth") or {}
                        wid = str(auth_data.get("chatgpt_account_id") or "").strip()
                        if wid:
                            self._log(f"Workspace ID (cookie/account_id): {wid}")
                            return wid

                    except Exception:
                        continue

                self._log("Cookie есть, но workspace_id не найден — пробую API", "warning")
            except Exception as e:
                self._log(f"Ошибка парсинга cookie: {e}", "warning")
        else:
            self._log("Cookie oai-client-auth-session отсутствует — пробую API", "warning")

        # Метод 2: через API workspace/list
        try:
            response = self.session.get(
                "https://auth.openai.com/api/accounts/workspace/list",
                headers={"content-type": "application/json"},
                timeout=15,
            )
            if response.status_code == 200:
                data = response.json()
                workspaces = data if isinstance(data, list) else (data.get("workspaces") or data.get("items") or [])
                if workspaces:
                    wid = str((workspaces[0] if isinstance(workspaces[0], str) else (workspaces[0] or {}).get("id", ""))).strip()
                    if wid:
                        self._log(f"Workspace ID (API/list): {wid}")
                        return wid
                self._log(f"API workspace/list вернул: {str(data)[:200]}", "warning")
        except Exception as e:
            self._log(f"Ошибка API workspace/list: {e}", "warning")

        # Метод 3: через API accounts/check
        try:
            response = self.session.get(
                "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27",
                headers={"content-type": "application/json"},
                timeout=15,
            )
            if response.status_code == 200:
                data = response.json()
                accounts = data.get("accounts") or {}
                for account_id, info in accounts.items():
                    if account_id and account_id != "default":
                        self._log(f"Workspace ID (API/accounts-check): {account_id}")
                        return account_id
                self._log(f"API accounts/check вернул: {str(data)[:200]}", "warning")
        except Exception as e:
            self._log(f"Ошибка API accounts/check: {e}", "warning")

        self._log("Не удалось получить Workspace ID ни одним способом", "error")
        return None

    def _select_workspace(self, workspace_id: str) -> Optional[str]:
        """Выбор Workspace"""
        try:
            select_body = f'{{"workspace_id":"{workspace_id}"}}'

            response = self.session.post(
                OPENAI_API_ENDPOINTS["select_workspace"],
                headers={
                    "referer": "https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
                    "content-type": "application/json",
                },
                data=select_body,
            )

            if response.status_code != 200:
                self._log(f"Ошибка выбора workspace: {response.status_code}", "error")
                self._log(f"Ответ: {response.text[:200]}", "warning")
                return None

            continue_url = str((response.json() or {}).get("continue_url") or "").strip()
            if not continue_url:
                self._log("Ответ workspace/select не содержит continue_url", "error")
                return None

            self._log(f"Continue URL: {continue_url[:100]}...")
            return continue_url

        except Exception as e:
            self._log(f"Ошибка выбора Workspace: {e}", "error")
            return None

    def _follow_redirects(self, start_url: str) -> Optional[str]:
        """Следование по цепочке редиректов"""
        try:
            current_url = start_url
            max_redirects = 6

            for i in range(max_redirects):
                self._log(f"Редирект {i+1}/{max_redirects}: {current_url[:100]}...")

                response = self.session.get(
                    current_url,
                    allow_redirects=False,
                    timeout=15
                )

                location = response.headers.get("Location") or ""

                # Если не статус редиректа, остановка
                if response.status_code not in [301, 302, 303, 307, 308]:
                    self._log(f"Не статус редиректа: {response.status_code}")
                    break

                if not location:
                    self._log("В ответе редиректа отсутствует заголовок Location")
                    break

                # Построение следующего URL
                import urllib.parse
                next_url = urllib.parse.urljoin(current_url, location)

                # Проверка наличия callback параметров
                if "code=" in next_url and "state=" in next_url:
                    self._log(f"Найден URL обратного вызова: {next_url[:100]}...")
                    return next_url

                current_url = next_url

            self._log("Не удалось найти callback URL в цепочке редиректов", "error")
            return None

        except Exception as e:
            self._log(f"Ошибка следования по редиректам: {e}", "error")
            return None

    def _handle_oauth_callback(self, callback_url: str) -> Optional[Dict[str, Any]]:
        """Обработка OAuth callback"""
        try:
            if not self.oauth_start:
                self._log("OAuth процесс не инициализирован", "error")
                return None

            self._log("Обработка OAuth callback...")
            token_info = self.oauth_manager.handle_callback(
                callback_url=callback_url,
                expected_state=self.oauth_start.state,
                code_verifier=self.oauth_start.code_verifier
            )

            self._log("OAuth авторизация успешна")
            return token_info

        except Exception as e:
            self._log(f"Ошибка обработки OAuth callback: {e}", "error")
            return None

    def run(self) -> RegistrationResult:
        """
        Выполнение полного процесса регистрации

        Поддержка автоматической авторизации существующих аккаунтов:
        - При обнаружении зарегистрированного email автоматически переключается на авторизацию
        - Для существующих аккаунтов пропускается: установка пароля, отправка кода, создание аккаунта
        - Общие шаги: получение кода, проверка кода, Workspace и OAuth callback

        Returns:
            RegistrationResult: Результат регистрации
        """
        result = RegistrationResult(success=False, logs=self.logs)

        try:
            self._log("=" * 60)
            self._log("Начало процесса регистрации")
            self._log("=" * 60)

            # 1. Проверка геолокации IP
            self._log("1. Проверка геолокации IP...")
            ip_ok, location = self._check_ip_location()
            if not ip_ok:
                result.error_message = f"Геолокация IP не поддерживается: {location}"
                self._log(f"Ошибка проверки IP: {location}", "error")
                return result

            self._log(f"IP геолокация: {location}")

            # 2. Создание почтового ящика
            self._log("2. Создание почтового ящика...")
            if not self._create_email():
                result.error_message = "Ошибка создания почтового ящика"
                return result

            result.email = self.email

            # 3. Инициализация сессии
            self._log("3. Инициализация сессии...")
            if not self._init_session():
                result.error_message = "Ошибка инициализации сессии"
                return result

            # 4. Начало OAuth авторизации
            self._log("4. Начало OAuth авторизации...")
            if not self._start_oauth():
                result.error_message = "Ошибка начала OAuth авторизации"
                return result

            # 5. Получение Device ID
            self._log("5. Получение Device ID...")
            did = self._get_device_id()
            if not did:
                result.error_message = "Ошибка получения Device ID"
                return result

            # 6. Проверка Sentinel
            self._log("6. Проверка Sentinel...")
            sen_token = self._check_sentinel(did)
            if sen_token:
                self._log("Sentinel проверка пройдена")
            else:
                self._log("Sentinel не пройден или отключён", "warning")

            # 7. Отправка формы регистрации + определение статуса аккаунта
            self._log("7. Отправка формы регистрации...")
            signup_result = self._submit_signup_form(did, sen_token)
            if not signup_result.success:
                result.error_message = f"Ошибка отправки формы: {signup_result.error_message}"
                return result

            # 8. [Существующий аккаунт - пропуск] Регистрация пароля
            if self._is_existing_account:
                self._log("8. [Существующий аккаунт] Пропуск установки пароля, OTP отправлен автоматически")
            else:
                self._log("8. Регистрация пароля...")
                password_ok, password = self._register_password()
                if not password_ok:
                    result.error_message = "Ошибка регистрации пароля"
                    return result

            # 9. [Существующий аккаунт - пропуск] Отправка кода подтверждения
            if self._is_existing_account:
                self._log("9. [Существующий аккаунт] Пропуск отправки кода, используется автоматический OTP")
                # OTP для существующего аккаунта уже отправлен при подаче формы, записываем метку времени
                self._otp_sent_at = time.time()
            else:
                self._log("9. Отправка кода подтверждения...")
                if not self._send_verification_code():
                    result.error_message = "Ошибка отправки кода"
                    return result

            # 10. Получение кода подтверждения
            self._log("10. Ожидание кода подтверждения...")
            code = self._get_verification_code()
            if not code:
                result.error_message = "Ошибка получения кода"
                return result

            # 11. Проверка кода подтверждения
            self._log("11. Проверка кода подтверждения...")
            if not self._validate_verification_code(code):
                result.error_message = "Ошибка проверки кода"
                return result

            # 12. [Существующий аккаунт - пропуск] Создание аккаунта
            if self._is_existing_account:
                self._log("12. [Существующий аккаунт] Пропуск создания аккаунта")
            else:
                self._log("12. Создание аккаунта...")
                if not self._create_user_account():
                    result.error_message = "Ошибка создания аккаунта"
                    return result

            # 13. Получение Workspace ID + выбор + OAuth
            # Проверяем, вернул ли create_account continue_url напрямую
            continue_url = str(self._create_account_response.get("continue_url") or "").strip()

            if continue_url:
                self._log("13. continue_url получен из ответа create_account")
            else:
                # Пробуем классический путь: workspace → select → continue_url
                self._log("13. Получение Workspace ID...")
                workspace_id = self._get_workspace_id()
                if workspace_id:
                    result.workspace_id = workspace_id
                    self._log("14. Выбор Workspace...")
                    continue_url = self._select_workspace(workspace_id)

            if not continue_url:
                # Последняя попытка — authorize/continue напрямую
                self._log("13. Workspace не найден, пробуем authorize/continue...", "warning")
                try:
                    resp = self.session.get(
                        OPENAI_API_ENDPOINTS["signup"],
                        headers={"accept": "application/json"},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                        continue_url = str(data.get("continue_url") or data.get("redirect_url") or "").strip()
                        if continue_url:
                            self._log(f"continue_url из authorize/continue: {continue_url[:80]}...")
                    if not continue_url:
                        self._log(f"authorize/continue не дал URL. Status: {resp.status_code}, Body: {resp.text[:200]}", "warning")
                except Exception as e:
                    self._log(f"Ошибка authorize/continue: {e}", "warning")

            if not continue_url:
                result.error_message = "Не удалось получить continue_url (workspace/select/authorize)"
                return result

            # 15. Следование по цепочке редиректов
            self._log("15. Следование по цепочке редиректов...")
            callback_url = self._follow_redirects(continue_url)
            if not callback_url:
                result.error_message = "Ошибка следования по редиректам"
                return result

            # 16. Обработка OAuth callback
            self._log("16. Обработка OAuth callback...")
            token_info = self._handle_oauth_callback(callback_url)
            if not token_info:
                result.error_message = "Ошибка обработки OAuth callback"
                return result

            # Извлечение информации об аккаунте
            result.account_id = token_info.get("account_id", "")
            result.access_token = token_info.get("access_token", "")
            result.refresh_token = token_info.get("refresh_token", "")
            result.id_token = token_info.get("id_token", "")
            result.password = self.password or ""  # Сохранение пароля (для существующего аккаунта пустой)

            # Установка метки источника
            result.source = "login" if self._is_existing_account else "register"

            # Попытка получить session_token из cookie
            session_cookie = self.session.cookies.get("__Secure-next-auth.session-token")
            if session_cookie:
                self.session_token = session_cookie
                result.session_token = session_cookie
                self._log(f"Получен Session Token")

            # 17. Завершение
            self._log("=" * 60)
            if self._is_existing_account:
                self._log("Авторизация успешна! (существующий аккаунт)")
            else:
                self._log("Регистрация завершена!")
            self._log(f"Email: {result.email}")
            self._log(f"Account ID: {result.account_id}")
            self._log(f"Workspace ID: {result.workspace_id}")
            self._log("=" * 60)

            result.success = True
            result.metadata = {
                "email_service": self.email_service.service_type.value,
                "proxy_used": self.proxy_url,
                "registered_at": datetime.now().isoformat(),
                "is_existing_account": self._is_existing_account,
            }

            return result

        except Exception as e:
            self._log(f"Непредвиденная ошибка в процессе регистрации: {e}", "error")
            result.error_message = str(e)
            return result

    def save_to_database(self, result: RegistrationResult) -> bool:
        """
        Сохранение результата в базу данных

        Args:
            result: Результат регистрации

        Returns:
            Успешно ли сохранение
        """
        if not result.success:
            return False

        try:
            # Получение client_id по умолчанию
            settings = get_settings()

            with get_db() as db:
                # Merge Abuzovo mailbox_id into extra_data if applicable
                extra = dict(result.metadata) if result.metadata else {}
                if (self.email_service.service_type == EmailServiceType.ABUZOVO
                        and self.email_info
                        and self.email_info.get("mailbox_id")):
                    extra["abuzovo_mailbox_id"] = self.email_info["mailbox_id"]

                # Сохранение информации об аккаунте
                account = crud.create_account(
                    db,
                    email=result.email,
                    password=result.password,
                    client_id=settings.openai_client_id,
                    session_token=result.session_token,
                    email_service=self.email_service.service_type.value,
                    email_service_id=self.email_info.get("service_id") if self.email_info else None,
                    account_id=result.account_id,
                    workspace_id=result.workspace_id,
                    access_token=result.access_token,
                    refresh_token=result.refresh_token,
                    id_token=result.id_token,
                    proxy_used=self.proxy_url,
                    extra_data=extra or None,
                    source=result.source
                )

                self._log(f"Аккаунт сохранён в БД, ID: {account.id}")
                return True

        except Exception as e:
            self._log(f"Ошибка сохранения в БД: {e}", "error")
            return False