@echo off
REM ==========================================
REM ACME.sh 证书获取脚本 (Windows)
REM 使用 Git Bash 或 WSL 运行 acme.sh
REM ==========================================

setlocal enabledelayedexpansion

echo ==========================================
echo ACME.sh 证书获取工具
echo ==========================================
echo.

REM 检查前置条件
echo [检查] 验证前置条件...
echo.

REM 检查 Git Bash
where bash >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Git Bash 已安装
    set "BASH=bash"
) else (
    echo [警告] 未找到 Git Bash
    echo 请安装 Git for Windows: https://git-scm.com/download/win
    echo 或使用 WSL
)

REM 检查 WSL
wsl --status >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] WSL 已安装
    echo 可以使用 WSL 运行 acme.sh
)

echo.
echo 请选择运行环境:
echo 1. Git Bash
echo 2. WSL (Windows Subsystem for Linux)
echo 3. 仅生成配置示例
echo.
set /p CHOICE="请输入选项 (1/2/3): "

REM 设置证书目录
set PROJECT_DIR=%~dp0..
set CERT_DIR=%PROJECT_DIR%\ssl
if not exist "%CERT_DIR%" mkdir "%CERT_DIR%"

if "%CHOICE%"=="1" (
    echo 使用 Git Bash 运行...
    echo.
    echo [提示] 首次运行需要安装 acme.sh:
    echo   bash -c "curl https://get.acme.sh | sh -s email=your@email.com"
    echo.
    set /p DOMAIN="请输入域名 (例如: example.com): "
    set /p EMAIL="请输入邮箱: "

    REM 生成 Git Bash 命令
    echo.
    echo ==========================================
    echo 请在 Git Bash 中运行以下命令:
    echo ==========================================
    echo.
    echo # 1. 安装 acme.sh (如果尚未安装)
    echo curl https://get.acme.sh ^| sh -s email=%EMAIL%
    echo.
    echo # 2. 申请证书
    echo ~/.acme.sh/acme.sh --issue -d %DOMAIN% -d www.%DOMAIN% --webroot /var/www/html
    echo.
    echo # 3. 安装证书到项目目录
    echo ~/.acme.sh/acme.sh --install-cert -d %DOMAIN% --key-file "%PROJECT_DIR:\=/%/ssl/privkey.pem" --fullchain-file "%PROJECT_DIR:\=/%/ssl/fullchain.pem"
    echo.
    echo # 4. 自动续期已配置
    echo.
    pause
    exit /b 0
)

if "%CHOICE%"=="2" (
    echo 使用 WSL 运行...
    echo.
    set /p DOMAIN="请输入域名 (例如: example.com): "
    set /p EMAIL="请输入邮箱: "

    echo.
    echo ==========================================
    echo 请在 WSL 终端中运行以下命令:
    echo ==========================================
    echo.
    echo # 1. 安装 acme.sh
    echo curl https://get.acme.sh ^| sh -s email=%EMAIL%
    echo.
    echo # 2. 申请证书 (假设 Nginx 在 /var/www/html)
    echo ~/.acme.sh/acme.sh --issue -d %DOMAIN% -d www.%DOMAIN% --webroot /var/www/html
    echo.
    echo # 3. 安装证书
    echo sudo ~/.acme.sh/acme.sh --install-cert -d %DOMAIN% --key-file "/mnt/d/code/sushi_digital_human/ssl/privkey.pem" --fullchain-file "/mnt/d/code/sushi_digital_human/ssl/fullchain.pem"
    echo.
    echo # 4. 自动续期已配置
    echo.
    pause
    exit /b 0
)

if "%CHOICE%"=="3" (
    echo 生成配置示例...
    set /p DOMAIN="请输入域名: "
    set /p EMAIL="请输入邮箱: "

    echo.
    echo ==========================================
    echo ACME.sh 配置示例
    echo ==========================================
    echo.
    echo # 安装 acme.sh
    echo curl https://get.acme.sh ^| sh -s email=%EMAIL%
    echo.
    echo # HTTP 方式申请证书 (需要 80 端口)
    echo ~/.acme.sh/acme.sh --issue -d %DOMAIN% -d www.%DOMAIN% --standalone
    echo.
    echo # 或 DNS 方式 (不需要开放端口)
    echo ~/.acme.sh/acme.sh --issue --dns -d %DOMAIN% -d www.%DOMAIN%
    echo.
    echo # 安装证书
    echo ~/.acme.sh/acme.sh --install-cert -d %DOMAIN% --key-file ./ssl/privkey.pem --fullchain-file ./ssl/fullchain.pem --reloadcmd "docker exec sushi-nginx nginx -s reload"
    echo.
    echo # acme.sh 会自动添加 cron 任务实现自动续期
    echo crontab -l ^| grep acme.sh
    echo.
    pause
    exit /b 0
)

echo [错误] 无效选项
pause
