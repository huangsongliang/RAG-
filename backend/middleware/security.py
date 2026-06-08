"""
安全中间件模块
提供XSS防护、点击劫持防护、CSP、SQL注入防护等安全功能
"""

import re

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from backend.utils.logger import get_logger

logger = get_logger(__name__)


# 危险的SQL模式 - 用于检测潜在的SQL注入
# 注意：不拦截单独的引号字符，避免影响正常聊天
# 只匹配 SQL 关键字和可疑模式
DANGEROUS_SQL_PATTERNS = [
    r"(union\s+select|insert\s+into|update\s+\w+\s+set|delete\s+from|drop\s+table|alter\s+table|create\s+table)",
    r"or\s+\d+\s*=\s*\d+",
    r"and\s+\d+\s*=\s*\d+",
    r"--|;",
    r"/\*.*\*/",
    r"exec\s+\w+",
    r"sp_\w+",
    r"xp_\w+",
    r"declare\s+\w+",
    r"cast\(",
    r"convert\(",
    r"waitfor\s+delay",
]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件 - 添加安全响应头"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # 防止点击劫持
        response.headers["X-Frame-Options"] = "DENY"

        # 防止MIME类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS防护
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 强制使用HTTPS (HSTS) - 建议生产环境使用
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # 内容安全策略
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self';"
        )

        # 引用策略
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 权限策略
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), autoplay=()"

        return response


class SQLInjectionProtectionMiddleware(BaseHTTPMiddleware):
    """SQL注入防护中间件"""

    def __init__(self, app):
        super().__init__(app)
        self._sql_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in DANGEROUS_SQL_PATTERNS]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 检查查询参数
        for key, value in request.query_params.items():
            if self._has_suspicious_pattern(value):
                logger.warning(f"潜在的SQL注入尝试: {key}={value}")
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Request contains suspicious patterns"}
                )

        # 检查请求体
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.json()
                await request.body()  # 重新读取body
                if isinstance(body, dict):
                    for key, value in body.items():
                        if isinstance(value, str) and self._has_suspicious_pattern(value):
                            logger.warning(f"潜在的SQL注入尝试: {key}={value}")
                            return JSONResponse(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                content={"detail": "Request contains suspicious patterns"},
                            )
            except Exception:
                logger.debug("无法解析请求体进行 SQL 注入检测：非 JSON 请求体或流式请求")

        response = await call_next(request)
        return response

    def _has_suspicious_pattern(self, text: str) -> bool:
        """检查文本是否包含可疑的SQL模式"""
        text_lower = text.lower()
        for pattern in self._sql_patterns:
            if pattern.search(text_lower):
                return True
        return False


class XSSProtectionMiddleware(BaseHTTPMiddleware):
    """XSS防护中间件"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 对查询参数进行验证
        for key, value in request.query_params.items():
            if self._has_xss_pattern(value):
                logger.warning(f"潜在的XSS尝试: {key}={value}")

        response = await call_next(request)
        return response

    def _has_xss_pattern(self, text: str) -> bool:
        """检查XSS模式"""
        xss_patterns = [
            r"<script[^>]*>",
            r"javascript:",
            r"on\w+\s*=",
            r"eval\(",
            r"expression\(",
            r"document\.",
            r"window\.",
            r"iframe",
            r"alert\(",
        ]

        text_lower = text.lower()
        for pattern in xss_patterns:
            if re.search(pattern, text_lower):
                return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件 - 基于Redis的令牌桶算法"""

    def __init__(self, app):
        super().__init__(app)
        # 使用现有的rate_limiter
        from backend.utils.rate_limiter import rate_limiter

        self._limiter = rate_limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 对特殊路径跳过限流
        skip_paths = ["/health", "/docs", "/redoc", "/openapi.json"]
        if request.url.path in skip_paths:
            return await call_next(request)

        # 获取客户端信息
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")

        # 检查限流
        allowed = await self._limiter.check(client_ip, request.url.path)
        if not allowed:
            logger.warning(f"请求被限流: {client_ip} - {request.url.path}")
            remaining_info = await self._limiter.get_remaining(client_ip, request.url.path)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests",
                    "message": "请求过于频繁，请稍后重试",
                    "remaining": remaining_info["remaining"],
                    "reset_in": remaining_info["reset_in"],
                },
                headers={
                    "Retry-After": str(remaining_info["reset_in"]),
                    "X-RateLimit-Remaining": str(remaining_info["remaining"]),
                },
            )

        response = await call_next(request)
        return response


def sanitize_input(text: str) -> str:
    """清洗用户输入，防止XSS和SQL注入"""
    if not text or not isinstance(text, str):
        return text

    # 移除危险字符
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace('"', "&quot;").replace("'", "&#x27;")
    text = text.replace("/", "&#x2F;").replace("\\", "&#x5C;")

    # 移除多余的空格
    text = re.sub(r"\s+", " ", text).strip()

    return text


def validate_email(email: str) -> bool:
    """验证邮箱格式"""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_password(password: str) -> dict:
    """验证密码强度"""
    result = {"valid": False, "errors": [], "strength": "weak"}

    if len(password) < 8:
        result["errors"].append("密码长度至少8位")
    if not re.search(r"[a-z]", password):
        result["errors"].append("密码需要包含小写字母")
    if not re.search(r"[A-Z]", password):
        result["errors"].append("密码需要包含大写字母")
    if not re.search(r"[0-9]", password):
        result["errors"].append("密码需要包含数字")
    if not re.search(r"[!@#$%^&*()_+=-]", password):
        result["errors"].append("密码需要包含特殊字符")

    if not result["errors"]:
        result["valid"] = True
        # 计算强度
        strength_score = 0
        if len(password) >= 12:
            strength_score += 2
        elif len(password) >= 8:
            strength_score += 1
        if re.search(r"[a-z]", password):
            strength_score += 1
        if re.search(r"[A-Z]", password):
            strength_score += 1
        if re.search(r"[0-9]", password):
            strength_score += 1
        if re.search(r"[!@#$%^&*()_+=-]", password):
            strength_score += 2

        if strength_score >= 6:
            result["strength"] = "strong"
        elif strength_score >= 4:
            result["strength"] = "medium"

    return result
