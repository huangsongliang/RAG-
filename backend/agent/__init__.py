"""Agent 核心模块 - ReAct 模式智能体，支持多轮思考和工具调用

v2 改进：
- 工具接口统一（BaseTool + ToolResult）
- 工具分组展示（按类别聚合 System Prompt）
- LLM 切换到 Messages 模式（system/user 角色分离）
- 错误信息脱敏
- 工具声明式注册（TOOL_CLASSES 列表）
"""

import asyncio
import inspect
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from backend.agent.tools import CATEGORY_LABELS, TOOL_CLASSES, BaseTool, ToolCategory, ToolResult, sanitize_error
from backend.generator import get_async_llm
from backend.memory.conversation import ConversationMemory as RedisConversationMemory
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ── ReAct 循环配置 ──────────────────────────────────────────────

HARD_MAX_STEPS = 15
DEFAULT_MAX_STEPS = 8
TOOL_TIMEOUT = 15.0
MAX_TOOL_RETRIES = 3
MAX_FORMAT_ERRORS = 2
LLM_OBSERVATION_MAX_LEN = 800
TRACE_OBSERVATION_MAX_LEN = 200
CONVERSATION_COMPRESS_THRESHOLD = 6000

# ReAct 格式的 System Prompt 模板（按类别分组展示工具）
REACT_SYSTEM_TEMPLATE = """你是一个智能助手，能够使用工具来解决问题。

{tools_description}

请严格按照以下格式思考并回答：

Thought: 我需要理解用户的问题并决定下一步该做什么
Action: 工具名（如果需要调用工具）
Action Input: 工具参数（JSON格式）

Observation: 工具返回的结果（由系统填入）

...（Thought/Action/Action Input/Observation 可以重复多轮）

Thought: 我现在有足够的信息来回答问题
Final Answer: 最终的完整回答

规则：
1. 如果是简单闲聊（如"你好""今天心情不错""谢谢"），直接给出 Final Answer，不要调用任何工具。
2. 根据用户问题的需求，从可用工具列表中选择最合适的工具。
3. 每次只调用一个工具，等待 Observation 后再决定下一步。
4. 基于给定事实回答问题，不要编造信息。
5. 如果某个工具返回错误，不要再尝试它，换其他工具或直接基于已有信息回答。
6. 如果发现信息不足以给出完整答案，请在 Final Answer 中诚实说明已知信息和信息缺口。
7. 上下文中的 [已禁用工具] 列表中的工具不要再调用。"""


# ── ReAct 响应解析 ──────────────────────────────────────────────


def _parse_react_response(text: str) -> Dict[str, Any]:
    """解析 LLM 返回的 ReAct 格式响应

    Args:
        text: LLM 原始响应文本

    Returns:
        {
            "thought": Optional[str],
            "action": Optional[str],
            "action_input": Optional[str],
            "is_final": bool,
            "final_answer": Optional[str],
        }
    """
    result: Dict[str, Any] = {
        "thought": None,
        "action": None,
        "action_input": None,
        "is_final": False,
        "final_answer": None,
    }

    # 提取 Final Answer（如果存在）
    fa_match = re.search(r"Final Answer\s*:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if fa_match:
        result["is_final"] = True
        result["final_answer"] = fa_match.group(1).strip()
        text_before_fa = text[: fa_match.start()]
    else:
        text_before_fa = text

    # 提取 Thought
    thought_match = re.search(
        r"Thought\s*:\s*(.*?)(?=\n(?:Action|Final Answer):|\Z)",
        text_before_fa,
        re.DOTALL | re.IGNORECASE,
    )
    if thought_match:
        result["thought"] = thought_match.group(1).strip()

    # 提取 Action
    action_match = re.search(r"Action\s*:\s*(.+?)(?:\n|$)", text_before_fa, re.IGNORECASE)
    if action_match:
        result["action"] = action_match.group(1).strip()

    # 提取 Action Input
    ai_match = re.search(
        r"Action Input\s*:\s*(.*?)(?=\n(?:Observation|Thought|Action|Final Answer):|\Z)",
        text_before_fa,
        re.DOTALL | re.IGNORECASE,
    )
    if ai_match:
        result["action_input"] = ai_match.group(1).strip()

    return result


def _try_parse_action_input(raw_input: str) -> Dict[str, Any]:
    """尝试将 Action Input 解析为 JSON dict，失败则包装为 {"query": raw_input}"""
    if not raw_input:
        return {}

    raw = raw_input.strip()

    # 去掉可能的 markdown 代码块包裹
    code_match = re.match(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if code_match:
        raw = code_match.group(1).strip()

    # 尝试 JSON 解析
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # 尝试提取第一个 JSON 对象
    json_match = re.search(r"\{[^{}]*\}", raw)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

    return {"query": raw}


# ── 结果模型 ────────────────────────────────────────────────────


class AgentResult(BaseModel):
    """Agent 执行结果"""

    answer: str = Field(..., description="最终回答")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="引用来源")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="工具调用追踪")
    steps: int = Field(0, description="ReAct 实际执行步数（有效步数）")
    forced: bool = Field(False, description="是否因达到步数上限被强制结束")
    completion: Literal["complete", "partial", "degraded"] = Field("complete", description="回答完整度")
    unavailable_tools: List[str] = Field(default_factory=list, description="因故障被禁用的工具")
    effective_steps: int = Field(0, description="成功执行的工具调用次数")
    total_llm_calls: int = Field(0, description="LLM 调用总次数")
    metrics: List[Dict[str, Any]] = Field(default_factory=list, description="每步执行指标")


