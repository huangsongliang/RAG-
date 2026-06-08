"""FastAPI 主应用入口"""

import signal
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer

from backend.api import (
    agent_router,
    alerts_router,
    audit_router,
    auth_router,
    chart_router,
    chat_router,
    cicd_router,
    documents_router,
    knowledge_graph_router,
    link_parser_router,
    multimodal_router,
    notification_router,
    permission_router,
    plugins_router,
    summary_router,
    tracing_router,
    unified_chat_router,
    versioning_router,
    workflow_router,
)
from backend.api.versioning import VersionMiddleware
from backend.core.config import settings
from backend.database.session import async_initialize_database
from backend.middleware.security import (
    SecurityHeadersMiddleware,
    SQLInjectionProtectionMiddleware,
    XSSProtectionMiddleware,
)
from backend.utils.alerting import start_alerting, stop_alerting
from backend.utils.error_tracking import setup_exception_handlers
from backend.utils.health import perform_health_check, shutdown_manager
from backend.utils.logger import get_logger, set_request_id
from backend.utils.performance import generate_prometheus_metrics, get_prometheus_content_type
from backend.utils.rate_limiter import concurrency_limit_middleware, rate_limit_middleware
from backend.utils.warnings import *  # noqa: F401, F403

logger = get_logger(__name__)


def setup_shutdown_signal_handlers(app: FastAPI):
    """设置关闭信号处理器"""

    def handle_shutdown(signum, frame):
        logger.info(f"收到关闭信号 {signum}")
        shutdown_manager.initiate_shutdown()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("启动应用...")

    # 设置关闭信号处理器
    setup_shutdown_signal_handlers(app)

    # 初始化数据库
    logger.info("初始化数据库...")
    await async_initialize_database()
    logger.info("数据库初始化完成")

    # 初始化默认角色和权限
    logger.info("初始化默认角色和权限...")
    from backend.core.auth_manager import initialize_default_roles_and_permissions

    await initialize_default_roles_and_permissions()
    logger.info("角色和权限初始化完成")

    # 启动告警系统
    logger.info("启动告警系统...")
    await start_alerting()
    logger.info("告警系统启动完成")

    yield

    # 关闭时清理
    logger.info("关闭应用...")

    # 停止告警系统
    logger.info("停止告警系统...")
    await stop_alerting()
    logger.info("告警系统已停止")

    # 等待所有请求完成
    await shutdown_manager.wait_for_requests_to_complete()

    # 关闭 LLM 线程池
    try:
        from backend.generator import get_async_llm

        llm = get_async_llm()
        llm.close()
    except Exception as e:
        logger.warning(f"关闭 LLM 线程池失败: {str(e)}")

    # 关闭缓存嵌入模型线程池
    try:
        from backend.generator import get_cached_embeddings

        embeddings = get_cached_embeddings()
        embeddings.close()
    except Exception as e:
        logger.warning(f"关闭嵌入模型线程池失败: {str(e)}")

    logger.info("应用已优雅关闭")


# OpenAPI 安全方案配置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

openapi_tags = [
    {"name": "认证", "description": "用户认证相关接口，包括登录、注册、令牌管理"},
    {"name": "聊天", "description": "文档问答聊天接口，支持 RAG 检索增强"},
    {"name": "文档管理", "description": "文档上传、管理、检索、处理相关接口"},
    {"name": "多模态问答", "description": "支持图片理解的多模态问答接口"},
    {"name": "工作流", "description": "工作流定义、执行、管理接口"},
    {"name": "Agent", "description": "智能代理相关接口"},
    {"name": "权限管理", "description": "权限授予、检查、角色管理接口"},
    {"name": "审计日志", "description": "系统操作审计、安全事件追踪接口"},
    {"name": "监控告警", "description": "系统监控、告警、错误追踪接口"},
    {"name": "追踪", "description": "性能追踪、错误分析、链路追踪接口"},
    {"name": "部署", "description": "模型部署、版本管理、流量控制接口"},
    {"name": "A/B测试", "description": "A/B测试配置、流量分配接口"},
    {"name": "图表", "description": "图表解析、数据提取接口"},
    {"name": "CICD", "description": "测试、验证、部署流水线接口"},
    {"name": "调试", "description": "调试工具、断点管理接口"},
    {"name": "Dify集成", "description": "Dify 平台集成接口"},
    {"name": "知识图谱", "description": "知识图谱查询、构建接口"},
    {"name": "总结", "description": "文档摘要、总结生成接口"},
    {"name": "健康检查", "description": "服务健康状态检查接口"},
]

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
# 企业级智能文档问答平台 API

