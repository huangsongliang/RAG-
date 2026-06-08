"""
LLM 容错机制模块
提供重试和熔断功能，确保LLM服务的稳定性和可靠性
"""

import asyncio
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional, Tuple

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class RetryConfig:
    """重试配置"""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0,
        retry_on_exceptions: Tuple = (Exception,),
    ):
        """
        Args:
            max_retries: 最大重试次数
            initial_delay: 初始延迟（秒）
            backoff_factor: 退避因子
            max_delay: 最大延迟（秒）
            retry_on_exceptions: 需要重试的异常类型
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.retry_on_exceptions = retry_on_exceptions


class CircuitBreaker:
    """熔断器实现 - 防止服务雪崩"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 1,
    ):
        """
        Args:
            failure_threshold: 失败阈值，超过此值触发熔断
            recovery_timeout: 熔断恢复时间（秒）
            half_open_max_requests: 半开状态下允许的最大请求数
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        # 状态
        self._state: str = "closed"  # closed, open, half_open
        self._failure_count: int = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_requests: int = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        """获取当前状态"""
        return self._state

    async def _transition_to_open(self):
        """转换到熔断状态"""
        self._state = "open"
        self._last_failure_time = datetime.now()
        logger.warning("熔断器已打开，所有请求将被拒绝")

    async def _transition_to_half_open(self):
        """转换到半开状态"""
        self._state = "half_open"
        self._failure_count = 0
        self._half_open_requests = 0
        logger.info("熔断器进入半开状态，允许部分请求")

    async def _transition_to_closed(self):
        """转换到关闭状态（正常状态）"""
        self._state = "closed"
        self._failure_count = 0
        self._half_open_requests = 0
        logger.info("熔断器已关闭，恢复正常请求")

    async def _check_recovery(self):
        """检查是否可以尝试恢复"""
        if self._last_failure_time and (datetime.now() - self._last_failure_time) >= timedelta(
            seconds=self.recovery_timeout
        ):
            await self._transition_to_half_open()

    async def allow_request(self) -> bool:
        """检查是否允许请求通过"""
        async with self._lock:
            if self._state == "closed":
                return True

            if self._state == "open":
                await self._check_recovery()
                return False

            if self._state == "half_open":
                if self._half_open_requests < self.half_open_max_requests:
                    self._half_open_requests += 1
                    return True
                return False

        return False

    async def record_failure(self):
        """记录失败"""
        async with self._lock:
            if self._state == "half_open":
                # 半开状态下失败，立即回到熔断状态
                await self._transition_to_open()
            elif self._state == "closed":
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    await self._transition_to_open()

    async def record_success(self):
        """记录成功"""
        async with self._lock:
            if self._state == "half_open":
                # 半开状态下成功，恢复到关闭状态
                await self._transition_to_closed()
            elif self._state == "closed":
                # 重置失败计数
                if self._failure_count > 0:
                    self._failure_count = 0


class LLMRetry:
    """LLM重试装饰器"""

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()

    def __call__(self, func: Callable) -> Callable:
        """装饰器实现"""

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(self.config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except self.config.retry_on_exceptions as e:
                    last_exception = e

                    if attempt == self.config.max_retries:
                        logger.error(f"LLM调用失败，已达到最大重试次数 {self.config.max_retries}")
                        break

                    # 计算延迟（指数退避）
                    delay = min(
                        self.config.initial_delay * (self.config.backoff_factor**attempt), self.config.max_delay
                    )

                    logger.warning(f"LLM调用失败（第 {attempt + 1} 次尝试），{delay:.2f}秒后重试: {str(e)}")

                    await asyncio.sleep(delay)

            raise last_exception

        return wrapper


class LLMFallback:
    """LLM降级策略"""

    @staticmethod
    def get_default_response(prompt: str = "") -> dict:
        """获取默认响应（降级时使用）"""
        return {"output": {"choices": [{"message": {"content": "抱歉，当前服务暂时不可用，请稍后重试。"}}]}}

    @staticmethod
    def get_default_messages_response(messages: list = None) -> dict:
        """获取 Messages 模式的默认降级响应"""
        return {"output": {"choices": [{"message": {"content": "抱歉，当前服务暂时不可用，请稍后重试。"}}]}}

    @staticmethod
    def get_empty_response() -> dict:
        """获取空响应"""
        return {"output": {"choices": [{"message": {"content": ""}}]}}


class SafeLLM:
    """安全LLM封装 - 整合重试和熔断机制"""

    def __init__(
        self,
        llm,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        """
        Args:
            llm: 原始LLM实例
            retry_config: 重试配置
            circuit_breaker: 熔断器实例
        """
        self._llm = llm
        self._retry = LLMRetry(retry_config)
        self._circuit_breaker = circuit_breaker or CircuitBreaker()

    async def invoke(self, prompt: str, **kwargs) -> Any:
        """安全调用LLM - 带重试和熔断"""
        # 检查熔断器状态
        if not await self._circuit_breaker.allow_request():
            logger.warning("熔断器已打开，返回降级响应")
            return LLMFallback.get_default_response(prompt)

        try:
            # 使用重试装饰器包装调用
            @self._retry
            async def _safe_invoke():
                return await self._llm.invoke(prompt, **kwargs)

            result = await _safe_invoke()

            # 记录成功
            await self._circuit_breaker.record_success()

            return result

        except Exception as e:
            # 记录失败
            await self._circuit_breaker.record_failure()
            logger.error(f"LLM调用失败（已熔断）: {str(e)}")

            # 返回降级响应
            return LLMFallback.get_default_response(prompt)

    async def invoke_messages(self, messages, **kwargs) -> Any:
        """安全调用LLM（Messages 模式）- 带重试和熔断"""
        if not await self._circuit_breaker.allow_request():
            logger.warning("熔断器已打开，返回降级响应")
            return LLMFallback.get_default_messages_response(messages)

        try:

            @self._retry
            async def _safe_invoke():
                return await self._llm.invoke_messages(messages, **kwargs)

            result = await _safe_invoke()
            await self._circuit_breaker.record_success()
            return result

        except Exception as e:
            await self._circuit_breaker.record_failure()
            logger.error(f"LLM Messages 调用失败（已熔断）: {str(e)}")
            return LLMFallback.get_default_messages_response(messages)

    async def stream(self, prompt: str, **kwargs) -> Any:
        """安全流式调用LLM"""
        # 对于流式调用，先检查熔断器状态
        if not await self._circuit_breaker.allow_request():
            logger.warning("熔断器已打开，返回降级响应")
            yield "抱歉，当前服务暂时不可用，请稍后重试。"
            return

        try:
            # 流式调用不进行重试（因为是连续的流）
            async for chunk in self._llm.stream(prompt, **kwargs):
                yield chunk

            # 记录成功
            await self._circuit_breaker.record_success()

        except Exception as e:
            # 记录失败
            await self._circuit_breaker.record_failure()
            logger.error(f"LLM流式调用失败（已熔断）: {str(e)}")

            # 返回降级响应
            yield "抱歉，当前服务暂时不可用，请稍后重试。"

    def close(self):
        """关闭LLM"""
        if hasattr(self._llm, "close"):
            self._llm.close()


# 全局熔断器实例
_global_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30, half_open_max_requests=1)


def get_circuit_breaker() -> CircuitBreaker:
    """获取全局熔断器实例"""
    return _global_circuit_breaker


def create_safe_llm(llm) -> SafeLLM:
    """创建安全LLM实例"""
    return SafeLLM(
        llm=llm,
        retry_config=RetryConfig(max_retries=3, initial_delay=1.0, backoff_factor=2.0, max_delay=10.0),
        circuit_breaker=_global_circuit_breaker,
    )
