"""
Модуль авторизации OpenAI OAuth
Функции OAuth, извлечённые из main.py
"""

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional

from curl_cffi import requests as cffi_requests

from ..config.constants import (
    OAUTH_CLIENT_ID,
    OAUTH_AUTH_URL,
    OAUTH_TOKEN_URL,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPE,
)


def _b64url_no_pad(raw: bytes) -> str:
    """Кодирование Base64 URL (без дополнения)"""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _sha256_b64url_no_pad(s: str) -> str:
    """Кодирование Base64 URL после хеширования SHA256"""
    return _b64url_no_pad(hashlib.sha256(s.encode("ascii")).digest())


def _random_state(nbytes: int = 16) -> str:
    """Генерация случайного state"""
    return secrets.token_urlsafe(nbytes)


def _pkce_verifier() -> str:
    """Генерация PKCE code_verifier"""
    return secrets.token_urlsafe(64)


def _parse_callback_url(callback_url: str) -> Dict[str, str]:
    """Разбор URL обратного вызова"""
    candidate = callback_url.strip()
    if not candidate:
        return {"code": "", "state": "", "error": "", "error_description": ""}

    if "://" not in candidate:
        if candidate.startswith("?"):
            candidate = f"http://localhost{candidate}"
        elif any(ch in candidate for ch in "/?#") or ":" in candidate:
            candidate = f"http://{candidate}"
        elif "=" in candidate:
            candidate = f"http://localhost/?{candidate}"

    parsed = urllib.parse.urlparse(candidate)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    fragment = urllib.parse.parse_qs(parsed.fragment, keep_blank_values=True)

    for key, values in fragment.items():
        if key not in query or not query[key] or not (query[key][0] or "").strip():
            query[key] = values

    def get1(k: str) -> str:
        v = query.get(k, [""])
        return (v[0] or "").strip()

    code = get1("code")
    state = get1("state")
    error = get1("error")
    error_description = get1("error_description")

    if code and not state and "#" in code:
        code, state = code.split("#", 1)

    if not error and error_description:
        error, error_description = error_description, ""

    return {
        "code": code,
        "state": state,
        "error": error,
        "error_description": error_description,
    }


