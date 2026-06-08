"""审计日志 API 路由"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.audit.audit_logger import AuditAction, AuditCategory, get_audit_logger
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/audit", tags=["审计日志"])


class AuditLogQuery(BaseModel):
    """审计日志查询"""

    user_id: Optional[str] = None
    action: Optional[str] = None
    category: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = None
    limit: int = 100
    offset: int = 0


def get_current_user_id(request: Request) -> str:
    """获取当前用户ID（示例）"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    return user_id


@router.get("/logs")
async def query_logs(
    user_id: Optional[str] = Query(None, description="用户ID"),
    action: Optional[str] = Query(None, description="操作类型"),
    category: Optional[str] = Query(None, description="类别"),
    resource_type: Optional[str] = Query(None, description="资源类型"),
    resource_id: Optional[str] = Query(None, description="资源ID"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    status: Optional[str] = Query(None, description="状态"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """查询审计日志"""
    try:
        audit_logger = get_audit_logger()

        logs = await audit_logger.query(
            user_id=user_id,
            action=AuditAction(action) if action else None,
            category=AuditCategory(category) if category else None,
            resource_type=resource_type,
            resource_id=resource_id,
            start_time=start_time,
            end_time=end_time,
            status=status,
            limit=limit,
            offset=offset,
        )

        return {
            "logs": logs,
            "count": len(logs),
            "limit": limit,
            "offset": offset,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"查询审计日志失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询审计日志失败: {str(e)}")


@router.get("/user/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    days: int = Query(7, ge=1, le=90, description="查询天数"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
):
    """获取用户活动日志"""
    try:
        audit_logger = get_audit_logger()
        logs = await audit_logger.get_user_activity(
            user_id=user_id,
            days=days,
            limit=limit,
        )

        return {
            "user_id": user_id,
            "days": days,
            "logs": logs,
            "count": len(logs),
        }

    except Exception as e:
        logger.error(f"获取用户活动失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取用户活动失败: {str(e)}")


@router.get("/resource/{resource_type}/{resource_id}/history")
async def get_resource_history(
    resource_type: str,
    resource_id: str,
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
):
    """获取资源操作历史"""
    try:
        audit_logger = get_audit_logger()
        logs = await audit_logger.get_resource_history(
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
        )

        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "logs": logs,
            "count": len(logs),
        }

    except Exception as e:
        logger.error(f"获取资源历史失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取资源历史失败: {str(e)}")


@router.get("/security/failed-attempts")
async def get_failed_attempts(
    hours: int = Query(24, ge=1, le=168, description="查询小时数"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
):
    """获取失败的操作"""
    try:
        audit_logger = get_audit_logger()
        logs = await audit_logger.get_failed_attempts(
            hours=hours,
            limit=limit,
        )

        return {
            "hours": hours,
            "logs": logs,
            "count": len(logs),
        }

    except Exception as e:
        logger.error(f"获取失败操作失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取失败操作失败: {str(e)}")


@router.get("/security/events")
async def get_security_events(
    days: int = Query(7, ge=1, le=90, description="查询天数"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
):
    """获取安全事件"""
    try:
        audit_logger = get_audit_logger()
        logs = await audit_logger.get_security_events(
            days=days,
            limit=limit,
        )

        return {
            "days": days,
            "logs": logs,
            "count": len(logs),
        }

    except Exception as e:
        logger.error(f"获取安全事件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取安全事件失败: {str(e)}")


@router.get("/statistics")
async def get_statistics(
    days: int = Query(7, ge=1, le=90, description="查询天数"),
):
    """获取审计统计"""
    try:
        audit_logger = get_audit_logger()
        start_time = datetime.now() - timedelta(days=days)

        stats = await audit_logger.get_statistics(
            start_time=start_time,
            end_time=datetime.now(),
        )

        return {
            "days": days,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "statistics": stats,
        }

    except Exception as e:
        logger.error(f"获取审计统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取审计统计失败: {str(e)}")


@router.get("/export")
async def export_logs(
    start_time: datetime = Query(..., description="开始时间"),
    end_time: datetime = Query(..., description="结束时间"),
    format: str = Query("json", description="导出格式"),
):
    """导出审计日志"""
    try:
        audit_logger = get_audit_logger()
        logs = await audit_logger.export_logs(
            start_time=start_time,
            end_time=end_time,
            format=format,
        )

        return {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "format": format,
            "count": len(logs),
            "logs": logs,
        }

    except Exception as e:
        logger.error(f"导出审计日志失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导出审计日志失败: {str(e)}")


@router.post("/cleanup")
async def cleanup_old_logs(
    days: int = Query(90, ge=30, le=365, description="保留天数"),
    current_user_id: str = Depends(get_current_user_id),
):
    """清理旧日志"""
    try:
        audit_logger = get_audit_logger()
        deleted_count = await audit_logger.cleanup_old_logs(days=days)

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "retained_days": days,
        }

    except Exception as e:
        logger.error(f"清理旧日志失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理旧日志失败: {str(e)}")


@router.get("/actions")
async def get_action_types():
    """获取操作类型列表"""
    return {"actions": [{"value": action.value, "name": action.name} for action in AuditAction]}


@router.get("/categories")
async def get_category_types():
    """获取类别列表"""
    return {"categories": [{"value": cat.value, "name": cat.name} for cat in AuditCategory]}
