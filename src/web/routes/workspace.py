"""
API маршруты для управления рабочими областями (workspaces)
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ...database.session import get_db
from ...database import crud
from ...core.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)
router = APIRouter()


# === Pydantic models for requests ===

class WorkspaceCreate(BaseModel):
    name: str
    account_id: str
    access_token: str
    organization_id: Optional[str] = None
    plan_type: str = "team"
    max_seats: int = 5

class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    access_token: Optional[str] = None
    max_seats: Optional[int] = None
    status: Optional[str] = None

class InviteRequest(BaseModel):
    email: str

class KickRequest(BaseModel):
    reason: Optional[str] = "manual kick"


# === Monitoring control (BEFORE /{workspace_id} to avoid path conflicts) ===

@router.get("/monitoring/status")
async def monitoring_status():
    """Get monitoring scheduler status"""
    from ...core.scheduler import workspace_scheduler
    return workspace_scheduler.get_status()


@router.post("/monitoring/start")
async def monitoring_start():
    """Start the monitoring scheduler"""
    from ...core.scheduler import workspace_scheduler
    if workspace_scheduler.is_running:
        return {"success": True, "status": "already_running"}
    await workspace_scheduler.start()
    return {"success": True, "status": "started"}


@router.post("/monitoring/stop")
async def monitoring_stop():
    """Stop the monitoring scheduler"""
    from ...core.scheduler import workspace_scheduler
    if not workspace_scheduler.is_running:
        return {"success": True, "status": "already_stopped"}
    await workspace_scheduler.stop()
    return {"success": True, "status": "stopped"}


@router.post("/monitoring/cycle")
async def monitoring_run_cycle():
    """Force run one monitoring cycle"""
    try:
        manager = WorkspaceManager()
        result = manager.run_monitoring_cycle()
        return result
    except Exception as e:
        logger.error(f"Monitoring cycle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-all")
async def check_all_workspaces():
    """Force check all workspaces"""
    try:
        manager = WorkspaceManager()
        result = manager.check_all_workspaces()
        return result
    except Exception as e:
        logger.error(f"Check all workspaces error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === CRUD routes ===

@router.get("")
async def list_workspaces():
    """Get all workspaces with stats"""
    with get_db() as db:
        workspaces = crud.get_workspaces(db)
        result = []
        for ws in workspaces:
            members = crud.get_workspace_members(db, ws.id)
            data = ws.to_dict()
            data["members_count"] = len(members)
            result.append(data)
    return {"workspaces": result}


@router.post("")
async def create_workspace(data: WorkspaceCreate):
    """Add a workspace to monitoring"""
    with get_db() as db:
        existing = crud.get_workspace_by_account_id(db, data.account_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Workspace с account_id '{data.account_id}' уже существует (id={existing.id})"
            )
        ws = crud.create_workspace(
            db,
            account_id=data.account_id,
            name=data.name,
            access_token=data.access_token,
            organization_id=data.organization_id,
            plan_type=data.plan_type,
            max_seats=data.max_seats,
        )
    return {"success": True, "workspace_id": ws.id, "workspace": ws.to_dict()}


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: int):
    """Get workspace details with members and ban emails"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
        members = crud.get_workspace_members(db, ws.id)
        ban_emails = crud.get_workspace_ban_emails(db, ws.id)
        return {
            "workspace": ws.to_dict(),
            "members": [m.to_dict() for m in members],
            "ban_emails": [be.to_dict() for be in ban_emails],
        }


@router.put("/{workspace_id}")
async def update_workspace(workspace_id: int, data: WorkspaceUpdate):
    """Update workspace settings"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="Нет данных для обновления")
        updated = crud.update_workspace(db, workspace_id, **update_data)
    return {"success": True, "workspace": updated.to_dict()}


@router.delete("/{workspace_id}")
async def delete_workspace(workspace_id: int):
    """Remove workspace from monitoring"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
        deleted = crud.delete_workspace(db, workspace_id)
        if not deleted:
            raise HTTPException(status_code=500, detail="Не удалось удалить workspace")
    return {"success": True, "deleted_id": workspace_id}


# === Action routes ===

@router.post("/{workspace_id}/check")
async def check_workspace(workspace_id: int):
    """Force check a single workspace"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
    try:
        manager = WorkspaceManager()
        result = manager.check_workspace(workspace_id)
        return result
    except Exception as e:
        logger.error(f"Check workspace {workspace_id} error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/auto-kick")
async def auto_kick_expired(workspace_id: int):
    """Auto-kick expired members from workspace"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
    try:
        manager = WorkspaceManager()
        result = manager.auto_kick_expired(workspace_id)
        return result
    except Exception as e:
        logger.error(f"Auto-kick workspace {workspace_id} error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/invite")
async def invite_member(workspace_id: int, data: InviteRequest):
    """Invite a member to workspace"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
    try:
        manager = WorkspaceManager()
        result = manager.invite_member(workspace_id, data.email)
        return result
    except Exception as e:
        logger.error(f"Invite to workspace {workspace_id} error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/kick/{member_id}")
async def kick_member(workspace_id: int, member_id: int, data: KickRequest = KickRequest()):
    """Kick a member from workspace"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
    try:
        manager = WorkspaceManager()
        result = manager.kick_member(workspace_id, member_id, data.reason)
        return result
    except Exception as e:
        logger.error(f"Kick member {member_id} from workspace {workspace_id} error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/check-ban")
async def check_ban(workspace_id: int):
    """Check for ban emails related to workspace"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
    try:
        manager = WorkspaceManager()
        result = manager.check_ban_emails(workspace_id)
        return result
    except Exception as e:
        logger.error(f"Check ban for workspace {workspace_id} error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/redistribute")
async def redistribute(workspace_id: int):
    """Redistribute members from this workspace to others"""
    with get_db() as db:
        ws = crud.get_workspace_by_id(db, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace не найден")
    try:
        manager = WorkspaceManager()
        result = manager.redistribute_members(workspace_id)
        return result
    except Exception as e:
        logger.error(f"Redistribute workspace {workspace_id} error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
