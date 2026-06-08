"""用户认证与权限管理 API"""

import asyncio
import re
from typing import List, Optional
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select

from backend.core.auth_manager import get_auth_manager, get_permission_manager
from backend.core.config import settings
from backend.core.security import verify_token
from backend.core.sms_service import get_sms_service
from backend.database.models import Permission, Role
from backend.database.session import get_db_session
from backend.memory.redis_client import redis_conn
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


def _github_request(method: str, url: str, **kwargs) -> requests.Response:
    """向 GitHub API 发请求，Windows 兼容（跳过本地开发证书验证）。"""
    import warnings

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    logger.info("_github_request v2: %s %s (verify=False)", method, url)
    return requests.request(method, url, timeout=10, verify=False, **kwargs)


def _validate_password_strength(password: str) -> None:
    """校验密码强度

    Args:
        password: 明文密码

    Raises:
        HTTPException: 密码不符合强度要求
    """
    errors = []
    if len(password) < 8:
        errors.append("密码长度至少8位")
    if not re.search(r"[a-z]", password):
        errors.append("密码需包含小写字母")
    if not re.search(r"[A-Z]", password):
        errors.append("密码需包含大写字母")
    if not re.search(r"[0-9]", password):
        errors.append("密码需包含数字")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", password):
        errors.append("密码需包含特殊字符")

    if errors:
        raise HTTPException(
            status_code=400,
            detail={"error": "密码强度不足", "details": errors},
        )


async def _get_client_identifier(request: Request) -> str:
    """获取客户端标识符（IP + 端点组合）"""
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    return client_ip


async def _check_login_rate_limit(request: Request) -> None:
    """检查登录/注册操作是否被限流

    Raises:
        HTTPException: 请求过于频繁
    """
    client_id = await _get_client_identifier(request)
    rate_key = f"login_rate:{client_id}"

    try:
        client = await redis_conn.get_client()
        attempts = await client.get(rate_key)
        if attempts and int(attempts) >= settings.login_max_attempts:
            ttl = await client.ttl(rate_key)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "请求过于频繁",
                    "message": f"请{ttl}秒后再试",
                    "retry_after": ttl,
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"登录限流检查失败（降级放行）: {e}")
        return


async def _record_login_attempt(request: Request) -> None:
    """记录登录/注册尝试"""
    client_id = await _get_client_identifier(request)
    rate_key = f"login_rate:{client_id}"

    try:
        client = await redis_conn.get_client()
        await client.incr(rate_key)
        await client.expire(rate_key, settings.login_lockout_minutes * 60)
    except Exception as e:
        logger.warning(f"记录登录尝试失败: {e}")


class SmsSendRequest(BaseModel):
    """发送短信验证码请求"""

    phone: str = Field(..., min_length=11, max_length=11)


class PhoneLoginRequest(BaseModel):
    """手机号登录请求"""

    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=6, max_length=6)


