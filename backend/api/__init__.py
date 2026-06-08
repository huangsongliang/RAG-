"""API 模块 - FastAPI 路由"""

from backend.api.agent import router as agent_router
from backend.api.alerts import router as alerts_router
from backend.api.audit import router as audit_router
from backend.api.auth import router as auth_router
from backend.api.chart import router as chart_router
from backend.api.chat import router as chat_router
from backend.api.cicd import router as cicd_router
from backend.api.document import router as document_router
from backend.api.documents import router as documents_router
from backend.api.knowledge_graph import router as knowledge_graph_router
from backend.api.link_parser import router as link_parser_router
from backend.api.multimodal import router as multimodal_router
from backend.api.notification import router as notification_router
from backend.api.permission import router as permission_router
from backend.api.plugins import router as plugins_router
from backend.api.summary import router as summary_router
from backend.api.tracing import router as tracing_router
from backend.api.unified_chat import router as unified_chat_router
from backend.api.versioning import router as versioning_router
from backend.api.workflow import router as workflow_router

__all__ = [
    "chat_router",
    "documents_router",
    "auth_router",
    "alerts_router",
    "knowledge_graph_router",
    "link_parser_router",
    "chart_router",
    "workflow_router",
    "cicd_router",
    "agent_router",
    "summary_router",
    "audit_router",
    "document_router",
    "multimodal_router",
    "unified_chat_router",
    "notification_router",
    "permission_router",
    "plugins_router",
    "tracing_router",
    "versioning_router",
]
