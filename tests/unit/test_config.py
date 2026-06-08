"""配置验证测试 - v1.2 补全

验证 pydantic-settings 的 field_validator 和 computed property：
- log_level 枚举白名单
- chroma_persist_dir 目录自动创建
- mysql_url / database_url 条件拼接与降级
"""

import os
from pathlib import Path

import pytest


class TestSettingsValidation:
    """Settings 字段验证测试"""

    def test_log_level_valid_values(self):
        """验证合法的 log_level 值"""
        from backend.core.config import Settings

        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            s = Settings(log_level=level)
            assert s.log_level == level

    def test_log_level_invalid_raises(self):
        """非法 log_level 应抛出验证错误"""
        from pydantic import ValidationError
        from backend.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(log_level="INVALID")

    def test_log_level_normalizes_to_upper(self):
        """log_level 自动转为大写（验证 validator 的 v.upper()）"""
        from backend.core.config import Settings

        s = Settings(log_level="debug")
        assert s.log_level == "DEBUG"  # valid 自动转为大写


    def test_chroma_persist_dir_default(self):
        """默认持久化目录"""
        from backend.core.config import Settings

        s = Settings()
        assert isinstance(s.chroma_persist_dir, Path)
        assert "chroma_db" in str(s.chroma_persist_dir)


    def test_chroma_persist_dir_creates_if_not_exists(self, tmp_path):
        """不存在的目录应自动创建"""
        from backend.core.config import Settings

        new_dir = tmp_path / "new_chroma"
        # 确保不存在
        if new_dir.exists():
            import shutil
            shutil.rmtree(str(new_dir))

        s = Settings(chroma_persist_dir=str(new_dir))
        assert Path(s.chroma_persist_dir).exists()

    def test_mysql_url_with_password(self):
        """mysql_url 属性：有密码时完整拼接"""
        from backend.core.config import Settings

        s = Settings(
            mysql_host="localhost",
            mysql_port=3306,
            mysql_user="root",
            mysql_password="secret",
            mysql_database="test_db",
        )
        url = s.mysql_url
        assert "mysql://root:secret@localhost:3306/test_db" in url

    def test_mysql_url_without_password(self):
        """mysql_url 属性：无密码时不包含密码段"""
        from backend.core.config import Settings

        s = Settings(
            mysql_host="localhost",
            mysql_port=3306,
            mysql_user="root",
            mysql_password="",
            mysql_database="test_db",
        )
        url = s.mysql_url
        assert ":@localhost" not in url
        assert "mysql://root@localhost:3306/test_db" in url

    def test_database_url_defaults_to_mysql(self):
        """默认情况下 database_url 应该是 MySQL URL"""
        from backend.core.config import Settings

        s = Settings(
            mysql_host="db.example.com",
            mysql_port=3307,
            mysql_user="app",
            mysql_password="pwd",
            mysql_database="sushi",
        )
        url = s.database_url
        assert "mysql+aiomysql://" in url

    def test_database_url_fallback_to_sqlite(self):
        """未配置 MySQL 主机时降级为 SQLite"""
        from backend.core.config import Settings

        s = Settings(mysql_host=None)  # 将主机设为 None 触发降级
        url = s.database_url
        assert "sqlite" in url



class TestSettingsDefaults:
    """Settings 默认值测试"""

    def test_default_app_version(self):
        from backend.core.config import Settings

        s = Settings()
        assert s.app_version == "1.0.0"


    def test_default_log_level(self):
        from backend.core.config import Settings

        s = Settings()
        assert s.log_level == "INFO"

    def test_default_redis_url(self):
        from backend.core.config import Settings

        s = Settings()
        assert "localhost" in s.redis_url
        assert "6379" in s.redis_url
