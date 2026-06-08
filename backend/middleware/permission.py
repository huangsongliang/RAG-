"""权限检查中间件和装饰器"""

import re
from functools import wraps
from typing import Callable, List, Optional

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt

from backend.auth.permission_manager import PermissionAction, PermissionResource, get_permission_manager
from backend.core.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# JWT 配置
ALGORITHM = "HS256"


def require_permission(
    resource_type: PermissionResource,
    resource_id_param: str = "resource_id",
    action: PermissionAction = PermissionAction.READ,
):
    """权限检查装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Optional[Request] = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="无法获取请求对象",
                )

            user_id = getattr(request.state, "user_id", None)
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="未认证",
                )

            resource_id = kwargs.get(resource_id_param)
            if not resource_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"缺少参数: {resource_id_param}",
                )

            perm_manager = get_permission_manager()
            has_permission = await perm_manager.check_permission(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=str(resource_id),
                action=action,
            )

            if not has_permission:
                logger.warning(
                    "权限不足: user=%s, resource=%s:%s, action=%s",
                    user_id,
                    resource_type,
                    resource_id,
                    action,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="权限不足",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(
    resource_type: PermissionResource,
    resource_id_param: str = "resource_id",
    actions: List[PermissionAction] = None,
):
    """要求任意权限的装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Optional[Request] = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="无法获取请求对象",
                )

            user_id = getattr(request.state, "user_id", None)
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="未认证",
                )

            resource_id = kwargs.get(resource_id_param)
            if not resource_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"缺少参数: {resource_id_param}",
                )

            perm_manager = get_permission_manager()

            for action in actions or [PermissionAction.READ]:
                has_permission = await perm_manager.check_permission(
                    user_id=user_id,
                    resource_type=resource_type,
                    resource_id=str(resource_id),
                    action=action,
                )
                if has_permission:
                    return await func(*args, **kwargs)

            logger.warning(
                f"权限不足: user={user_id}, resource={resource_type}:{resource_id}, required_actions={actions}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )

        return wrapper

    return decorator


def require_role(*role_names: str):
    """角色检查装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Optional[Request] = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="无法获取请求对象",
                )

            user_id = getattr(request.state, "user_id", None)
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="未认证",
                )

            user_roles = getattr(request.state, "roles", [])
            if not user_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="无角色权限",
                )

            has_role = any(role in role_names for role in user_roles)
            if not has_role:
                logger.warning(f"角色不足: user={user_id}, required_roles={role_names}, user_roles={user_roles}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="角色权限不足",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


class PermissionMiddleware:
    """权限检查中间件"""

    def __init__(self, app):
        self.app = app
        self.public_paths = [
            "/api/auth/login",
            "/api/auth/register",
            "/api/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if any(path.startswith(p) for p in self.public_paths):
            await self.app(scope, receive, send)
            return

        await self.app(scope, receive, send)


async def check_document_permission(
    user_id: str,
    document_id: str,
    action: PermissionAction = PermissionAction.READ,
) -> bool:
    """便捷函数：检查文档权限"""
    perm_manager = get_permission_manager()
    return await perm_manager.check_permission(
        user_id=user_id,
        resource_type=PermissionResource.DOCUMENT,
        resource_id=document_id,
        action=action,
    )


async def check_folder_permission(
    user_id: str,
    folder_id: str,
    action: PermissionAction = PermissionAction.READ,
) -> bool:
    """便捷函数：检查文件夹权限"""
    perm_manager = get_permission_manager()
    return await perm_manager.check_permission(
        user_id=user_id,
        resource_type=PermissionResource.FOLDER,
        resource_id=folder_id,
        action=action,
    )


async def grant_document_permission(
    user_id: str,
    document_id: str,
    action: PermissionAction,
    granted_by: str,
) -> bool:
    """便捷函数：授予文档权限"""
    perm_manager = get_permission_manager()
    return await perm_manager.grant_permission(
        user_id=user_id,
        resource_type=PermissionResource.DOCUMENT,
        resource_id=document_id,
        action=action,
        granted_by=granted_by,
    )


async def revoke_document_permission(
    user_id: str,
    document_id: str,
    action: PermissionAction,
) -> bool:
    """便捷函数：撤销文档权限"""
    perm_manager = get_permission_manager()
    return await perm_manager.revoke_permission(
        user_id=user_id,
        resource_type=PermissionResource.DOCUMENT,
        resource_id=document_id,
        action=action,
    )


# ==================== 统一认证中间件 ====================


class AuthMiddleware:
    """统一认证中间件 - 处理 JWT 认证和权限检查"""

    def __init__(self, app):
        self.app = app
        # 公共路径 - 不需要认证
        self.public_paths = {
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/logout",
            "/api/auth/refresh",
            "/api/auth/github/callback",
            "/api/auth/phone/send",
            "/api/auth/phone/verify",
            "/api/auth/reset-password/send",
            "/api/auth/reset-password/verify",
            "/api/auth/reset-password/confirm",
            "/health",
            "/health/liveness",
            "/health/readiness",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/",
        }
        # 公共前缀 - 以下前缀的路径都不需要认证
        self.public_prefixes = (
            "/docs",
            "/redoc",
            "/openapi.json",
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # 检查是否是公共路径
        if self._is_public_path(path):
            await self.app(scope, receive, send)
            return

        # 尝试解析 JWT token
        headers = dict(scope.get("headers", []))
        auth_header = None

        for key, value in headers.items():
            if key.lower() == b"authorization":
                auth_header = value.decode("utf-8")
                break

        user_info = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user_info = self._decode_jwt_token(token)

        # 如果没有有效token，设置匿名用户
        if not user_info:
            scope["user"] = {
                "user_id": None,
                "username": None,
                "roles": [],
                "is_authenticated": False,
            }
            scope["state"] = {"user_id": None, "roles": []}
            await self.app(scope, receive, send)
            return

        # 设置用户信息到 scope
        scope["user"] = {
            "user_id": user_info.get("sub"),
            "username": user_info.get("username"),
            "roles": user_info.get("roles", []),
            "is_authenticated": True,
        }
        scope["state"] = {
            "user_id": user_info.get("sub"),
            "roles": user_info.get("roles", []),
        }

        await self.app(scope, receive, send)

    def _is_public_path(self, path: str) -> bool:
        """检查路径是否是公共路径"""
        if path in self.public_paths:
            return True
        for prefix in self.public_prefixes:
            if path.startswith(prefix):
                return True
        return False

    def _decode_jwt_token(self, token: str) -> Optional[dict]:
        """解码 JWT token"""
        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[ALGORITHM],
            )
            return payload
        except JWTError as e:
            logger.debug(f"JWT 解码失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Token 解码异常: {str(e)}")
            return None


# ==================== 细粒度权限控制中间件 ====================


class RBACMiddleware:
    """基于角色的访问控制中间件"""

    def __init__(self, app):
        self.app = app
        self.perm_manager = None

        # 权限规则配置
        # 格式: [{"pattern": "路径模式", "methods": ["GET"], "resource_type": ..., "action": ...}]
        self.permission_rules = [
            # 文档管理权限
            {
                "pattern": r"^/api/documents/[^/]+$",
                "methods": ["GET"],
                "resource_type": PermissionResource.DOCUMENT,
                "action": PermissionAction.READ,
            },
            {
                "pattern": r"^/api/documents/[^/]+$",
                "methods": ["PUT", "PATCH"],
                "resource_type": PermissionResource.DOCUMENT,
                "action": PermissionAction.UPDATE,
            },
            {
                "pattern": r"^/api/documents/[^/]+$",
                "methods": ["DELETE"],
                "resource_type": PermissionResource.DOCUMENT,
                "action": PermissionAction.DELETE,
            },
            # 文件夹权限
            {
                "pattern": r"^/api/folders/[^/]+$",
                "methods": ["GET"],
                "resource_type": PermissionResource.FOLDER,
                "action": PermissionAction.READ,
            },
            {
                "pattern": r"^/api/folders/[^/]+$",
                "methods": ["PUT", "PATCH", "DELETE"],
                "resource_type": PermissionResource.FOLDER,
                "action": PermissionAction.UPDATE,
            },
            # 工作流权限
            {
                "pattern": r"^/api/workflows/[^/]+$",
                "methods": ["GET"],
                "resource_type": PermissionResource.WORKFLOW,
                "action": PermissionAction.READ,
            },
            {
                "pattern": r"^/api/workflows/[^/]+$",
                "methods": ["PUT", "PATCH", "DELETE", "POST"],
                "resource_type": PermissionResource.WORKFLOW,
                "action": PermissionAction.UPDATE,
            },
            # Agent 权限
            {
                "pattern": r"^/api/agents/[^/]+$",
                "methods": ["GET"],
                "resource_type": PermissionResource.AGENT,
                "action": PermissionAction.READ,
            },
            {
                "pattern": r"^/api/agents/[^/]+$",
                "methods": ["PUT", "PATCH", "DELETE"],
                "resource_type": PermissionResource.AGENT,
                "action": PermissionAction.UPDATE,
            },
        ]

        # 需要管理员角色的路径
        self.admin_paths = {
            r"^/api/permissions/",
            r"^/api/audit/",
            r"^/api/tracing/",
            r"^/api/alerts/",
            r"^/api/cicd/",
            r"^/api/deployment/",
        }

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # 公共路径跳过权限检查
        if self._is_public_path(path):
            await self.app(scope, receive, send)
            return

        # 获取用户信息
        user_info = scope.get("user", {})
        user_id = user_info.get("user_id")
        roles = user_info.get("roles", [])
        is_authenticated = user_info.get("is_authenticated", False)

        # 检查是否需要认证
        if not is_authenticated:
            # 对于需要认证的路径，返回未认证错误
            if not self._is_public_path(path):
                await self._send_error_response(send, 401, "未认证，请先登录")
                return

        # 检查管理员路径
        if self._requires_admin(path):
            if "admin" not in roles:
                await self._send_error_response(send, 403, "需要管理员权限")
                return

        # 检查细粒度权限
        permission_rule = self._match_permission_rule(path, method)
        if permission_rule:
            if not await self._check_resource_permission(user_id, permission_rule):
                await self._send_error_response(send, 403, "权限不足")
                return

        await self.app(scope, receive, send)

    def _is_public_path(self, path: str) -> bool:
        """检查路径是否是公共路径"""
        public_paths = {
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/logout",
            "/api/auth/refresh",
            "/api/auth/github/callback",
            "/health",
            "/health/liveness",
            "/health/readiness",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/",
        }
        if path in public_paths:
            return True
        if path.startswith("/docs") or path.startswith("/redoc"):
            return True
        return False

    def _requires_admin(self, path: str) -> bool:
        """检查路径是否需要管理员权限"""
        for pattern in self.admin_paths:
            if re.match(pattern, path):
                return True
        return False

    def _match_permission_rule(self, path: str, method: str) -> Optional[dict]:
        """匹配权限规则"""
        for entry in self.permission_rules:
            if re.match(entry["pattern"], path) and method in entry.get("methods", []):
                return entry
        return None

    async def _check_resource_permission(self, user_id: str, rule: dict) -> bool:
        """检查资源权限"""
        if not user_id:
            return False

        if not self.perm_manager:
            self.perm_manager = get_permission_manager()

        resource_type = rule.get("resource_type")
        action = rule.get("action")

        # 从路径中提取资源ID
        path = rule.get("path", "")
        resource_id = self._extract_resource_id(path)

        return await self.perm_manager.check_permission(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
        )

    def _extract_resource_id(self, path: str) -> str:
        """从路径中提取资源ID"""
        # 简单实现：提取最后一个路径段
        parts = path.strip("/").split("/")
        if len(parts) >= 3:
            return parts[2]
        return ""

    async def _send_error_response(self, send, status_code: int, detail: str):
        """发送错误响应"""
        import json

        response_body = json.dumps({"detail": detail}).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(response_body)).encode()),
        ]

        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": response_body,
            }
        )


# ==================== 依赖注入函数 ====================


async def get_current_user(request: Request) -> dict:
    """获取当前用户信息"""
    user_info = getattr(request.state, "user", {})
    return {
        "user_id": user_info.get("user_id"),
        "username": user_info.get("username"),
        "roles": user_info.get("roles", []),
        "is_authenticated": user_info.get("is_authenticated", False),
    }


async def require_authentication(request: Request):
    """依赖注入：要求用户已认证"""
    user_info = await get_current_user(request)
    if not user_info["is_authenticated"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未认证，请先登录",
        )
    return user_info


async def require_admin_role(request: Request):
    """依赖注入：要求管理员角色"""
    user_info = await require_authentication(request)
    if "admin" not in user_info["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user_info
