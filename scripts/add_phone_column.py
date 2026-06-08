"""
添加 phone 列到 users 表的迁移脚本
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.session import get_db_session
from sqlalchemy import text


async def add_phone_column():
    """添加 phone 列"""
    print("开始添加 phone 列...")

    async with get_db_session() as session:
        try:
            # 检查 phone 列是否已存在
            check_query = text("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'phone'
            """)
            result = await session.execute(check_query)
            count = result.scalar_one_or_none()

            if count and count > 0:
                print("phone 列已存在，无需添加")
                return True

            # 添加 phone 列
            add_column_query = text("""
                ALTER TABLE users
                ADD COLUMN phone VARCHAR(20) UNIQUE
            """)
            await session.execute(add_column_query)
            await session.commit()

            print("✅ phone 列添加成功！")
            return True

        except Exception as e:
            print(f"❌ 添加 phone 列失败: {e}")
            await session.rollback()
            return False


if __name__ == "__main__":
    success = asyncio.run(add_phone_column())
    sys.exit(0 if success else 1)
