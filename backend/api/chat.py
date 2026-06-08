"""聊天 API 路由"""

import json
import time
import traceback
import warnings
from datetime import datetime
from typing import AsyncGenerator, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.chain import get_rag_chain
from backend.database.models import Conversation
from backend.database.session import get_db_session
from backend.memory import ConversationMemory
from backend.retrieval import get_vector_store
from backend.utils.logger import get_logger
from backend.utils.performance import performance_monitor, timed_operation

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class Message(BaseModel):
    """消息模型"""

    role: str
    content: str


class ChatRequest(BaseModel):
    """聊天请求模型（带验证）"""

    message: str = Field(..., min_length=1, max_length=5000, description="用户消息")
    session_id: Optional[str] = None
    use_rag: bool = True
    top_k: int = Field(3, ge=1, le=20, description="检索文档数量")


class ChatResponse(BaseModel):
    """聊天响应模型"""

    answer: str
    session_id: str
    references: List[dict] = []
    sources: List[str] = []


class AddDocumentsRequest(BaseModel):
    """添加文档请求模型"""

    documents: List[str] = Field(..., min_length=1, max_length=100, description="文档列表")


def format_error_response(
    error_type: str, message: str, detail: Optional[str] = None, error_id: Optional[str] = None
) -> dict:
    """格式化统一错误响应（与 ErrorResponse Pydantic 模型对齐）"""
    from backend.utils.logger import get_request_id

    return {
        "error": error_type,
        "message": message,
        "detail": detail,
        "error_id": error_id,
        "request_id": get_request_id(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _get_user_id(request: Request) -> Optional[int]:
    """从 JWT token 直接解析用户 ID（AuthMiddleware 未注册，需自行解码）"""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        from jose import jwt

        from backend.core.config import settings

        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        uid = payload.get("sub")
        if uid:
            return int(uid) if isinstance(uid, int) or uid.isdigit() else None
    except Exception:
        return None
    return None


async def _save_conversation(session_id: str, user_id: Optional[int], title: str):
    """将会话信息持久化到数据库"""
    if not user_id:
        return
    try:
        async with get_db_session() as db:
            existing = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
            conv = existing.scalar_one_or_none()
            if conv:
                conv.title = title
                conv.updated_at = datetime.now()
            else:
                conv = Conversation(
                    user_id=user_id,
                    session_id=session_id,
                    title=title,
                )
                db.add(conv)
            await db.commit()
    except Exception as e:
        logger.warning(f"保存会话到数据库失败: {e}")


@router.post("/docs/add")
async def add_documents(request: AddDocumentsRequest):
    """添加文档到向量库"""
    try:
        # 输入验证
        if not request.documents or len(request.documents) == 0:
            raise HTTPException(
                status_code=400,
                detail=format_error_response(
                    "INVALID_INPUT",
                    "文档列表不能为空",
                    "documents 参数必须包含至少一个文档",
                ),
            )

        vector_store = get_vector_store()
        ids = vector_store.add_documents(request.documents)
        return {"status": "success", "count": len(ids), "ids": ids}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"添加文档失败: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=format_error_response("INTERNAL_ERROR", "添加文档失败", str(e)),
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request) -> ChatResponse:
    """聊天接口 - 调用 RAG 链处理（异步优化）"""

    start_time = time.time()
    session_id = request.session_id or str(uuid4())

    try:
        # 输入验证
        if not request.message or request.message.strip() == "":
            raise HTTPException(
                status_code=400,
                detail=format_error_response(
                    "INVALID_INPUT",
                    "消息内容不能为空",
                    "message 参数必须包含至少一个非空白字符",
                ),
            )

        # 获取对话记忆
        memory = ConversationMemory(session_id)

        # 获取历史消息（最近20条）
        history = await memory.get_history(limit=20)

        # 构建上下文
        context = "\n".join([f"{msg.role}: {msg.content}" for msg in history])

        with timed_operation("chat_request"):
            # 调用异步 RAG 链（使用线程池优化）
            rag_chain = get_rag_chain()
            result = await rag_chain.async_run(
                query=request.message,
                top_k=request.top_k,
                use_rag=request.use_rag,
                history=context,
            )

        # 保存对话到记忆
        await memory.save_message("user", request.message)
        await memory.save_message("assistant", result["answer"])

        # 持久化会话到数据库
        user_id = _get_user_id(req)
        title = request.message[:50] + ("..." if len(request.message) > 50 else "")
        await _save_conversation(session_id, user_id, title)

        # 提取来源信息
        sources = []
        for ref in result["references"]:
            if ref.get("metadata") and ref["metadata"].get("source"):
                sources.append(ref["metadata"]["source"])

        # 更新性能指标
        performance_monitor.increment_request_count()
        performance_monitor.add_request_time(time.time() - start_time)

        return ChatResponse(
            answer=result["answer"],
            session_id=session_id,
            references=result["references"],
            sources=sources,
        )

    except HTTPException as e:
        # 重新抛出已处理的 HTTP 异常
        raise e
    except Exception as e:
        logger.error(f"RAG 链调用失败: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=format_error_response("INTERNAL_ERROR", "服务内部错误", str(e)),
        )


async def generate_stream_response(
    session_id: str,
    message: str,
    user_id: Optional[int] = None,
    use_rag: bool = True,
    top_k: int = 3,
) -> AsyncGenerator[str, None]:
    """生成流式响应"""
    async for chunk in _stream_response_core(
        session_id,
        message,
        use_rag,
        top_k,
        user_id,
    ):
        yield chunk


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, req: Request):
    """流式聊天接口 - SSE"""

    session_id = request.session_id or str(uuid4())
    user_id = _get_user_id(req)

    return StreamingResponse(
        generate_stream_response(
            session_id=session_id,
            message=request.message,
            user_id=user_id,
            use_rag=request.use_rag,
            top_k=request.top_k,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session_id,
        },
    )


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "service": "企业智能文档问答系统"}


