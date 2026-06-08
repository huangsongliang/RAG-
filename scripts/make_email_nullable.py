"""
修改 email 字段允许为空的迁移脚本
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.session import get_db_session
from sqlalchemy import text


async def make_email_nullable():
    """修改 email 字段允许为空"""
    print("开始修改 email 字段...")

    async with get_db_session() as session:
        try:
            # 修改 email 字段允许为空
            alter_query = text("""
                ALTER TABLE users
                MODIFY COLUMN email VARCHAR(100) NULL
            """)
            await session.execute(alter_query)
            await session.commit()

            print("✅ email 字段已修改为允许为空！")
            return True

        except Exception as e:
            print(f"❌ 修改失败: {e}")
            await session.rollback()
            return False


if __name__ == "__main__":
    success = asyncio.run(make_email_nullable())
    sys.exit(0 if success else 1)
