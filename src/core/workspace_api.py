"""
OpenAI Workspace API Client
Клиент для управления Team workspaces через ChatGPT backend API
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from curl_cffi import requests as cffi_requests

logger = logging.getLogger(__name__)

BASE_URL = "https://chatgpt.com/backend-api"


@dataclass
class WorkspaceInfo:
    """Информация о рабочей области"""
    account_id: str
    organization_id: str = ""
    name: str = ""
    plan_type: str = "free"
    structure: str = "personal"
    is_deactivated: bool = False
    owner_id: str = ""
    subscription_plan: str = ""
    has_active_subscription: bool = False
    expires_at: Optional[str] = None
    renews_at: Optional[str] = None
    cancels_at: Optional[str] = None
    billing_period: str = ""
    is_delinquent: bool = False
    features: list = field(default_factory=list)


@dataclass
class WorkspaceMemberInfo:
    """Информация об участнике workspace"""
    user_id: str
    account_user_id: str = ""
    email: str = ""
    name: str = ""
    role: str = "standard-user"
    seat_type: str = ""
    created_time: str = ""
    deactivated_time: Optional[str] = None


@dataclass
class WorkspaceStats:
    """Статистика рабочей области"""
    account_id: str
    name: str = ""
    used_seats: int = 0
    members: List[WorkspaceMemberInfo] = field(default_factory=list)
    pending_invites: int = 0
    is_deactivated: bool = False
    plan_type: str = ""
    expires_at: Optional[str] = None
    days_remaining: int = 0


class WorkspaceAPIClient:
    """Клиент для OpenAI Workspace API"""

    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url

    def _get_proxies(self) -> Optional[dict]:
        if self.proxy_url:
            return {"http": self.proxy_url, "https": self.proxy_url}
        return None

    def _make_request(
        self,
        method: str,
        endpoint: str,
        access_token: str,
        account_id: Optional[str] = None,
        json_data: Optional[dict] = None,
        timeout: int = 30,
    ) -> Tuple[int, Any]:
        """
        Выполнить запрос к ChatGPT backend API

        Returns:
            (status_code, response_data)
        """
        url = f"{BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if account_id:
            headers["Chatgpt-Account-Id"] = account_id

        try:
            if method.upper() == "GET":
                resp = cffi_requests.get(
                    url, headers=headers, proxies=self._get_proxies(),
                    timeout=timeout, impersonate="chrome120"
                )
            elif method.upper() == "POST":
                resp = cffi_requests.post(
                    url, headers=headers, json=json_data,
                    proxies=self._get_proxies(), timeout=timeout, impersonate="chrome120"
                )
            elif method.upper() == "DELETE":
                resp = cffi_requests.delete(
                    url, headers=headers, json=json_data,
                    proxies=self._get_proxies(), timeout=timeout, impersonate="chrome120"
                )
            else:
                raise ValueError(f"Unsupported method: {method}")

            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text[:500]}

            return resp.status_code, data

        except Exception as e:
            logger.error(f"Workspace API request failed: {method} {endpoint} - {e}")
            raise

    # ==================== READ OPERATIONS ====================

    def get_account_info(self, access_token: str) -> Dict[str, Any]:
        """GET /backend-api/me — информация об аккаунте"""
        status, data = self._make_request("GET", "/me", access_token)
        if status != 200:
            raise RuntimeError(f"Failed to get account info: HTTP {status}")
        return data

    def get_all_workspaces(self, access_token: str) -> List[WorkspaceInfo]:
        """
        GET /backend-api/accounts/check/v4-2023-04-27
        Возвращает все workspace'ы пользователя с информацией о подписках
        """
        status, data = self._make_request("GET", "/accounts/check/v4-2023-04-27", access_token)
        if status != 200:
            raise RuntimeError(f"Failed to get workspaces: HTTP {status}")

        workspaces = []
        for acc_id, acc_data in data.get("accounts", {}).items():
            if acc_id == "default":
                continue
            account = acc_data.get("account", {})
            entitlement = acc_data.get("entitlement", {})

            ws = WorkspaceInfo(
                account_id=acc_id,
                organization_id=account.get("organization_id", ""),
                name=account.get("name") or "",
                plan_type=account.get("plan_type", "free"),
                structure=account.get("structure", "personal"),
                is_deactivated=account.get("is_deactivated", False),
                owner_id=account.get("account_owner_id", ""),
                subscription_plan=entitlement.get("subscription_plan", ""),
                has_active_subscription=entitlement.get("has_active_subscription", False),
                expires_at=entitlement.get("expires_at"),
                renews_at=entitlement.get("renews_at"),
                cancels_at=entitlement.get("cancels_at"),
                billing_period=entitlement.get("billing_period", ""),
                is_delinquent=entitlement.get("is_delinquent", False),
                features=acc_data.get("features", []),
            )
            workspaces.append(ws)

        return workspaces

    def list_members(self, access_token: str, account_id: str) -> Tuple[List[WorkspaceMemberInfo], int]:
        """
        GET /backend-api/accounts/{account_id}/users
        Возвращает (список участников, общее количество = занятые слоты)
        """
        status, data = self._make_request(
            "GET", f"/accounts/{account_id}/users", access_token, account_id
        )
        if status != 200:
            raise RuntimeError(f"Failed to list members: HTTP {status}")

        members = []
        for item in data.get("items", []):
            member = WorkspaceMemberInfo(
                user_id=item.get("id", ""),
                account_user_id=item.get("account_user_id", ""),
                email=item.get("email", ""),
                name=item.get("name", ""),
                role=item.get("role", "standard-user"),
                seat_type=item.get("seat_type", ""),
                created_time=item.get("created_time", ""),
                deactivated_time=item.get("deactivated_time"),
            )
            members.append(member)

        total = data.get("total", len(members))
        return members, total

    def list_invites(self, access_token: str, account_id: str) -> Tuple[List[Dict[str, Any]], int]:
        """
        GET /backend-api/accounts/{account_id}/invites
        Возвращает (список приглашений, общее количество)
        """
        status, data = self._make_request(
            "GET", f"/accounts/{account_id}/invites", access_token, account_id
        )
        if status != 200:
            raise RuntimeError(f"Failed to list invites: HTTP {status}")

        return data.get("items", []), data.get("total", 0)

    def get_workspace_settings(self, access_token: str, account_id: str) -> Dict[str, Any]:
        """GET /backend-api/accounts/{account_id}/settings"""
        status, data = self._make_request(
            "GET", f"/accounts/{account_id}/settings", access_token, account_id
        )
        if status != 200:
            raise RuntimeError(f"Failed to get workspace settings: HTTP {status}")
        return data

    def get_workspace_stats(self, access_token: str, account_id: str) -> WorkspaceStats:
        """Собирает полную статистику workspace за один вызов"""
        all_ws = self.get_all_workspaces(access_token)
        ws_info = None
        for ws in all_ws:
            if ws.account_id == account_id:
                ws_info = ws
                break

        members, used_seats = self.list_members(access_token, account_id)

        _, pending_count = self.list_invites(access_token, account_id)

        days_remaining = 0
        if ws_info and ws_info.expires_at:
            try:
                expires = datetime.fromisoformat(ws_info.expires_at.replace("+00:00", "+00:00").replace("Z", "+00:00"))
                now = datetime.now(expires.tzinfo) if expires.tzinfo else datetime.utcnow()
                delta = expires - now
                days_remaining = max(0, delta.days)
            except Exception as e:
                logger.warning(f"Failed to parse expires_at: {e}")

        return WorkspaceStats(
            account_id=account_id,
            name=ws_info.name if ws_info else "",
            used_seats=used_seats,
            members=members,
            pending_invites=pending_count,
            is_deactivated=ws_info.is_deactivated if ws_info else False,
            plan_type=ws_info.plan_type if ws_info else "",
            expires_at=ws_info.expires_at if ws_info else None,
            days_remaining=days_remaining,
        )

    # ==================== WRITE OPERATIONS ====================

    def invite_member(self, access_token: str, account_id: str, email_addresses: List[str]) -> Tuple[bool, str]:
        """
        POST /backend-api/accounts/{account_id}/invites
        Пригласить пользователей в workspace
        """
        try:
            status, data = self._make_request(
                "POST", f"/accounts/{account_id}/invites", access_token, account_id,
                json_data={"email_addresses": email_addresses}
            )
            if status in (200, 201):
                return True, f"Приглашение отправлено: {', '.join(email_addresses)}"
            error_msg = data.get("detail", str(data)) if isinstance(data, dict) else str(data)
            return False, f"Ошибка приглашения (HTTP {status}): {error_msg}"
        except Exception as e:
            return False, f"Ошибка при отправке приглашения: {str(e)}"

    def kick_member(self, access_token: str, account_id: str, user_id: str) -> Tuple[bool, str]:
        """
        DELETE /backend-api/accounts/{account_id}/users/{user_id}
        Удалить пользователя из workspace (кик)
        """
        try:
            status, data = self._make_request(
                "DELETE", f"/accounts/{account_id}/users/{user_id}", access_token, account_id
            )
            if status == 200 and data.get("success"):
                return True, "Пользователь удалён из workspace"
            error_msg = data.get("detail", str(data)) if isinstance(data, dict) else str(data)
            return False, f"Ошибка удаления (HTTP {status}): {error_msg}"
        except Exception as e:
            return False, f"Ошибка при удалении пользователя: {str(e)}"

    # ==================== BAN DETECTION ====================

    def check_workspace_banned(self, access_token: str, account_id: str) -> Tuple[bool, str]:
        """
        Проверить забанен ли workspace через accounts/check
        Returns: (is_banned, reason)
        """
        try:
            all_ws = self.get_all_workspaces(access_token)
            for ws in all_ws:
                if ws.account_id == account_id:
                    if ws.is_deactivated:
                        return True, "Workspace деактивирован (is_deactivated=true)"
                    if not ws.has_active_subscription:
                        return False, "Подписка неактивна (но не бан)"
                    return False, "Workspace активен"
            return False, "Workspace не найден в аккаунте"
        except Exception as e:
            logger.error(f"Ban check failed: {e}")
            return False, f"Ошибка проверки: {str(e)}"
