"""
Workspace Manager — ядро управления рабочими областями
Мониторинг, auto-kick, ban detection, redistribution
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from .workspace_api import WorkspaceAPIClient, WorkspaceInfo, WorkspaceMemberInfo, WorkspaceStats
from ..database.session import get_db
from ..database import crud
from ..database.models import Workspace, WorkspaceMember
from ..config.settings import get_settings

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Менеджер рабочих областей"""

    def __init__(self, proxy_url: Optional[str] = None):
        self.api_client = WorkspaceAPIClient(proxy_url=proxy_url)
        self._log_callbacks = []  # For WebSocket broadcasting

    def add_log_callback(self, callback):
        """Добавить callback для трансляции логов"""
        self._log_callbacks.append(callback)

    def _log(self, message: str, level: str = "info"):
        """Логирование + broadcast"""
        getattr(logger, level, logger.info)(message)
        for cb in self._log_callbacks:
            try:
                cb(message, level)
            except Exception:
                pass

    # ==================== CHECK / SYNC ====================

    def check_workspace(self, workspace_db_id: int) -> Dict[str, Any]:
        """
        Проверить workspace: обновить слоты, участников, статус бана.
        Основная функция мониторинга.
        """
        with get_db() as db:
            ws = crud.get_workspace_by_id(db, workspace_db_id)
            if not ws:
                return {"error": "Workspace не найден"}
            if not ws.access_token:
                return {"error": "Нет access_token для workspace"}

            account_id = ws.account_id
            access_token = ws.access_token

        try:
            # 1. Get stats from OpenAI API
            self._log(f"[{account_id}] Проверка workspace...")
            stats = self.api_client.get_workspace_stats(access_token, account_id)

            # 2. Check ban status
            is_banned, ban_reason = self.api_client.check_workspace_banned(access_token, account_id)

            # 3. Update DB
            with get_db() as db:
                update_data = {
                    "used_seats": stats.used_seats,
                    "status": "banned" if is_banned else "active",
                    "last_checked_at": datetime.utcnow(),
                    "name": stats.name or ws.name,
                }
                if is_banned and not ws.banned_at:
                    update_data["banned_at"] = datetime.utcnow()
                if stats.expires_at:
                    try:
                        update_data["subscription_expires_at"] = datetime.fromisoformat(
                            stats.expires_at.replace("Z", "+00:00")
                        )
                    except Exception:
                        pass

                crud.update_workspace(db, workspace_db_id, **update_data)

                # 4. Sync members
                self._sync_members(db, workspace_db_id, stats.members)

            result = {
                "account_id": account_id,
                "name": stats.name,
                "used_seats": stats.used_seats,
                "pending_invites": stats.pending_invites,
                "is_banned": is_banned,
                "days_remaining": stats.days_remaining,
                "members_count": len(stats.members),
            }

            self._log(f"[{account_id}] Слоты: {stats.used_seats}, Бан: {is_banned}, Дней: {stats.days_remaining}")
            return result

        except Exception as e:
            self._log(f"[{account_id}] Ошибка проверки: {e}", "error")
            return {"error": str(e)}

    def _sync_members(self, db, workspace_db_id: int, api_members: List[WorkspaceMemberInfo]):
        """Синхронизировать участников из API с БД"""
        existing = crud.get_workspace_members(db, workspace_db_id)
        existing_by_email = {m.email: m for m in existing}

        for api_member in api_members:
            if api_member.email in existing_by_email:
                # Update existing
                db_member = existing_by_email[api_member.email]
                crud.update_workspace_member(db, db_member.id,
                    openai_user_id=api_member.user_id,
                    name=api_member.name,
                    role=api_member.role,
                    seat_type=api_member.seat_type or "",
                    status="active" if not api_member.deactivated_time else "deactivated",
                )
                del existing_by_email[api_member.email]
            else:
                # New member
                crud.create_workspace_member(db, workspace_db_id, api_member.email,
                    openai_user_id=api_member.user_id,
                    name=api_member.name,
                    role=api_member.role,
                    seat_type=api_member.seat_type or "",
                    status="active",
                    invited_at=datetime.fromisoformat(api_member.created_time.replace("Z", "+00:00")) if api_member.created_time else None,
                )

        # Members no longer in API — mark as left (but don't delete)
        for email, db_member in existing_by_email.items():
            if db_member.status == "active":
                crud.update_workspace_member(db, db_member.id, status="left")

    def check_all_workspaces(self) -> List[Dict[str, Any]]:
        """Проверить все активные workspaces"""
        results = []
        with get_db() as db:
            workspaces = crud.get_active_workspaces(db)
            ws_ids = [(w.id, w.account_id) for w in workspaces]

        self._log(f"Начинаем проверку {len(ws_ids)} workspace(s)...")

        for ws_id, acc_id in ws_ids:
            result = self.check_workspace(ws_id)
            result["workspace_db_id"] = ws_id
            results.append(result)

        return results

    # ==================== AUTO-KICK ====================

    def process_expired_members(self, workspace_db_id: int) -> List[Dict[str, Any]]:
        """Кикнуть участников с истёкшим сроком"""
        settings = get_settings()
        if not settings.workspace_auto_kick_enabled:
            return []

        results = []
        with get_db() as db:
            ws = crud.get_workspace_by_id(db, workspace_db_id)
            if not ws or not ws.access_token:
                return []

            expired = crud.get_expired_members(db, workspace_db_id)

        for member in expired:
            if not member.openai_user_id:
                continue
            if member.role == "account-owner":
                continue  # Never kick owner

            success, msg = self.kick_member(workspace_db_id, member.id, "Срок приглашения истёк (auto-kick)")
            results.append({
                "member_id": member.id,
                "email": member.email,
                "success": success,
                "message": msg,
            })

        return results

    def kick_member(self, workspace_db_id: int, member_db_id: int, reason: str = "") -> Tuple[bool, str]:
        """Кикнуть конкретного участника"""
        with get_db() as db:
            ws = crud.get_workspace_by_id(db, workspace_db_id)
            member = crud.get_workspace_member_by_id(db, member_db_id)

            if not ws or not member:
                return False, "Workspace или участник не найден"
            if not ws.access_token:
                return False, "Нет access_token"
            if member.role == "account-owner":
                return False, "Невозможно кикнуть владельца"
            if not member.openai_user_id:
                return False, "Нет openai_user_id"

        # Call OpenAI API
        success, msg = self.api_client.kick_member(ws.access_token, ws.account_id, member.openai_user_id)

        if success:
            with get_db() as db:
                crud.update_workspace_member(db, member_db_id,
                    status="kicked",
                    kicked_at=datetime.utcnow(),
                    kick_reason=reason,
                )
            self._log(f"Кик {member.email} из {ws.name}: {reason}")

        return success, msg

    # ==================== INVITE ====================

    def invite_member(self, workspace_db_id: int, email: str, duration_days: Optional[int] = None) -> Tuple[bool, str]:
        """Пригласить участника в workspace"""
        with get_db() as db:
            ws = crud.get_workspace_by_id(db, workspace_db_id)
            if not ws or not ws.access_token:
                return False, "Workspace не найден или нет токена"

        success, msg = self.api_client.invite_member(ws.access_token, ws.account_id, [email])

        if success:
            expires_at = None
            if duration_days:
                expires_at = datetime.utcnow() + timedelta(days=duration_days)

            with get_db() as db:
                crud.create_workspace_member(db, workspace_db_id, email,
                    status="invited",
                    duration_days=duration_days,
                    invited_at=datetime.utcnow(),
                    expires_at=expires_at,
                )
            self._log(f"Приглашён {email} в {ws.name} на {duration_days or '∞'} дней")

        return success, msg

    # ==================== BAN DETECTION VIA EMAILS ====================

    def check_ban_emails(self, workspace_db_id: int) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Проверить входящую почту владельца workspace на письма о бане.
        Использует Abuzovo API для чтения писем.
        Returns: (ban_detected, found_emails)
        """
        settings = get_settings()
        if not settings.workspace_ban_detection_enabled:
            return False, []

        ban_keywords = settings.workspace_ban_keywords
        if isinstance(ban_keywords, str):
            try:
                import json
                ban_keywords = json.loads(ban_keywords)
            except Exception:
                ban_keywords = ["banned", "suspended", "violation"]

        with get_db() as db:
            ws = crud.get_workspace_by_id(db, workspace_db_id)
            if not ws or not ws.extra_data:
                return False, []

        # Get mailbox_id from workspace extra_data
        mailbox_id = (ws.extra_data or {}).get("owner_mailbox_id")
        if not mailbox_id:
            return False, []

        try:
            from curl_cffi import requests as cffi_requests

            api_url = settings.abuzovo_api_url.rstrip("/")
            api_token = settings.abuzovo_api_token.get_secret_value() if settings.abuzovo_api_token else ""

            if not api_token:
                return False, []

            resp = cffi_requests.get(
                f"{api_url}/api/v1/messages",
                params={"mailbox_id": mailbox_id},
                headers={"Authorization": f"Bearer {api_token}"},
                timeout=30,
                impersonate="chrome120",
            )

            if resp.status_code != 200:
                logger.warning(f"Failed to read mailbox {mailbox_id}: HTTP {resp.status_code}")
                return False, []

            messages = resp.json().get("items", []) or resp.json().get("messages", [])

        except Exception as e:
            logger.error(f"Error reading ban emails: {e}")
            return False, []

        # Check messages for ban keywords
        ban_detected = False
        found = []

        for msg in messages:
            subject = (msg.get("subject") or "").lower()
            body = (msg.get("body") or msg.get("text") or msg.get("html") or "").lower()
            sender = (msg.get("from") or msg.get("sender") or "").lower()

            # Check if from OpenAI
            if "openai" not in sender and "chatgpt" not in sender:
                continue

            # Check for ban keywords
            text_to_check = f"{subject} {body}"
            for keyword in ban_keywords:
                if keyword.lower() in text_to_check:
                    ban_detected = True
                    found.append({
                        "subject": msg.get("subject"),
                        "sender": sender,
                        "keyword": keyword,
                        "message_id": msg.get("id"),
                    })

                    # Save to DB
                    with get_db() as db:
                        crud.create_workspace_ban_email(db, workspace_db_id,
                            mailbox_id=mailbox_id,
                            message_id=msg.get("id"),
                            subject=msg.get("subject"),
                            sender=sender,
                            body_snippet=text_to_check[:500],
                            ban_type="workspace_ban",
                        )
                    break

        if ban_detected:
            self._log(f"⚠️ Обнаружен бан workspace {ws.name}!", "warning")
            with get_db() as db:
                crud.update_workspace(db, workspace_db_id,
                    status="banned",
                    banned_at=datetime.utcnow(),
                )

        return ban_detected, found

    # ==================== REDISTRIBUTE ====================

    def redistribute_members(self, banned_workspace_db_id: int) -> List[Dict[str, Any]]:
        """
        Перераспределить участников забаненного workspace.
        - 1-day users → кикнуть
        - 30-day (long-term) users → переместить в другой workspace
        """
        settings = get_settings()
        if not settings.workspace_auto_redistribute_enabled:
            return []

        long_duration = settings.workspace_long_duration_days
        results = []

        with get_db() as db:
            banned_ws = crud.get_workspace_by_id(db, banned_workspace_db_id)
            if not banned_ws:
                return []

            members = crud.get_workspace_members(db, banned_workspace_db_id, status="active")
            active_workspaces = crud.get_active_workspaces(db)
            # Exclude the banned one
            target_workspaces = [w for w in active_workspaces if w.id != banned_workspace_db_id]

        self._log(f"Перераспределение из {banned_ws.name}: {len(members)} участников")

        for member in members:
            if member.role == "account-owner":
                continue

            duration = member.duration_days or 0

            if duration <= settings.workspace_auto_kick_duration:
                # Short-term user → just kick (or mark as kicked since ws is banned)
                with get_db() as db:
                    crud.update_workspace_member(db, member.id,
                        status="kicked",
                        kicked_at=datetime.utcnow(),
                        kick_reason=f"Workspace забанен, краткосрочный ({duration}д)",
                    )
                results.append({
                    "email": member.email,
                    "action": "kicked",
                    "reason": f"short-term ({duration}d), workspace banned",
                })
                self._log(f"  Кик {member.email} (краткосрочный {duration}д)")

            elif duration >= long_duration:
                # Long-term user → try to move to another workspace
                moved = False
                for target_ws in target_workspaces:
                    if target_ws.used_seats < target_ws.max_seats and target_ws.access_token:
                        # Invite to new workspace
                        success, msg = self.api_client.invite_member(
                            target_ws.access_token, target_ws.account_id, [member.email]
                        )
                        if success:
                            with get_db() as db:
                                crud.update_workspace_member(db, member.id,
                                    status="kicked",
                                    kicked_at=datetime.utcnow(),
                                    kick_reason=f"Перемещён в {target_ws.name} (workspace забанен)",
                                    moved_to_workspace_id=target_ws.id,
                                )
                                # Create member in new workspace
                                crud.create_workspace_member(db, target_ws.id, member.email,
                                    status="invited",
                                    duration_days=member.duration_days,
                                    invited_at=datetime.utcnow(),
                                    expires_at=member.expires_at,
                                )
                                # Update target seats
                                crud.update_workspace(db, target_ws.id,
                                    used_seats=target_ws.used_seats + 1,
                                )

                            results.append({
                                "email": member.email,
                                "action": "moved",
                                "target_workspace": target_ws.name,
                            })
                            self._log(f"  Перемещён {member.email} → {target_ws.name}")
                            moved = True
                            break

                if not moved:
                    results.append({
                        "email": member.email,
                        "action": "no_space",
                        "reason": "Нет доступных workspace с свободными слотами",
                    })
                    self._log(f"  ⚠️ Нет места для {member.email}", "warning")

            else:
                # Medium-term — just kick
                with get_db() as db:
                    crud.update_workspace_member(db, member.id,
                        status="kicked",
                        kicked_at=datetime.utcnow(),
                        kick_reason=f"Workspace забанен ({duration}д)",
                    )
                results.append({
                    "email": member.email,
                    "action": "kicked",
                    "reason": f"medium-term ({duration}d), workspace banned",
                })

        return results

    # ==================== FULL MONITORING CYCLE ====================

    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """
        Полный цикл мониторинга (вызывается scheduler'ом):
        1. Проверить все workspaces
        2. Auto-kick просроченных
        3. Проверить письма на бан
        4. Перераспределить при бане
        """
        settings = get_settings()
        if not settings.workspace_monitoring_enabled:
            return {"skipped": True, "reason": "Мониторинг выключен"}

        self._log("═══ Цикл мониторинга ═══")
        cycle_result = {
            "timestamp": datetime.utcnow().isoformat(),
            "checks": [],
            "kicks": [],
            "bans_detected": [],
            "redistributions": [],
        }

        # 1. Check all workspaces
        check_results = self.check_all_workspaces()
        cycle_result["checks"] = check_results

        # 2. Auto-kick expired for each workspace
        with get_db() as db:
            all_ws = crud.get_active_workspaces(db)
            ws_ids = [w.id for w in all_ws]

        for ws_id in ws_ids:
            kicks = self.process_expired_members(ws_id)
            cycle_result["kicks"].extend(kicks)

        # 3. Check ban emails
        if settings.workspace_ban_detection_enabled:
            with get_db() as db:
                all_ws_for_ban = crud.get_workspaces(db, status="active")
                ban_ws_ids = [w.id for w in all_ws_for_ban]

            for ws_id in ban_ws_ids:
                ban_detected, ban_emails = self.check_ban_emails(ws_id)
                if ban_detected:
                    cycle_result["bans_detected"].append({
                        "workspace_id": ws_id,
                        "emails": ban_emails,
                    })
                    # 4. Redistribute if ban detected
                    if settings.workspace_auto_redistribute_enabled:
                        redis_results = self.redistribute_members(ws_id)
                        cycle_result["redistributions"].extend(redis_results)

        # Also check API-detected bans (is_deactivated)
        for check in check_results:
            if check.get("is_banned") and settings.workspace_auto_redistribute_enabled:
                ws_db_id = check.get("workspace_db_id")
                if ws_db_id:
                    redis_results = self.redistribute_members(ws_db_id)
                    cycle_result["redistributions"].extend(redis_results)

        self._log(f"═══ Цикл завершён: {len(check_results)} проверок, {len(cycle_result['kicks'])} киков, {len(cycle_result['bans_detected'])} банов ═══")
        return cycle_result
