@echo off
REM MySQL数据库备份脚本 - Windows版本
REM 企业级智能文档问答平台

echo ========================================
echo 企业级智能文档问答平台 - 数据库备份
echo ========================================
echo.

REM 配置变量
set BACKUP_DIR=%~dp0..\backup\mysql
set DATE=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set DB_NAME=enterprise_doc_qa
set DB_USER=testuser
set DB_PASSWORD=testpassword
set DB_PORT=3307
set RETENTION_DAYS=7

REM 处理时间中的空格
set DATE=%DATE: =0%

REM 创建备份目录
if not exist "%BACKUP_DIR%" (
    echo 创建备份目录: %BACKUP_DIR%
    mkdir "%BACKUP_DIR%"
)

echo.
echo 开始备份数据库...
echo 数据库: %DB_NAME%
echo 备份目录: %BACKUP_DIR%
echo 备份文件名: %DB_NAME%_%DATE%.sql
echo.

REM 执行备份
docker exec enterprise-doc-qa-mysql-test mysqldump -u%DB_USER% -p%DB_PASSWORD% %DB_NAME% > "%BACKUP_DIR%\%DB_NAME%_%DATE%.sql"

if %ERRORLEVEL% EQU 0 (
    echo ✓ 备份成功!
    echo.

    REM 压缩备份文件
    echo 压缩备份文件...
    powershell -Command "Compress-Archive -Path '%BACKUP_DIR%\%DB_NAME%_%DATE%.sql' -DestinationPath '%BACKUP_DIR%\%DB_NAME%_%DATE%.zip' -Force"

    if %ERRORLEVEL% EQU 0 (
        echo ✓ 压缩成功!
        del "%BACKUP_DIR%\%DB_NAME%_%DATE%.sql"

        REM 清理旧备份
        echo.
        echo 清理 %RETENTION_DAYS% 天前的备份...
        forfiles /P "%BACKUP_DIR%" /M *.zip /D -%RETENTION_DAYS% /C "cmd /c del @path"
        echo ✓ 清理完成!

        echo.
        echo ========================================
        echo 备份完成!
        echo ========================================
        echo 备份文件: %DB_NAME%_%DATE%.zip
        echo 备份目录: %BACKUP_DIR%
    ) else (
        echo ✗ 压缩失败!
    )
) else (
    echo ✗ 备份失败!
)

echo.
pause
