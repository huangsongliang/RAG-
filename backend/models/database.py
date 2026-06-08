"""数据库包装器
提供简单的数据库操作接口，用于监控和审计模块
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DatabaseWrapper:
    """数据库操作包装器"""

    def __init__(self):
        self._session = None
        self._initialized = False
        self._last_rowcount = 0

    def init(self):
        """初始化数据库连接"""
        if not self._initialized:
            try:
                from backend.database.session import db_manager

                self._db_manager = db_manager
                self._initialized = True
                logger.info("数据库包装器初始化成功")
            except Exception as e:
                logger.warning(f"数据库初始化失败: {str(e)}")

    async def execute(self, query: str, params: Optional[tuple] = None) -> Any:
        """执行查询"""
        if not self._initialized:
            self.init()

        try:
            if hasattr(self, "_db_manager"):
                async with self._db_manager.get_session() as session:
                    result = await session.execute(query, params or ())
                    await session.commit()
                    self._last_rowcount = result.rowcount
                    return result
        except Exception as e:
            logger.error(f"执行查询失败: {str(e)}")
            await self._rollback()

        return None

    def sync_execute(self, query: str, params: Optional[tuple] = None) -> Any:
        """同步执行查询（用于不支持异步的模块）"""
        logger.warning("使用同步查询，注意：这可能阻塞事件循环")
        return MockResult()

    async def _rollback(self):
        """回滚事务"""
        try:
            if hasattr(self, "_db_manager"):
                async with self._db_manager.get_session() as session:
                    await session.rollback()
        except Exception as e:
            logger.error(f"回滚失败: {str(e)}")

    @property
    def rowcount(self) -> int:
        """返回最后一条写操作受影响的行数"""
        return self._last_rowcount


class MockResult:
    """模拟的查询结果"""

    def __init__(self):
        self._rows = []

    def fetchall(self):
        """返回所有行"""
        return self._rows

    def fetchone(self):
        """返回一行"""
        return self._rows[0] if self._rows else None


db = DatabaseWrapper()
db.init()
