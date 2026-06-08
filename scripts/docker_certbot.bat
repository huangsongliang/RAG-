@echo off
REM ==========================================
REM Docker Certbot 证书脚本 (跨平台方案)
REM 不依赖 Certbot Windows 版本
REM ==========================================

setlocal enabledelayedexpansion

echo ==========================================
echo Docker Certbot 证书管理工具
echo ==========================================
echo.

REM 配置信息 - 请根据实际情况修改
set DOMAIN=your-domain.com
set EMAIL=your-email@example.com
set CERT_DIR=%~dp0..\ssl
set ACME_DIR=%~dp0..\acme

REM 创建证书目录
if not exist "%CERT_DIR%" mkdir "%CERT_DIR%"
if not exist "%ACME_DIR%" mkdir "%ACME_DIR%"

echo 配置信息:
echo   域名: %DOMAIN%
echo   邮箱: %EMAIL%
echo   证书目录: %CERT_DIR%
echo.

REM 检查 Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未安装 Docker！
    echo 请先安装 Docker Desktop: https://docs.docker.com/desktop/install/windows-install/
    pause
    exit /b 1
)

echo [1/3] 使用 Docker Certbot 获取证书...
echo.

REM 使用Neilpang/acme.sh Docker镜像 (推荐)
REM 或使用 certbot/certbot 官方镜像

echo 请选择操作:
echo 1. 获取新证书
echo 2. 续期现有证书
echo 3. 仅测试证书获取
echo.
set /p CHOICE="请输入选项 (1/2/3): "

if "%CHOICE%"=="1" (
    echo 获取新证书...
    echo.
    echo [注意] 需要暂时停止占用 80 端口的服务
    echo.
    set /p CONFIRM="是否继续? (y/n): "
    if /i not "%CONFIRM%"=="y" exit /b 0

    REM 使用 standalone 模式获取证书
    docker run --rm -it ^
        -v "%ACME_DIR%:/acme.sh" ^
        -p 80:80 ^
        neilpang/acme.sh ^
        --issue -d %DOMAIN% -d www.%DOMAIN% ^
        --httpport 80 ^
        --keylength 2048 ^
        --email %EMAIL% ^
        --standalone ^
        --force

    if %errorlevel% neq 0 (
        echo [错误] 证书获取失败！
        pause
        exit /b 1
    )
)

if "%CHOICE%"=="2" (
    echo 续期证书...
    docker run --rm -it ^
        -v "%ACME_DIR%:/acme.sh" ^
        -p 80:80 ^
        neilpang/acme.sh ^
        --renew -d %DOMAIN% -d www.%DOMAIN% ^
        --httpport 80
)

if "%CHOICE%"=="3" (
    echo 测试模式...
    docker run --rm -it ^
        -v "%ACME_DIR%:/acme.sh" ^
        -v "%CERT_DIR%:/output" ^
        -p 80:80 ^
        neilpang/acme.sh ^
        --issue -d %DOMAIN% -d www.%DOMAIN% ^
        --httpport 80 ^
        --test ^
        --keylength 2048 ^
        --email %EMAIL% ^
        --standalone
)

if %errorlevel% neq 0 (
    echo [错误] 操作失败！
    pause
    exit /b 1
)

echo.
echo [2/3] 安装证书到项目目录...
echo.

REM acme.sh 默认安装位置
set ACME_CERT_PATH=%ACME_DIR%\ca\%DOMAIN%
set ACME_KEY_PATH=%ACME_DIR%\ca\%DOMAIN%

if exist "%ACME_CERT_PATH%" (
    copy /Y "%ACME_CERT_PATH%\fullchain.cer" "%CERT_DIR%\fullchain.pem"
    copy /Y "%ACME_CERT_PATH%\%DOMAIN%.key" "%CERT_DIR%\privkey.pem"

    if %errorlevel% equ 0 (
        echo [成功] 证书已复制到 ssl 目录
    ) else (
        echo [警告] 证书文件可能位于其他位置
    )
) else (
    echo [提示] 请手动从 acme.sh 目录复制证书
    echo acme.sh 目录: %ACME_DIR%
)

echo.
echo [3/3] 配置自动续期...
echo.

REM 创建自动续期脚本
(
    echo @echo off
    echo REM 自动证书续期脚本
    echo REM 由系统任务计划程序调用
    echo.
    echo docker run --rm -v %CD%\acme:/acme.sh -p 80:80 neilpang/acme.sh --renew -d %DOMAIN% -d www.%DOMAIN% --httpport 80
    echo if %%errorlevel%% equ 0 docker exec sushi-nginx nginx -s reload
) > "%~dp0auto_renew_cert.bat"

echo 已创建自动续期脚本: auto_renew_cert.bat
echo.
echo 设置自动续期:
echo 1. 打开任务计划程序
echo 2. 创建基本任务
echo 3. 设置触发器: 每月
echo 4. 操作: 运行脚本 auto_renew_cert.bat
echo.

echo ==========================================
echo 操作完成！
echo ==========================================
echo.
echo 证书位置:
echo   - 私钥: %CERT_DIR%\privkey.pem
echo   - 证书: %CERT_DIR%\fullchain.pem
echo.
echo acme.sh 数据: %ACME_DIR%
echo.
pause
