"""Agent 模块测试"""

import asyncio
import sys
sys.path.insert(0, "d:/code/sushi_digital_human")

from backend.agent import get_agent_manager
from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def test_agent_basic():
    """测试 Agent 基础功能"""
    logger.info("测试 Agent 基础功能...")

    agent_manager = get_agent_manager()

    # 测试直接回答
    result = await agent_manager.run("你好，请问你是做什么的")
    logger.info(f"直接回答测试: {result.answer[:50]}...")
    assert result.answer

    # 测试工具调用 - 计算器
    result = await agent_manager.run("计算 2 + 3 * 4")
    logger.info(f"计算器测试: steps={result.effective_steps}, completion={result.completion}")
    assert result.answer

    logger.info("✅ Agent 基础功能测试通过")


async def test_agent_with_memory():
    """测试 Agent 多轮对话记忆"""
    logger.info("测试 Agent 多轮对话记忆...")

    agent_manager = get_agent_manager()
    session_id = "test_session_agent_001"

    # 第一轮对话
    result1 = await agent_manager.run("我想了解一下Python", session_id=session_id)
    logger.info(f"第一轮: {result1.answer[:30]}...")

    # 第二轮对话（上下文关联）
    result2 = await agent_manager.run("它的优缺点是什么", session_id=session_id)
    logger.info(f"第二轮: {result2.answer[:30]}...")

    # 第三轮对话（继续上下文）
    result3 = await agent_manager.run("总结一下", session_id=session_id)
    logger.info(f"第三轮: {result3.answer[:30]}...")

    logger.info("✅ Agent 多轮对话记忆测试通过")


async def test_agent_tools():
    """测试 Agent 工具列表"""
    logger.info("测试 Agent 工具列表...")

    agent_manager = get_agent_manager()
    tools = agent_manager.tools

    logger.info(f"可用工具: {[tool.name for tool in tools]}")
    assert len(tools) >= 1

    logger.info("✅ Agent 工具列表测试通过")


async def main():
    """运行所有 Agent 测试"""
    logger.info("=" * 60)
    logger.info("开始测试 Agent 模块")
    logger.info("=" * 60)

    try:
        await test_agent_basic()
        await test_agent_with_memory()
        await test_agent_tools()

        logger.info("\n" + "=" * 60)
        logger.info("🎉 所有 Agent 测试通过！")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