@dataclass
class StepMetrics:
    """单步执行指标（用于最终汇总）"""

    step: int
    thought: str = ""
    action: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    llm_latency_ms: int = 0
    tool_latency_ms: int = 0
    tool_success: bool = True
    observation_len: int = 0
    error: Optional[str] = None


# ── Agent 管理器 ────────────────────────────────────────────────


class AgentManager:
    """ReAct Agent 管理器 - 支持多轮思考和工具调用（v2 重构版）"""

    def __init__(self):
        self.llm = get_async_llm()
        self.tools = self._initialize_tools()
        self._tool_map: Dict[str, BaseTool] = {t.name: t for t in self.tools}
        logger.info(f"Agent管理器初始化完成，已加载 {len(self.tools)} 个工具")

    def _initialize_tools(self) -> List[BaseTool]:
        """初始化工具列表（声明式注册，新增工具只需在 TOOL_CLASSES 加一行）"""
        tools: List[BaseTool] = []
        for tool_cls in TOOL_CLASSES:
            tools.append(tool_cls())
        logger.info(f"已加载 {len(tools)} 个工具: {[t.name for t in tools]}")
        return tools

    def _build_grouped_tools_description(self) -> str:
        """构建按类别分组的工具描述字符串（用于 System Prompt）"""
        # 按类别分组
        groups: Dict[ToolCategory, List[BaseTool]] = {}
        for tool in self.tools:
            groups.setdefault(tool.category, []).append(tool)

        lines: List[str] = ["可用工具：", ""]
        for category in (ToolCategory.KNOWLEDGE, ToolCategory.DATA, ToolCategory.CREATIVITY, ToolCategory.UTILITY):
            cat_tools = groups.get(category, [])
            if not cat_tools:
                continue
            label = CATEGORY_LABELS.get(category, "📦 其他")
            lines.append(f"{label}：")
            for tool in cat_tools:
                lines.append(tool.get_llm_description())
            lines.append("")

        return "\n".join(lines)

    async def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], bool]:
        """执行指定工具，返回 (observation_text, extra_data, is_success)

        改进：
        - 统一使用 ToolResult 接口
        - 错误信息脱敏
        - asyncio.wait_for 超时控制
        """
        tool = self._tool_map.get(tool_name)
        if tool is None:
            available = ", ".join(self._tool_map.keys())
            return f"错误: 未知工具 '{tool_name}'，可用工具: {available}", {}, False

        try:
            logger.info(f"🔧 调用工具: {tool_name}，参数: {tool_args}")
            start_time = time.monotonic()

            result = tool.run(**tool_args)
            if inspect.iscoroutine(result):
                result = await asyncio.wait_for(result, timeout=TOOL_TIMEOUT)

            elapsed = (time.monotonic() - start_time) * 1000

        except asyncio.TimeoutError:
            logger.error(f"⏱ 工具 {tool_name} 执行超时（>{TOOL_TIMEOUT}秒）")
            return (
                f"工具 '{tool_name}' 执行超时（>{TOOL_TIMEOUT}秒），请尝试简化问题或稍后重试。",
                {},
                False,
            )
        except TypeError:
            # 参数不匹配时的兜底（兼容 LLM 输出格式问题）
            try:
                query_val = tool_args.get("query", list(tool_args.values())[0] if tool_args else "")
                result = tool.run(query_val)
                if inspect.iscoroutine(result):
                    result = await asyncio.wait_for(result, timeout=TOOL_TIMEOUT)
            except Exception as e:
                return f"工具执行出错: {sanitize_error(str(e))}", {}, False
        except Exception as e:
            sanitized = sanitize_error(str(e))
            logger.error(f"❌ 工具 {tool_name} 执行失败: {sanitized}")
            return f"工具执行出错: {sanitized}", {}, False

        # 统一处理 ToolResult
        if isinstance(result, ToolResult):
            elapsed_str = f"耗时 {elapsed:.0f}ms"
            if result.success:
                logger.info(f"✅ 工具 {tool_name} 执行成功，{elapsed_str}")
            else:
                logger.warning(f"⚠️ 工具 {tool_name} 返回失败: {result.error}")
            observation = result.to_observation(LLM_OBSERVATION_MAX_LEN)
            extra = {
                "sources": result.sources,
                **result.extra,
            }
            return observation, extra, result.success

        # 兼容旧版返回格式（dict/str）
        extra: Dict[str, Any] = {}
        if isinstance(result, dict):
            extra = {
                "sources": result.get("sources", []),
                "query": result.get("query", ""),
            }
            observation = result.get("answer", "") or json.dumps(result, ensure_ascii=False)
        else:
            observation = str(result)
        logger.info(f"✅ 工具 {tool_name} 执行成功（兼容模式），{elapsed:.0f}ms")
        return observation, extra, True

    async def run(
        self,
        query: str,
        session_id: Optional[str] = None,
        max_steps: Optional[int] = None,
    ) -> AgentResult:
        """ReAct Agent 主循环 —— Think → Act → Observe → Think → ... → Final Answer

        改进要点：
        - 双计数器模型（有效步数 vs 总 LLM 调用）
        - 工具失败不消耗有效步数
        - 单工具连续失败 3 次自动禁用
        - LLM 格式错误自动纠正
        - 降级回答不调 LLM（确定性模板拼接）
        - 工具执行超时控制
        - LLM Messages 模式（system/user 角色分离）
        - 错误信息脱敏

        Args:
            query: 用户问题
            session_id: 会话 ID
            max_steps: 手动覆盖最大有效步数

        Returns:
            AgentResult
        """
        start_time = time.monotonic()
        logger.info(f"Agent 开始 ReAct 处理: {query[:80]}...")

        # ── 0. 参数校验与预算设定 ──
        if max_steps is not None:
            effective_max = min(max(max_steps, 1), HARD_MAX_STEPS)
        else:
            effective_max = DEFAULT_MAX_STEPS

        # ── 1. 加载历史对话 ──
        history_context = ""
        redis_memory = None
        if session_id:
            redis_memory = RedisConversationMemory(session_id)
            history = await redis_memory.get_history(limit=10)
            if history:
                history_parts = [f"{m.role}: {m.content}" for m in history]
                history_context = "对话历史：\n" + "\n".join(history_parts[-6:])

        # ── 2. 构建 System Prompt（分组展示工具） ──
        tools_desc = self._build_grouped_tools_description()
        system_prompt = REACT_SYSTEM_TEMPLATE.format(tools_description=tools_desc)

        # ── 3. 构建初始上下文（用户消息部分，会在 ReAct 循环中增长） ──
        user_message = query
        if history_context:
            user_message = f"{history_context}\n\n当前问题: {query}"

        conversation = user_message  # 不含 system prompt，后者单独在 messages 中

        # ── 4. 状态追踪 ──
        effective_steps: int = 0
        total_llm_calls: int = 0
        tool_retries: Dict[str, int] = {}
        unavailable_tools: set = set()
        format_errors: int = 0
        all_sources: List[Dict[str, Any]] = []
        tool_calls_trace: List[Dict[str, Any]] = []
        all_metrics: List[Dict[str, Any]] = []

        # ── 5. ReAct 主循环 ──
        while effective_steps < effective_max and total_llm_calls < HARD_MAX_STEPS:
            total_llm_calls += 1
            llm_start = time.monotonic()

            # 构建上下文（含禁用工具提醒）
            context_for_llm = conversation
            if unavailable_tools:
                disabled_str = ", ".join(sorted(unavailable_tools))
                context_for_llm = (
                    f"{conversation}\n\n[系统提示] 以下工具因多次失败已被禁用，" f"请不要再调用: {disabled_str}"
                )

            logger.info(f"ReAct 第 {effective_steps + 1} 有效步 " f"(总LLM调用 #{total_llm_calls})...")

            # 5a. LLM 推理（Messages 模式：system + user）
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_for_llm},
            ]
            llm_result = await self.llm.invoke_messages(messages)
            response_text = llm_result.output["choices"][0]["message"]["content"]
            llm_latency = int((time.monotonic() - llm_start) * 1000)

            # 5b. 解析响应
            parsed = _parse_react_response(response_text)
            thought = parsed["thought"] or ""

            # 5c. 格式错误检测
            if not parsed["is_final"] and not parsed["action"]:
                format_errors += 1
                logger.warning(f"LLM 格式错误 (#{format_errors}): " f"未检测到 Action 或 Final Answer")
                if format_errors > MAX_FORMAT_ERRORS:
                    logger.error("LLM 格式错误次数超限，触发降级")
                    return await self._build_degraded_result(
                        query=query,
                        sources=all_sources,
                        tool_calls=tool_calls_trace,
                        effective_steps=effective_steps,
                        total_llm_calls=total_llm_calls,
                        unavailable_tools=list(unavailable_tools),
                        metrics=all_metrics,
                        reason="format_error",
                        session_id=session_id,
                        redis_memory=redis_memory,
                    )

                # 追加纠正提示
                conversation += (
                    "\n\n[系统提示] 你上一步的输出格式不符合要求。"
                    "请严格按照 Thought / Action / Action Input "
                    "或 Final Answer 格式输出。"
                )
                continue

            format_errors = 0

            # 5d. Final Answer → 直接返回
            if parsed["is_final"] and parsed["final_answer"]:
                final_answer = parsed["final_answer"]
                total_latency = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    f"ReAct 完成: {effective_steps} 有效步输出 Final Answer, "
                    f"总LLM调用 {total_llm_calls}, 总耗时 {total_latency}ms"
                )

                if session_id and redis_memory:
                    await redis_memory.save_message("user", query)
                    await redis_memory.save_message("assistant", final_answer)

                all_metrics.append(
                    {
                        "step": effective_steps + 1,
                        "type": "final_answer",
                        "llm_latency_ms": llm_latency,
                        "tool_latency_ms": 0,
                        "success": True,
                    }
                )

                return AgentResult(
                    answer=final_answer,
                    sources=all_sources,
                    tool_calls=tool_calls_trace,
                    steps=effective_steps,
                    forced=False,
                    completion="partial" if unavailable_tools else "complete",
                    unavailable_tools=list(unavailable_tools),
                    effective_steps=effective_steps,
                    total_llm_calls=total_llm_calls,
                    metrics=all_metrics,
                )

            # 5e. Action → 执行工具
            if parsed["action"]:
                action_name = parsed["action"]
                action_input = _try_parse_action_input(parsed["action_input"] or "")

                # 跳过已禁用工具
                if action_name in unavailable_tools:
                    disabled_str = ", ".join(sorted(unavailable_tools))
                    conversation += (
                        f"\n\n{response_text}\n"
                        f"[系统提示] 工具 '{action_name}' 已被禁用。"
                        f"当前禁用工具: {disabled_str}。请选择其他工具"
                        f"或直接给出 Final Answer。"
                    )
                    logger.warning(f"LLM 尝试调用已禁用工具: {action_name}")
                    continue

                # 执行工具（带超时）
                tool_start = time.monotonic()
                observation, extra, is_success = await self._execute_tool(action_name, action_input)
                tool_latency = int((time.monotonic() - tool_start) * 1000)

                # 收集来源
                if extra.get("sources"):
                    all_sources.extend(extra["sources"])

                # 追踪记录
                trace_obs = self._smart_truncate(observation, TRACE_OBSERVATION_MAX_LEN)
                tool_calls_trace.append(
                    {
                        "step": effective_steps + 1,
                        "thought": thought,
                        "tool": action_name,
                        "input": action_input,
                        "observation": trace_obs,
                        "success": is_success,
                    }
                )

                all_metrics.append(
                    {
                        "step": effective_steps + 1,
                        "type": "tool_call",
                        "thought": thought[:100],
                        "action": action_name,
                        "tool_args": action_input,
                        "llm_latency_ms": llm_latency,
                        "tool_latency_ms": tool_latency,
                        "success": is_success,
                        "observation_len": len(observation),
                        "error": None if is_success else observation[:200],
                    }
                )

                # 步数计数与重试管理
                if is_success:
                    effective_steps += 1
                    tool_retries[action_name] = 0
                else:
                    tool_retries[action_name] = tool_retries.get(action_name, 0) + 1
                    current_retries = tool_retries[action_name]
                    if current_retries >= MAX_TOOL_RETRIES:
                        unavailable_tools.add(action_name)
                        disabled_str = ", ".join(sorted(unavailable_tools))
                        observation = (
                            f"[系统提示] 工具 '{action_name}' 连续失败"
                            f" {current_retries} 次已被禁用。"
                            f"当前禁用工具: {disabled_str}。{observation}"
                        )
                        logger.warning(f"工具 {action_name} 已被禁用（连续失败 {current_retries} 次）")
                    else:
                        logger.warning(
                            f"工具 {action_name} 执行失败 "
                            f"（{current_retries}/{MAX_TOOL_RETRIES}），"
                            f"不消耗有效步数"
                        )

                # 追加到对话
                conversation = self._append_step_to_conversation(conversation, response_text, observation)

                # 压缩长对话
                conversation = self._maybe_compress_conversation(conversation)

                continue

        # ── 6. 资源耗尽 → 诚实降级（不调 LLM） ──
        reason = "step_limit" if effective_steps >= effective_max else "llm_call_limit"
        logger.warning(
            f"ReAct 资源耗尽: reason={reason}, "
            f"effective_steps={effective_steps}, "
            f"total_llm_calls={total_llm_calls}"
        )
        return await self._build_degraded_result(
            query=query,
            sources=all_sources,
            tool_calls=tool_calls_trace,
            effective_steps=effective_steps,
            total_llm_calls=total_llm_calls,
            unavailable_tools=list(unavailable_tools),
            metrics=all_metrics,
            reason=reason,
            session_id=session_id,
            redis_memory=redis_memory,
        )

    async def stream_run(
        self,
        query: str,
        session_id: Optional[str] = None,
        max_steps: Optional[int] = None,
        file_paths: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """ReAct Agent 流式执行 —— 异步生成器，yield SSE 事件字典

        与 run() 的区别：
        1. 返回 AsyncGenerator 而非 AgentResult
        2. 每个 yield 是一个 SSE 事件字典（兼容 event_to_json）
        3. 中间步骤 yield status 事件（友好提示），非原始 thought/action
        4. Final Answer 阶段 yield content 事件（逐段推送）

        Yield 的事件格式：
        - {"type": "status", "phase": "analyzing", "detail": "..."}
        - {"type": "status", "phase": "generating", "detail": "..."}
        - {"type": "content", "data": "..."}
        - {"type": "metadata", ...}
        """
        start_time = time.monotonic()
        logger.info(f"Agent stream_run 开始: {query[:80]}...")

        # 参数校验
        if max_steps is not None:
            effective_max = min(max(max_steps, 1), HARD_MAX_STEPS)
        else:
            effective_max = DEFAULT_MAX_STEPS

        # 加载历史对话
        history_context = ""
        redis_memory = None
        if session_id:
            redis_memory = RedisConversationMemory(session_id)
            history = await redis_memory.get_history(limit=10)
            if history:
                history_parts = [f"{m.role}: {m.content}" for m in history]
                history_context = "对话历史：\n" + "\n".join(history_parts[-6:])

        # 构建 System Prompt
        tools_desc = self._build_grouped_tools_description()
        system_prompt = REACT_SYSTEM_TEMPLATE.format(tools_description=tools_desc)

        if file_paths:
            system_prompt += "\n\n注意：本次请求包含图片附件，" "你可以使用 multimodal 工具来理解图片内容。\n"
            system_prompt += f"图片文件路径: {', '.join(file_paths)}\n"

        # 构建初始上下文
        user_message = query
        if history_context:
            user_message = f"{history_context}\n\n当前问题: {query}"
        conversation = user_message

        # 状态追踪
        effective_steps: int = 0
        total_llm_calls: int = 0
        tool_retries: Dict[str, int] = {}
        unavailable_tools: set = set()
        format_errors: int = 0
        all_sources: List[Dict[str, Any]] = []
        tool_calls_trace: List[Dict[str, Any]] = []

        # ReAct 主循环
        while effective_steps < effective_max and total_llm_calls < HARD_MAX_STEPS:
            total_llm_calls += 1
            llm_start = time.monotonic()

            context_for_llm = conversation
            if unavailable_tools:
                disabled_str = ", ".join(sorted(unavailable_tools))
                context_for_llm = f"{conversation}\n\n[系统提示] 以下工具已被禁用: {disabled_str}"

            # 推送"分析中"状态
            step_display = effective_steps + 1
            yield {
                "type": "status",
                "phase": "analyzing",
                "detail": f"正在分析（第 {step_display} 步）...",
            }

            # LLM 推理
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_for_llm},
            ]
            llm_result = await self.llm.invoke_messages(messages)
            response_text = llm_result.output["choices"][0]["message"]["content"]
            llm_latency = int((time.monotonic() - llm_start) * 1000)

            # 解析响应
            parsed = _parse_react_response(response_text)
            thought = parsed["thought"] or ""

            # 格式错误处理
            if not parsed["is_final"] and not parsed["action"]:
                format_errors += 1
                if format_errors > MAX_FORMAT_ERRORS:
                    logger.error("LLM 格式错误次数超限，触发降级")
                    degraded = await self._build_degraded_result(
                        query=query,
                        sources=all_sources,
                        tool_calls=tool_calls_trace,
                        effective_steps=effective_steps,
                        total_llm_calls=total_llm_calls,
                        unavailable_tools=list(unavailable_tools),
                        metrics=[],
                        reason="format_error",
                        session_id=session_id,
                        redis_memory=redis_memory,
                    )
                    yield {
                        "type": "metadata",
                        "answer": degraded.answer,
                        "sources": degraded.sources,
                        "tool_calls": degraded.tool_calls,
                        "route": "agent",
                        "steps": effective_steps,
                        "completion": degraded.completion,
                    }
                    return

                conversation += "\n\n[系统提示] 请严格按 Thought/Action/Final Answer 格式输出。"
                continue

            format_errors = 0

            # Final Answer → 流式推送
            if parsed["is_final"] and parsed["final_answer"]:
                final_answer = parsed["final_answer"]

                yield {
                    "type": "status",
                    "phase": "generating",
                    "detail": "正在整理回答...",
                }

                # 分段推送（模拟流式）
                chunk_size = 100
                for i in range(0, len(final_answer), chunk_size):
                    chunk = final_answer[i : i + chunk_size]
                    yield {"type": "content", "data": chunk}

                # 保存记忆
                if session_id and redis_memory:
                    await redis_memory.save_message("user", query)
                    await redis_memory.save_message("assistant", final_answer)

                total_latency = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    f"Agent stream 完成: {effective_steps} 步, "
                    f"总LLM调用 {total_llm_calls}, 总耗时 {total_latency}ms"
                )

                yield {
                    "type": "metadata",
                    "answer": final_answer,
                    "sources": all_sources,
                    "tool_calls": tool_calls_trace,
                    "route": "agent",
                    "steps": effective_steps,
                    "completion": "partial" if unavailable_tools else "complete",
                }
                return

            # Action → 执行工具
            if parsed["action"]:
                action_name = parsed["action"]
                action_input = _try_parse_action_input(parsed["action_input"] or "")

                if action_name in unavailable_tools:
                    conversation += f"\n\n[系统提示] 工具 '{action_name}' 已被禁用。" f"请选择其他工具。"
                    continue

                yield {
                    "type": "status",
                    "phase": "analyzing",
                    "detail": f"正在调用工具: {action_name}...",
                }

                # 推送 tool_start 事件（供前端实时展示工具调用进度）
                yield {
                    "type": "tool_start",
                    "step": effective_steps + 1,
                    "tool": action_name,
                    "input": (
                        {k: str(v)[:200] for k, v in action_input.items()}
                        if isinstance(action_input, dict)
                        else str(action_input)[:200]
                    ),
                }

                tool_start = time.monotonic()
                observation, extra, is_success = await self._execute_tool(
                    action_name,
                    action_input,
                )
                tool_latency = int((time.monotonic() - tool_start) * 1000)

                if extra.get("sources"):
                    all_sources.extend(extra["sources"])

                trace_obs = self._smart_truncate(observation, TRACE_OBSERVATION_MAX_LEN)
                tool_calls_trace.append(
                    {
                        "step": effective_steps + 1,
                        "thought": thought[:100],
                        "tool": action_name,
                        "input": action_input,
                        "observation": trace_obs,
                        "success": is_success,
                    }
                )

                # 推送 tool_end 事件（工具执行完毕，携带结果摘要）
                yield {
                    "type": "tool_end",
                    "step": effective_steps + 1,
                    "tool": action_name,
                    "success": is_success,
                    "summary": trace_obs[:200],
                }

                if is_success:
                    effective_steps += 1
                    tool_retries[action_name] = 0
                else:
                    tool_retries[action_name] = tool_retries.get(action_name, 0) + 1
                    if tool_retries[action_name] >= MAX_TOOL_RETRIES:
                        unavailable_tools.add(action_name)
                        logger.warning(f"工具 {action_name} 已被禁用" f"（连续失败 {tool_retries[action_name]} 次）")

                conversation = self._append_step_to_conversation(
                    conversation,
                    response_text,
                    observation,
                )
                conversation = self._maybe_compress_conversation(conversation)
                continue

        # 资源耗尽 → 降级
        reason = "step_limit" if effective_steps >= effective_max else "llm_call_limit"
        logger.warning(
            f"Agent stream 资源耗尽: reason={reason}, "
            f"effective_steps={effective_steps}, total_llm_calls={total_llm_calls}"
        )
        degraded = await self._build_degraded_result(
            query=query,
            sources=all_sources,
            tool_calls=tool_calls_trace,
            effective_steps=effective_steps,
            total_llm_calls=total_llm_calls,
            unavailable_tools=list(unavailable_tools),
            metrics=[],
            reason=reason,
            session_id=session_id,
            redis_memory=redis_memory,
        )

        yield {
            "type": "status",
            "phase": "generating",
            "detail": "正在生成降级回答...",
        }
        for i in range(0, len(degraded.answer), 100):
            yield {"type": "content", "data": degraded.answer[i : i + 100]}

        yield {
            "type": "metadata",
            "answer": degraded.answer,
            "sources": degraded.sources,
            "tool_calls": degraded.tool_calls,
            "route": "agent",
            "steps": effective_steps,
            "completion": degraded.completion,
        }

    # ── 辅助方法 ────────────────────────────────────────────────

    @staticmethod
    def _smart_truncate(text: str, max_len: int) -> str:
        """智能截断：超过最大长度时保留首尾重要部分"""
        if len(text) <= max_len:
            return text
        head_len = int(max_len * 0.7)
        tail_len = max_len - head_len - 5
        return text[:head_len] + "...\n..." + text[-tail_len:]

    def _append_step_to_conversation(self, conversation: str, response_text: str, observation: str) -> str:
        """将完成的工具调用步骤追加到对话，observation 做智能截断"""
        truncated_obs = self._smart_truncate(observation, LLM_OBSERVATION_MAX_LEN)
        return conversation + f"\n\n{response_text}\nObservation: {truncated_obs}"

    def _maybe_compress_conversation(self, conversation: str) -> str:
        """如果对话过长，压缩旧的观测内容"""
        if len(conversation) <= CONVERSATION_COMPRESS_THRESHOLD:
            return conversation

        parts = conversation.split("Observation:")
        if len(parts) <= 2:
            return conversation

        result_parts = parts[:-1]
        last_obs_content = parts[-1]

        compressed: List[str] = []
        for i, part in enumerate(result_parts):
            if i == 0:
                compressed.append(part)
            else:
                obs_end = part.find("\n\n")
                if obs_end > 150:
                    compressed.append(f"Observation:[中间结果已压缩，{len(part[:obs_end])} 字符]")
                    if obs_end != -1:
                        compressed.append(part[obs_end:])
                elif obs_end != -1:
                    compressed.append(f"Observation:{part}")
                else:
                    compressed.append(f"Observation:{part[:150]}...")

        result = "Observation:".join(compressed) + last_obs_content
        logger.debug(f"对话压缩: {len(conversation)} -> {len(result)} 字符")
        return result

    async def _build_degraded_result(
        self,
        query: str,
        sources: List[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        effective_steps: int,
        total_llm_calls: int,
        unavailable_tools: List[str],
        metrics: List[Dict[str, Any]],
        reason: str,
        session_id: Optional[str] = None,
        redis_memory: Optional[RedisConversationMemory] = None,
    ) -> AgentResult:
        """构建降级回答（不调用 LLM，确定性拼接）"""
        successful_calls = [t for t in tool_calls if t.get("success", True)]
        failed_calls = [t for t in tool_calls if not t.get("success", True)]

        if successful_calls:
            answer_parts = [
                "⚠️ 由于执行步数已达上限，以下回答基于部分已有信息生成：",
                "",
            ]
            for tc in successful_calls:
                tool_name = tc.get("tool", "unknown")
                obs = tc.get("observation", "")
                answer_parts.append(f"【{tool_name}】{obs}")
            answer_parts.append("")

            if unavailable_tools:
                answer_parts.append(f"以下工具因故障被禁用：{', '.join(unavailable_tools)}")
            if reason == "step_limit":
                answer_parts.append("建议您将复杂问题拆分为更简单的子问题分别提问。")
            elif reason == "format_error":
                answer_parts.append("模型输出格式异常，建议稍后重试。")
            answer = "\n".join(answer_parts)
            completion: Literal["complete", "partial", "degraded"] = "partial"
        elif failed_calls:
            failed_tool_names = [t.get("tool", "") for t in failed_calls]
            answer = (
                f"抱歉，所有工具调用均失败。失败的工具："
                f"{', '.join(failed_tool_names)}。"
                f"建议您稍后重试，或尝试用更简单的方式提问。"
            )
            completion = "degraded"
        else:
            answer = "抱歉，无法完成您的请求。建议您将问题拆分成更简单的子问题，" "或换一种方式提问。"
            completion = "degraded"

        if session_id and redis_memory:
            try:
                await redis_memory.save_message("user", query)
                await redis_memory.save_message("assistant", answer)
            except Exception:
                pass

        return AgentResult(
            answer=answer,
            sources=sources,
            tool_calls=tool_calls,
            steps=effective_steps,
            forced=True,
            completion=completion,
            unavailable_tools=unavailable_tools,
            effective_steps=effective_steps,
            total_llm_calls=total_llm_calls,
            metrics=metrics,
        )


_agent_manager: Optional[AgentManager] = None


def get_agent_manager() -> AgentManager:
    """获取Agent管理器实例"""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
        logger.info("Agent管理器已初始化")
    return _agent_manager