@router.get("/docs/count")
async def get_document_count():
    """获取向量库文档数量"""
    vector_store = get_vector_store()
    count = vector_store.count()
    return {"count": count}


@router.delete("/docs")
async def clear_documents():
    """清空向量库"""
    vector_store = get_vector_store()
    vector_store.delete_all()
    return {"status": "success", "message": "所有文档已删除"}


@router.get("/stats/performance")
async def get_performance_stats():
    """获取性能统计指标"""
    return performance_monitor.get_metrics()


@router.post("/stats/reset")
async def reset_performance_stats():
    """重置性能统计指标"""
    performance_monitor.reset()
    return {"status": "success", "message": "性能统计已重置"}


# ==================== 会话历史 API ====================


@router.get("/chat/sessions")
async def list_sessions(request: Request):
    """获取当前用户的会话列表（需登录）"""
    user_id = _get_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")

    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc())
            )
            convs = result.scalars().all()
            return {
                "sessions": [
                    {
                        "id": c.session_id,
                        "title": c.title or "新对话",
                        "created_at": c.created_at.isoformat() if c.created_at else "",
                        "updated_at": c.updated_at.isoformat() if c.updated_at else "",
                    }
                    for c in convs
                ]
            }
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取指定会话的消息历史（从 Redis 读取）"""
    try:
        memory = ConversationMemory(session_id)
        messages = await memory.get_full_history()
        return {
            "session_id": session_id,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in messages
            ],
        }
    except Exception as e:
        logger.error(f"获取会话消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 异步流式 API ====================
async def _stream_response_core(
    session_id: str,
    message: str,
    use_rag: bool = True,
    top_k: int = 3,
    user_id: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """流式响应核心逻辑（消除 generate_stream_response 和
    generate_async_stream_response 的代码重复）"""
    start_time = time.time()

    try:
        # 输入验证
        if not message or message.strip() == "":
            error_info = json.dumps({"type": "error", "data": "消息内容不能为空"}, ensure_ascii=False)
            yield f"data: {error_info}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 获取对话记忆
        memory = ConversationMemory(session_id)

        # 获取历史消息（最近20条）
        history = await memory.get_history(limit=20)

        # 构建上下文
        context = "\n".join([f"{msg.role}: {msg.content}" for msg in history])

        # 保存用户消息到记忆
        await memory.save_message("user", message)

        # 持久化会话到数据库
        title = message[:50] + ("..." if len(message) > 50 else "")
        await _save_conversation(session_id, user_id, title)

        # 获取 RAG 链
        rag_chain = get_rag_chain()

        # 先发送引用信息（异步检索，不阻塞事件循环）
        references = await rag_chain.async_retrieve(message, top_k=top_k) if use_rag else []
        if references:
            ref_json = json.dumps({"type": "references", "data": references}, ensure_ascii=False)
            yield f"data: {ref_json}\n\n"

        # 流式生成回答（每个 chunk 直接发送）
        full_answer = ""
        async for chunk in rag_chain.stream_run(message, top_k=top_k, use_rag=use_rag, history=context):
            full_answer += chunk
            chunk_json = json.dumps({"type": "chunk", "data": chunk}, ensure_ascii=False)
            yield f"data: {chunk_json}\n\n"

        # 保存助手回复到记忆
        await memory.save_message("assistant", full_answer)

        # 更新性能指标
        performance_monitor.increment_request_count()
        performance_monitor.add_request_time(time.time() - start_time)

        # 发送完成信号
        yield f"data: {json.dumps({'type': 'done', 'data': full_answer}, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error(f"流式响应生成失败: {str(e)}\n{traceback.format_exc()}")
        error_info = json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False)
        yield f"data: {error_info}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'data': ''}, ensure_ascii=False)}\n\n"


async def generate_async_stream_response(
    session_id: str,
    message: str,
    user_id: Optional[int] = None,
    use_rag: bool = True,
    top_k: int = 3,
) -> AsyncGenerator[str, None]:
    """生成异步流式响应（结合异步任务队列和SSE，与 generate_stream_response 共享核心逻辑）"""
    async for chunk in _stream_response_core(
        session_id,
        message,
        use_rag,
        top_k,
        user_id,
    ):
        yield chunk


@router.post("/chat/async/stream")
async def chat_async_stream(request: ChatRequest, req: Request):
    """异步流式聊天接口 - SSE 实时推送"""

    session_id = request.session_id or str(uuid4())
    user_id = _get_user_id(req)

    return StreamingResponse(
        generate_async_stream_response(
            session_id=session_id,
            message=request.message,
            user_id=user_id,
            use_rag=request.use_rag,
            top_k=request.top_k,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session_id,
        },
    )


# ==================== 异步队列 API ====================
class AsyncChatRequest(BaseModel):
    """异步聊天请求模型"""

    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    use_rag: bool = True
    top_k: int = 3


class AsyncChatResponse(BaseModel):
    """异步聊天响应模型"""

    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应模型"""

    task_id: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None