基于 RAG（检索增强生成）技术的企业级知识库问答系统，提供以下核心能力：

## 核心功能模块

### 文档问答
- 支持多种文档格式（PDF、Word、Excel、Markdown等）
- 智能分块与向量检索
- 混合检索（向量+BM25）与重排序

### 多模态能力
- 图片理解与描述
- OCR文字提取
- 多模态问答

### 工作流引擎
- 可视化工作流定义
- 任务编排与执行
- 条件分支与循环

### 智能代理
- 角色化 Agent
- 多 Agent 协作
- 任务拆分与并行执行

### 监控与运维
- 性能追踪与分析
- 错误追踪与聚合
- 实时告警系统

## 安全特性
- JWT 身份认证
- 细粒度权限控制
- 审计日志记录
- 请求限流与并发控制

## API 版本
当前版本: v1

## 认证方式
使用 OAuth2 Bearer Token 进行认证，获取令牌后在请求头中添加:
```
Authorization: Bearer <token>
```
""",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
)

# OpenAPI 安全方案配置
app.openapi_schema = None


def custom_openapi():
    """自定义 OpenAPI schema，添加安全方案"""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = app.openapi()
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "使用 JWT Token 进行认证，格式: Bearer <token>",
        }
    }
    openapi_schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = custom_openapi

# 请求体大小限制
app.state.max_request_size = 10 * 1024 * 1024  # 10MB

# GZip 压缩中间件（提升传输性能）
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 信任主机中间件（安全防护）
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# 安全头中间件
app.add_middleware(SecurityHeadersMiddleware)

# SQL注入防护中间件
app.add_middleware(SQLInjectionProtectionMiddleware)

# XSS防护中间件
app.add_middleware(XSSProtectionMiddleware)

# API 版本管理中间件
app.add_middleware(VersionMiddleware)


# 请求追踪 ID 中间件（必须在其他中间件之前）
@app.middleware("http")
async def request_id_middleware(request, call_next):
    """为每个请求注入请求追踪 ID，支持链路追踪"""
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    set_request_id(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# 限流中间件（性能保护）
@app.middleware("http")
async def add_rate_limit_middleware(request, call_next):
    return await rate_limit_middleware(request, call_next)


# 并发限制中间件（控制并发数）
@app.middleware("http")
async def add_concurrency_limit_middleware(request, call_next):
    return await concurrency_limit_middleware(request, call_next)


# 请求计数中间件（用于优雅关闭）
@app.middleware("http")
async def add_request_count_middleware(request, call_next):
    shutdown_manager.increment_request_count()
    try:
        return await call_next(request)
    finally:
        shutdown_manager.decrement_request_count()


# 注册路由
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(auth_router)
app.include_router(alerts_router)
app.include_router(agent_router)
app.include_router(summary_router)
app.include_router(knowledge_graph_router)
app.include_router(chart_router)
app.include_router(workflow_router)
app.include_router(cicd_router)
# 新增路由注册
app.include_router(audit_router)
app.include_router(multimodal_router)
app.include_router(notification_router)
app.include_router(unified_chat_router)
app.include_router(permission_router)
app.include_router(plugins_router)
app.include_router(tracing_router)
app.include_router(versioning_router)

# 设置全局异常处理器
setup_exception_handlers(app)


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "企业级智能文档问答平台",
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    """健康检查 - 返回详细的服务健康状态"""
    report = await perform_health_check()

    # 根据健康状态设置 HTTP 状态码
    status_code = 200
    if report["status"] == "degraded":
        status_code = 200  # 降级状态仍返回 200
    elif report["status"] == "unhealthy":
        status_code = 503  # 不健康状态返回 503

    return JSONResponse(content=report, status_code=status_code)


@app.get("/health/liveness")
async def liveness_check():
    """存活检查 - 检查服务是否正在运行"""
    return {"status": "alive", "timestamp": time.time()}


@app.get("/health/readiness")
async def readiness_check():
    """就绪检查 - 检查服务是否准备好处理请求"""
    report = await perform_health_check()

    if report["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail="服务未就绪")

    return {"status": "ready", "timestamp": time.time()}


@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点"""
    metrics_data = generate_prometheus_metrics()
    content_type = get_prometheus_content_type()
    return Response(content=metrics_data, media_type=content_type)
