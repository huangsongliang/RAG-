"""Agent API 端点 —— ReAct 模式智能体接口"""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent import AgentResult, get_agent_manager
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


class AgentRequest(BaseModel):
    """Agent请求模型"""

    query: str = Field(..., min_length=1, max_length=5000, description="用户问题")
    session_id: Optional[str] = Field(None, description="会话ID，用于多轮对话")
    max_steps: Optional[int] = Field(None, ge=1, le=15, description="手动覆盖最大有效步数（1-15）")


class ToolCallTrace(BaseModel):
    """工具调用追踪"""

    step: int = Field(..., description="ReAct 步骤序号")
    thought: str = Field("", description="该步的思考过程")
    tool: str = Field(..., description="调用的工具名称")
    input: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    observation: str = Field("", description="工具返回摘要")
    success: bool = Field(True, description="工具执行是否成功")


class AgentResponse(BaseModel):
    """Agent响应模型（ReAct 模式）"""

    answer: str = Field(..., description="最终回答")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="引用来源")
    tool_calls: List[ToolCallTrace] = Field(default_factory=list, description="工具调用追踪")
    steps: int = Field(0, description="ReAct 实际执行步数（有效步数）")
    forced: bool = Field(False, description="是否因达到步数上限被强制结束")
    completion: Literal["complete", "partial", "degraded"] = Field("complete", description="回答完整度")
    unavailable_tools: List[str] = Field(default_factory=list, description="因故障被禁用的工具")
    effective_steps: int = Field(0, description="成功执行的工具调用次数")
    total_llm_calls: int = Field(0, description="LLM 调用总次数")
    metrics: List[Dict[str, Any]] = Field(default_factory=list, description="每步执行指标")


class ToolInfo(BaseModel):
    """工具信息模型"""

    name: str
    description: str


@router.post("/chat", response_model=AgentResponse)
async def agent_chat(request: AgentRequest):
    """Agent 对话接口（ReAct 模式，支持多轮对话和工具调用）

    支持以下场景：
    - 简单闲聊：直接回答，不调工具
    - 知识库问答：自动调用 document_qa 检索
    - 数学计算：自动调用 calculator
    - 文本总结：自动调用 summarize
    - 组合问题：多轮 ReAct，依次调用多个工具后综合回答
    - 失败降级：工具故障自动禁用，步数耗尽诚实告知
    """
    try:
        agent_manager = get_agent_manager()
        result: AgentResult = await agent_manager.run(
            query=request.query,
            session_id=request.session_id,
            max_steps=request.max_steps,
        )

        return AgentResponse(
            answer=result.answer,
            sources=result.sources,
            tool_calls=result.tool_calls,
            steps=result.steps,
            forced=result.forced,
            completion=result.completion,
            unavailable_tools=result.unavailable_tools,
            effective_steps=result.effective_steps,
            total_llm_calls=result.total_llm_calls,
            metrics=result.metrics,
        )

    except Exception as e:
        logger.error(f"Agent API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools", response_model=List[ToolInfo])
async def list_tools():
    """获取可用工具列表"""
    try:
        agent_manager = get_agent_manager()
        tools = []
        for tool in agent_manager.tools:
            tools.append(ToolInfo(name=tool.name, description=tool.description))
        return tools

    except Exception as e:
        logger.error(f"获取工具列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def agent_health():
    """Agent健康检查"""
    try:
        agent_manager = get_agent_manager()
        return {"status": "healthy", "tools_count": len(agent_manager.tools)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Agent服务异常: {str(e)}")
