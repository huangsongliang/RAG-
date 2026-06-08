"""
Pydantic 数据模型定义
用于 API 请求/响应的数据验证和序列化

包含：
- 聊天相关模型
- 检索相关模型
- 通用响应模型
- 错误响应模型
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    """消息角色枚举"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """聊天消息模型"""

    role: MessageRole = Field(..., description="消息角色")
    content: str = Field(..., min_length=1, max_length=10000, description="消息内容")
    timestamp: Optional[datetime] = Field(default=None, description="消息时间戳")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "user",
                "content": "企业级文档问答平台如何部署？",
                "timestamp": "2024-01-15T10:30:00",
            }
        }
    )


class ChatRequest(BaseModel):
    """聊天请求模型"""

    message: str = Field(..., min_length=1, max_length=5000, description="用户消息")
    session_id: Optional[str] = Field(default=None, description="会话 ID，用于多轮对话")
    stream: bool = Field(default=True, description="是否启用流式输出")
    temperature: Optional[float] = Field(default=None, ge=0, le=2, description="LLM 温度参数")
    top_k: Optional[int] = Field(default=None, ge=1, le=20, description="检索文档数量")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "企业级文档问答平台如何部署？",
                "session_id": "user_123_session_456",
                "stream": True,
                "temperature": 0.7,
                "top_k": 5,
            }
        }
    )


class DocumentReference(BaseModel):
    """文档引用模型"""

    content: str = Field(..., description="引用的文档内容")
    source: str = Field(..., description="文档来源")
    score: float = Field(..., ge=0, le=1, description="相似度得分")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="额外元数据")


class ChatResponse(BaseModel):
    """聊天响应模型"""

    answer: str = Field(..., description="AI 生成的答案")
    references: List[DocumentReference] = Field(default_factory=list, description="引用的文档列表")
    session_id: str = Field(..., description="会话 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="响应时间戳")
    model_name: str = Field(..., description="使用的模型名称")
    usage: Optional[Dict[str, int]] = Field(default=None, description="Token 使用量统计")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "平台支持Docker Compose单机部署和Kubernetes集群部署两种方式...",
                "references": [
                    {
                        "content": "《水调歌头》创作背景...",
                        "source": "平台部署指南.txt",
                        "score": 0.95,
                        "metadata": {"page": 1},
                    }
                ],
                "session_id": "user_123_session_456",
                "created_at": "2024-01-15T10:30:05",
                "model_name": "qwen-max",
                "usage": {
                    "prompt_tokens": 150,
                    "completion_tokens": 200,
                    "total_tokens": 350,
                },
            }
        }
    )


class StreamChunk(BaseModel):
    """流式响应数据块"""

    content: str = Field(..., description="响应内容片段")
    is_final: bool = Field(default=False, description="是否为最后一个片段")
    references: Optional[List[DocumentReference]] = Field(default=None, description="最终答案的引用文档")

    model_config = ConfigDict(
        json_schema_extra={"example": {"content": "《水调歌头", "is_final": False, "references": None}}
    )


class SessionHistory(BaseModel):
    """会话历史模型"""

    session_id: str = Field(..., description="会话 ID")
    messages: List[ChatMessage] = Field(default_factory=list, description="消息列表")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="额外元数据")


class HealthStatus(BaseModel):
    """健康检查状态模型"""

    status: str = Field(..., description="服务状态")
    version: str = Field(..., description="应用版本")
    timestamp: datetime = Field(default_factory=datetime.now, description="检查时间")
    services: Dict[str, bool] = Field(default_factory=dict, description="依赖服务状态")


class ErrorResponse(BaseModel):
    """统一错误响应模型 — 所有 API 错误响应的标准格式"""

    error: str = Field(..., description="错误码（如 LLM_TIMEOUT, VALIDATION_ERROR）")
    message: str = Field(..., description="错误消息")
    detail: Optional[str] = Field(default=None, description="详细错误信息（仅开发环境返回）")
    error_id: Optional[str] = Field(default=None, description="错误追踪 ID，用于关联服务端日志")
    request_id: Optional[str] = Field(default=None, description="请求追踪 ID")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="错误发生时间 (ISO 8601)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "LLM_TIMEOUT",
                "message": "LLM 调用超时",
                "detail": "qwen-max 模型响应时间超过 60 秒",
                "error_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "request_id": "req_abc123",
                "timestamp": "2024-01-15T10:30:05",
            }
        }
    )


class RetrievalResult(BaseModel):
    """检索结果模型"""

    query: str = Field(..., description="检索查询")
    documents: List[DocumentReference] = Field(default_factory=list, description="检索到的文档列表")
    total: int = Field(..., description="检索结果总数")
    retrieval_time_ms: float = Field(..., description="检索耗时（毫秒）")
    method: str = Field(..., description="检索方法")


class Document(BaseModel):
    """文档模型"""

    content: str = Field(..., description="文档内容")
    source: str = Field(..., description="文档来源")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="文档元数据")
    embedding: Optional[List[float]] = Field(default=None, description="文档嵌入向量")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "content": "企业级智能文档问答平台基于RAG架构...",
                "source": "平台介绍.txt",
                "metadata": {
                    "category": "biography",
                    "author": "admin",
                    "created_at": "2024-01-01",
                },
                "embedding": [0.123, -0.456, 0.789],
            }
        }
    )


class EmbeddingRequest(BaseModel):
    """嵌入请求模型"""

    texts: List[str] = Field(..., min_length=1, max_length=100, description="要嵌入的文本列表")
    model: Optional[str] = Field(default=None, description="嵌入模型名称")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "texts": ["企业级文档问答平台是新一代智能知识管理解决方案", "系统集成了通义千问大语言模型"],
                "model": "text_embedding_v2",
            }
        }
    )


class EmbeddingResponse(BaseModel):
    """嵌入响应模型"""

    embeddings: List[List[float]] = Field(..., description="嵌入向量列表")
    model: str = Field(..., description="使用的模型")
    dimension: int = Field(..., description="向量维度")
    usage: Dict[str, int] = Field(..., description="Token 使用量统计")