class PhoneRegisterRequest(BaseModel):
    """手机号注册请求"""

    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=6, max_length=6)
    password: Optional[str] = Field(None, min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """校验密码强度（可选）"""
        if v is not None:
            _validate_password_strength(v)
        return v


class RegisterRequest(BaseModel):
    """用户注册请求"""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """校验密码强度"""
        _validate_password_strength(v)
        return v


class LoginRequest(BaseModel):
    """用户登录请求"""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """令牌响应"""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class UserInfo(BaseModel):
    """用户信息"""

    id: int
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    roles: List[str]
    permissions: List[str]


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""

    refresh_token: str


class AssignRoleRequest(BaseModel):
    """分配角色请求"""

    user_id: int
    role_name: str


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    """获取当前用户ID"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
        )

    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌无效",
            )
        return int(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
        )


def require_permission(permission_name: str):
    """权限依赖装饰器"""

    async def dependency(user_id: int = Depends(get_current_user_id)):
        permission_manager = get_permission_manager()
        has_perm = await permission_manager.has_permission(user_id, permission_name)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {permission_name}",
            )
        return user_id

    return dependency


@router.post("/register")
async def register(request: RegisterRequest, req: Request):
    """用户注册"""
    # 限流检查
    await _check_login_rate_limit(req)

    auth_manager = get_auth_manager()
    result = await auth_manager.register_user(
        username=request.username,
        email=request.email,
        password=request.password,
    )

    if not result.get("success"):
        await _record_login_attempt(req)
        raise HTTPException(status_code=400, detail=result.get("error"))

    logger.info(f"用户注册成功: {request.username}")
    return {"message": "注册成功", "user_id": result.get("user_id")}


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, req: Request):
    """用户登录"""
    # 限流检查
    await _check_login_rate_limit(req)

    auth_manager = get_auth_manager()
    result = await auth_manager.login_user(
        email=request.email,
        password=request.password,
    )

    if not result.get("success"):
        await _record_login_attempt(req)
        raise HTTPException(status_code=401, detail=result.get("error"))

    return TokenResponse(
        access_token=result.get("access_token"),
        refresh_token=result.get("refresh_token"),
    )


@router.post("/refresh")
async def refresh_token(request: RefreshTokenRequest):
    """刷新访问令牌"""
    auth_manager = get_auth_manager()
    result = await auth_manager.refresh_token(request.refresh_token)

    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error"))

    return TokenResponse(access_token=result.get("access_token"))


@router.get("/me", response_model=UserInfo)
async def get_current_user(user_id: int = Depends(get_current_user_id)):
    """获取当前用户信息"""
    auth_manager = get_auth_manager()
    permission_manager = get_permission_manager()

    user = await auth_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    roles = await permission_manager.get_user_roles(user_id)
    permissions = await permission_manager.get_user_permissions(user_id)

    return UserInfo(
        id=user.id,
        username=user.username,
        email=user.email,
        phone=getattr(user, "phone", None),
        roles=roles,
        permissions=permissions,
    )


@router.post("/roles/assign")
async def assign_role(
    request: AssignRoleRequest,
    user_id: int = Depends(require_permission("admin:user:manage")),
):
    """为用户分配角色（需要管理员权限）"""
    permission_manager = get_permission_manager()
    success = await permission_manager.assign_role_to_user(
        user_id=request.user_id,
        role_name=request.role_name,
    )

    if not success:
        raise HTTPException(status_code=400, detail="分配角色失败")

    return {"message": "角色分配成功"}


@router.get("/roles")
async def list_roles(user_id: int = Depends(get_current_user_id)):
    """获取所有角色列表"""
    async with get_db_session() as session:
        result = await session.execute(select(Role))
        roles = result.scalars().all()

        return [
            {
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "is_active": role.is_active,
            }
            for role in roles
        ]


@router.get("/permissions")
async def list_permissions(user_id: int = Depends(get_current_user_id)):
    """获取所有权限列表"""
    async with get_db_session() as session:
        result = await session.execute(select(Permission))
        permissions = result.scalars().all()

        return [
            {
                "id": perm.id,
                "name": perm.name,
                "description": perm.description,
                "resource": perm.resource,
                "action": perm.action,
            }
            for perm in permissions
        ]


@router.post("/sms/send")
async def send_sms_code(request: SmsSendRequest):
    """发送短信验证码"""
    sms_service = get_sms_service()
    success = await sms_service.send_sms_code(request.phone)

    if not success:
        raise HTTPException(status_code=429, detail="发送过于频繁，请稍后再试")

    return {"message": "验证码发送成功"}


@router.post("/login/phone", response_model=TokenResponse)
async def login_with_phone(request: PhoneLoginRequest, req: Request):
    """手机号验证码登录"""
    # 限流检查
    await _check_login_rate_limit(req)

    sms_service = get_sms_service()
    auth_manager = get_auth_manager()

    # 验证验证码
    if not sms_service.verify_sms_code(request.phone, request.code):
        await _record_login_attempt(req)
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 检查用户是否存在
    result = await auth_manager.login_with_phone(request.phone)

    if not result.get("success"):
        await _record_login_attempt(req)
        raise HTTPException(status_code=404, detail=result.get("error"))

    return TokenResponse(
        access_token=result.get("access_token"),
        refresh_token=result.get("refresh_token"),
    )


@router.post("/register/phone")
async def register_with_phone(request: PhoneRegisterRequest, req: Request):
    """手机号注册"""
    # 限流检查
    await _check_login_rate_limit(req)

    sms_service = get_sms_service()
    auth_manager = get_auth_manager()

    # 验证验证码
    if not sms_service.verify_sms_code(request.phone, request.code):
        await _record_login_attempt(req)
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 注册用户
    result = await auth_manager.register_with_phone(phone=request.phone, password=request.password)

    if not result.get("success"):
        await _record_login_attempt(req)
        raise HTTPException(status_code=400, detail=result.get("error"))

    logger.info(f"手机号注册成功: {request.phone}")
    return {"message": "注册成功", "user_id": result.get("user_id")}


@router.get("/github/redirect")
async def github_login_redirect():
    """重定向到 GitHub 授权页面"""
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GitHub OAuth 未配置")

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": "user:email",
        "response_type": "code",
    }

    github_auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    return RedirectResponse(url=github_auth_url)


@router.get("/github/callback")
async def github_callback(code: str):
    """GitHub OAuth 回调处理"""
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=500, detail="GitHub OAuth 未配置")

    loop = asyncio.get_event_loop()

    try:
        # 1. 获取 GitHub access token
        token_response = await loop.run_in_executor(
            None,
            lambda: _github_request(
                "POST",
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_redirect_uri,
                },
                headers={"Accept": "application/json"},
            ),
        )
        token_data = token_response.json()

        if "error" in token_data:
            raise HTTPException(status_code=400, detail=token_data.get("error_description", token_data["error"]))

        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="获取 access token 失败")

        # 2. 获取 GitHub 用户信息
        user_response = await loop.run_in_executor(
            None,
            lambda: _github_request(
                "GET",
                "https://api.github.com/user",
                headers={"Authorization": f"token {access_token}"},
            ),
        )
        user_data = user_response.json()

        # 3. 获取 GitHub 用户邮箱
        email_response = await loop.run_in_executor(
            None,
            lambda: _github_request(
                "GET",
                "https://api.github.com/user/emails",
                headers={"Authorization": f"token {access_token}"},
            ),
        )
        emails = email_response.json()
        email = next((e["email"] for e in emails if e["primary"]), None) or user_data.get("email")

        auth_manager = get_auth_manager()
        result = await auth_manager.login_with_oauth(
            provider="github", provider_id=str(user_data.get("id")), username=user_data.get("login"), email=email
        )

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        logger.info(f"GitHub 登录成功: {user_data.get('login')}")

        frontend_callback_url = (
            f"{settings.frontend_url}/github/callback"
            f"?access_token={result.get('access_token')}"
            f"&refresh_token={result.get('refresh_token')}"
        )
        return RedirectResponse(url=frontend_callback_url)

    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub OAuth 请求失败: {str(e)}")
        raise HTTPException(status_code=500, detail="GitHub 认证请求失败")
    except Exception as e:
        logger.error(f"GitHub OAuth 处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail="GitHub 认证处理失败")