@router.post("/chat/async", response_model=AsyncChatResponse)
async def chat_async(request: AsyncChatRequest):
    """
    异步聊天接口 - 使用轻量级任务队列

    立即返回任务ID，客户端可以通过 /chat/async/{task_id} 查询结果
    """
    try:
        from backend.utils.task_manager import get_task_manager

        task_manager = get_task_manager()

        session_id = request.session_id or str(uuid4())

        # 提交任务到线程池队列
        task_id = task_manager.submit(
            "process_chat",
            query=request.message,
            session_id=session_id,
            top_k=request.top_k,
            user_id=request.user_id,
        )

        return AsyncChatResponse(
            task_id=task_id,
            status="pending",
            message="任务已提交，请通过 task_id 查询结果",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交任务失败: {str(e)}")


@router.get("/chat/async/{task_id}", response_model=TaskStatusResponse)
async def get_async_chat_result(task_id: str):
    """
    获取异步聊天任务结果

    Args:
        task_id: 任务ID
    """
    try:
        from backend.utils.task_manager import get_task_manager

        task_manager = get_task_manager()

        # 获取任务状态
        task = task_manager.get_task(task_id)

        if not task:
            return TaskStatusResponse(task_id=task_id, status="not_found", error="任务不存在或已过期")

        if task.status.value == "completed":
            return TaskStatusResponse(task_id=task_id, status="completed", result=task.result)
        elif task.status.value == "failed":
            return TaskStatusResponse(task_id=task_id, status="failed", error=task.error)
        else:
            # 任务还在执行中
            return TaskStatusResponse(task_id=task_id, status=task.status.value, result={"info": "处理中..."})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询任务失败: {str(e)}")


# ==================== 兼容层（deprecated） ====================
# 旧入口标记 deprecated，内部代理到统一引擎 /api/chat/send。
# 计划在 6 个月后移除。迁移指南见 docs/MIGRATION_UNIFIED_CHAT.md


@router.post("/chat/async/stream", deprecated=True)
async def chat_async_stream_deprecated(request: ChatRequest, req: Request):
    """[DEPRECATED] 旧版异步流式聊天 — 内部代理到 /api/chat/send"""
    warnings.warn(
        "此接口已废弃，请迁移到 POST /api/chat/send 统一入口。",
        DeprecationWarning,
    )

    from backend.api.unified_chat import ChatSendRequest
    from backend.api.unified_chat import _get_user_id as unified_get_user_id
    from backend.api.unified_chat import _route_rag, _stream_with_heartbeat, event_to_json

    session_id = request.session_id or str(uuid4())
    user_id = unified_get_user_id(req)

    async def generator():
        async for event in _route_rag(
            request.message,
            session_id,
            user_id,
            request.use_rag,
            request.top_k,
        ):
            yield event

    return StreamingResponse(
        _stream_with_heartbeat(generator()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-ID": session_id,
            "X-Deprecated": "true",
        },
    )


@router.post("/chat/stream", deprecated=True)
async def chat_stream_deprecated(request: ChatRequest, req: Request):
    """[DEPRECATED] 旧版流式聊天 — 内部代理到 /api/chat/send"""
    warnings.warn(
        "此接口已废弃，请迁移到 POST /api/chat/send 统一入口。",
        DeprecationWarning,
    )

    from backend.api.unified_chat import ChatSendRequest
    from backend.api.unified_chat import _get_user_id as unified_get_user_id
    from backend.api.unified_chat import _route_rag, _stream_with_heartbeat, event_to_json

    session_id = request.session_id or str(uuid4())
    user_id = unified_get_user_id(req)

    async def generator():
        async for event in _route_rag(
            request.message,
            session_id,
            user_id,
            request.use_rag,
            request.top_k,
        ):
            yield event

    return StreamingResponse(
        _stream_with_heartbeat(generator()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-ID": session_id,
            "X-Deprecated": "true",
        },
    )
