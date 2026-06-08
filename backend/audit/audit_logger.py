"""审计日志模块
记录所有系统操作，支持查询和分析
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.models.database import db
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class AuditAction(str, Enum):
    """审计操作类型"""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PERMISSION_CHANGE = "permission_change"
    SYSTEM_CONFIG = "system_config"
    EXPORT = "export"
    IMPORT = "import"
    SHARE = "share"
    DOWNLOAD = "download"


class AuditCategory(str, Enum):
    """审计类别"""

    USER = "user"
    DOCUMENT = "document"
    PERMISSION = "permission"
    SYSTEM = "system"
    SECURITY = "security"
    DATA = "data"


class AuditLogger:
    """审计日志记录器"""

    def __init__(self):
        self.buffer_size = 100
        self.buffer = []

    def log(
        self,
        action: AuditAction,
        category: AuditCategory,
        user_id: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "success",
    ) -> str:
        """记录审计日志"""
        log_id = str(uuid4())

        log_entry = {
            "id": log_id,
            "action": action.value,
            "category": category.value,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "status": status,
            "created_at": datetime.now(),
        }

        self.buffer.append(log_entry)

        if len(self.buffer) >= self.buffer_size:
            try:
                asyncio.create_task(self._flush_buffer())
            except RuntimeError:
                pass  # 无运行中的事件循环，跳过刷新

        logger.info(f"审计日志: action={action}, user={user_id}, resource={resource_type}/{resource_id}")
        return log_id

    async def _flush_buffer(self):
        """刷新缓冲区到数据库"""
        if not self.buffer:
            return

        batch = self.buffer
        self.buffer = []

        try:
            for entry in batch:
                await db.execute(
                    """
                    INSERT INTO audit_logs (
                        id, action, category, user_id, resource_type, resource_id,
                        details, ip_address, user_agent, status, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entry["id"],
                        entry["action"],
                        entry["category"],
                        entry["user_id"],
                        entry["resource_type"],
                        entry["resource_id"],
                        str(entry["details"]) if entry["details"] else None,
                        entry["ip_address"],
                        entry["user_agent"],
                        entry["status"],
                        entry["created_at"],
                    ),
                )

            logger.info(f"审计日志刷新完成: {len(batch)} 条记录")

        except Exception as e:
            logger.error(f"审计日志刷新失败: {str(e)}")

    async def query(
        self,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        category: Optional[AuditCategory] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询审计日志"""
        try:
            conditions = []
            params = []

            if user_id:
                conditions.append("user_id = %s")
                params.append(user_id)

            if action:
                conditions.append("action = %s")
                params.append(action.value)

            if category:
                conditions.append("category = %s")
                params.append(category.value)

            if resource_type:
                conditions.append("resource_type = %s")
                params.append(resource_type)

            if resource_id:
                conditions.append("resource_id = %s")
                params.append(resource_id)

            if start_time:
                conditions.append("created_at >= %s")
                params.append(start_time)

            if end_time:
                conditions.append("created_at <= %s")
                params.append(end_time)

            if status:
                conditions.append("status = %s")
                params.append(status)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT id, action, category, user_id, resource_type, resource_id,
                       details, ip_address, user_agent, status, created_at
                FROM audit_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])

            result = await db.execute(query, tuple(params))

            logs = []
            for row in result.fetchall():
                logs.append(
                    {
                        "id": row[0],
                        "action": row[1],
                        "category": row[2],
                        "user_id": row[3],
                        "resource_type": row[4],
                        "resource_id": row[5],
                        "details": row[6],
                        "ip_address": row[7],
                        "user_agent": row[8],
                        "status": row[9],
                        "created_at": str(row[10]),
                    }
                )

            return logs

        except Exception as e:
            logger.error(f"查询审计日志失败: {str(e)}")
            return []

    async def get_user_activity(
        self,
        user_id: str,
        days: int = 7,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取用户活动日志"""
        start_time = datetime.now() - timedelta(days=days)
        return await self.query(
            user_id=user_id,
            start_time=start_time,
            limit=limit,
        )

    async def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取资源操作历史"""
        return await self.query(
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
        )

    async def get_failed_attempts(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取失败的操作"""
        start_time = datetime.now() - timedelta(hours=hours)
        return await self.query(
            status="failed",
            start_time=start_time,
            limit=limit,
        )

    async def get_security_events(
        self,
        days: int = 7,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取安全事件"""
        start_time = datetime.now() - timedelta(days=days)
        return await self.query(
            category=AuditCategory.SECURITY,
            start_time=start_time,
            limit=limit,
        )

    async def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """获取审计统计"""
        try:
            if not start_time:
                start_time = datetime.now() - timedelta(days=7)
            if not end_time:
                end_time = datetime.now()

            stats = {}

            result = await db.execute(
                """
                SELECT action, COUNT(*) as count
                FROM audit_logs
                WHERE created_at BETWEEN %s AND %s
                GROUP BY action
                """,
                (start_time, end_time),
            )
            stats["actions"] = {row[0]: row[1] for row in result.fetchall()}

            result = await db.execute(
                """
                SELECT category, COUNT(*) as count
                FROM audit_logs
                WHERE created_at BETWEEN %s AND %s
                GROUP BY category
                """,
                (start_time, end_time),
            )
            stats["categories"] = {row[0]: row[1] for row in result.fetchall()}

            result = await db.execute(
                """
                SELECT user_id, COUNT(*) as count
                FROM audit_logs
                WHERE created_at BETWEEN %s AND %s
                GROUP BY user_id
                ORDER BY count DESC
                LIMIT 10
                """,
                (start_time, end_time),
            )
            stats["top_users"] = [{"user_id": row[0], "count": row[1]} for row in result.fetchall()]

            result = await db.execute(
                """
                SELECT COUNT(*) FROM audit_logs
                WHERE created_at BETWEEN %s AND %s
                """,
                (start_time, end_time),
            )
            stats["total_count"] = result.fetchone()[0]

            result = await db.execute(
                """
                SELECT COUNT(*) FROM audit_logs
                WHERE created_at BETWEEN %s AND %s AND status = 'failed'
                """,
                (start_time, end_time),
            )
            stats["failed_count"] = result.fetchone()[0]

            return stats

        except Exception as e:
            logger.error(f"获取审计统计失败: {str(e)}")
            return {}

    async def export_logs(
        self,
        start_time: datetime,
        end_time: datetime,
        format: str = "json",
    ) -> List[Dict[str, Any]]:
        """导出审计日志"""
        return await self.query(
            start_time=start_time,
            end_time=end_time,
            limit=10000,
        )

    async def cleanup_old_logs(self, days: int = 90) -> int:
        """清理旧日志"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)

            result = await db.execute(
                """
                DELETE FROM audit_logs
                WHERE created_at < %s
                """,
                (cutoff_time,),
            )

            deleted_count = result.rowcount

            logger.info(f"审计日志清理完成: 删除 {deleted_count} 条旧记录")
            return deleted_count

        except Exception as e:
            logger.error(f"清理审计日志失败: {str(e)}")
            return 0


_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取审计日志记录器实例"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
        logger.info("审计日志记录器已初始化")
    return _audit_logger