def _jwt_claims_no_verify(id_token: str) -> Dict[str, Any]:
    """Разбор JWT ID Token (без проверки подписи)"""
    if not id_token or id_token.count(".") < 2:
        return {}
    payload_b64 = id_token.split(".")[1]
    pad = "=" * ((4 - (len(payload_b64) % 4)) % 4)
    try:
        payload = base64.urlsafe_b64decode((payload_b64 + pad).encode("ascii"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return {}


def _decode_jwt_segment(seg: str) -> Dict[str, Any]:
    """Декодирование сегмента JWT"""
    raw = (seg or "").strip()
    if not raw:
        return {}
    pad = "=" * ((4 - (len(raw) % 4)) % 4)
    try:
        decoded = base64.urlsafe_b64decode((raw + pad).encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}


def _to_int(v: Any) -> int:
    """Преобразование в целое число"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _post_form(
    url: str,
    data: Dict[str, str],
    timeout: int = 30,
    proxy_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Отправка POST-запроса с формой

    Args:
        url: URL запроса
        data: данные формы
        timeout: время ожидания
        proxy_url: URL прокси

    Returns:
        JSON-данные ответа
    """
    # Формирование настройки прокси
    proxies = None
    if proxy_url:
        proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        # Отправка запроса через curl_cffi с поддержкой прокси и отпечатка браузера
        response = cffi_requests.post(
            url,
            data=data,
            headers=headers,
            timeout=timeout,
            proxies=proxies,
            impersonate="chrome"
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"token exchange failed: {response.status_code}: {response.text}"
            )

        return response.json()

    except cffi_requests.RequestsError as e:
        raise RuntimeError(f"token exchange failed: network error: {e}") from e


@dataclass(frozen=True)
class OAuthStart:
    """Информация о начале OAuth"""
    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str


def generate_oauth_url(
    *,
    redirect_uri: str = OAUTH_REDIRECT_URI,
    scope: str = OAUTH_SCOPE,
    client_id: str = OAUTH_CLIENT_ID
) -> OAuthStart:
    """
    Генерация URL авторизации OAuth

    Args:
        redirect_uri: адрес обратного вызова
        scope: область разрешений
        client_id: OpenAI Client ID

    Returns:
        Объект OAuthStart, содержащий URL авторизации и необходимые параметры
    """
    state = _random_state()
    code_verifier = _pkce_verifier()
    code_challenge = _sha256_b64url_no_pad(code_verifier)

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    auth_url = f"{OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return OAuthStart(
        auth_url=auth_url,
        state=state,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )


def submit_callback_url(
    *,
    callback_url: str,
    expected_state: str,
    code_verifier: str,
    redirect_uri: str = OAUTH_REDIRECT_URI,
    client_id: str = OAUTH_CLIENT_ID,
    token_url: str = OAUTH_TOKEN_URL,
    proxy_url: Optional[str] = None
) -> str:
    """
    Обработка URL обратного вызова OAuth, получение токена доступа

    Args:
        callback_url: URL обратного вызова
        expected_state: ожидаемое значение state
        code_verifier: PKCE code_verifier
        redirect_uri: адрес обратного вызова
        client_id: OpenAI Client ID
        token_url: адрес обмена токенов
        proxy_url: URL прокси

    Returns:
        JSON-строка с токеном доступа и другой информацией

    Raises:
        RuntimeError: ошибка OAuth
        ValueError: отсутствуют необходимые параметры или state не совпадает
    """
    cb = _parse_callback_url(callback_url)
    if cb["error"]:
        desc = cb["error_description"]
        raise RuntimeError(f"oauth error: {cb['error']}: {desc}".strip())

    if not cb["code"]:
        raise ValueError("callback url missing ?code=")
    if not cb["state"]:
        raise ValueError("callback url missing ?state=")
    if cb["state"] != expected_state:
        raise ValueError("state mismatch")

    token_resp = _post_form(
        token_url,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": cb["code"],
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        proxy_url=proxy_url
    )

    access_token = (token_resp.get("access_token") or "").strip()
    refresh_token = (token_resp.get("refresh_token") or "").strip()
    id_token = (token_resp.get("id_token") or "").strip()
    expires_in = _to_int(token_resp.get("expires_in"))

    claims = _jwt_claims_no_verify(id_token)
    email = str(claims.get("email") or "").strip()
    auth_claims = claims.get("https://api.openai.com/auth") or {}
    account_id = str(auth_claims.get("chatgpt_account_id") or "").strip()

    now = int(time.time())
    expired_rfc3339 = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + max(expires_in, 0))
    )
    now_rfc3339 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    config = {
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "last_refresh": now_rfc3339,
        "email": email,
        "type": "codex",
        "expired": expired_rfc3339,
    }

    return json.dumps(config, ensure_ascii=False, separators=(",", ":"))


class OAuthManager:
    """Менеджер OAuth"""

    def __init__(
        self,
        client_id: str = OAUTH_CLIENT_ID,
        auth_url: str = OAUTH_AUTH_URL,
        token_url: str = OAUTH_TOKEN_URL,
        redirect_uri: str = OAUTH_REDIRECT_URI,
        scope: str = OAUTH_SCOPE,
        proxy_url: Optional[str] = None
    ):
        self.client_id = client_id
        self.auth_url = auth_url
        self.token_url = token_url
        self.redirect_uri = redirect_uri
        self.scope = scope
        self.proxy_url = proxy_url

    def start_oauth(self) -> OAuthStart:
        """Начало процесса OAuth"""
        return generate_oauth_url(
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            client_id=self.client_id
        )

    def handle_callback(
        self,
        callback_url: str,
        expected_state: str,
        code_verifier: str
    ) -> Dict[str, Any]:
        """Обработка обратного вызова OAuth"""
        result_json = submit_callback_url(
            callback_url=callback_url,
            expected_state=expected_state,
            code_verifier=code_verifier,
            redirect_uri=self.redirect_uri,
            client_id=self.client_id,
            token_url=self.token_url,
            proxy_url=self.proxy_url
        )
        return json.loads(result_json)

    def extract_account_info(self, id_token: str) -> Dict[str, Any]:
        """Извлечение информации об аккаунте из ID Token"""
        claims = _jwt_claims_no_verify(id_token)
        email = str(claims.get("email") or "").strip()
        auth_claims = claims.get("https://api.openai.com/auth") or {}
        account_id = str(auth_claims.get("chatgpt_account_id") or "").strip()

        return {
            "email": email,
            "account_id": account_id,
            "claims": claims
        }