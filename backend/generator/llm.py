"""
LLM 依赖模块
提供 LLM 和嵌入模型的 FastAPI 依赖注入
直接使用 DashScope SDK，简洁高效
"""

import asyncio
import os
from asyncio import Queue
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Annotated, Any, AsyncGenerator, Dict, List, Optional

from dashscope import Generation, TextEmbedding
from fastapi import Depends

from backend.core.config import settings

# 确保 API Key 已设置
if settings.dashscope_api_key:
    os.environ["DASHSCOPE_API_KEY"] = settings.dashscope_api_key

# 容错机制
from backend.generator.llm_fault_tolerance import create_safe_llm


class AsyncLLM:
    """异步 LLM 封装 - 性能优化"""

    def __init__(self):
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def invoke(self, prompt: str, **kwargs) -> Any:
        """异步调用 - 使用线程池执行（Completion 模式，兼容旧接口）"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(self._executor, self._sync_invoke, prompt, kwargs)
        return response

    def _sync_invoke(self, prompt: str, kwargs) -> Any:
        """同步调用（在线程池中执行）"""
        response = Generation.call(
            model=self.model,
            prompt=prompt,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            result_format="message",
        )
        return response

    async def invoke_messages(self, messages: List[Dict[str, str]], **kwargs) -> Any:
        """异步调用 - 使用 Chat Messages 模式（结构化消息）

        Args:
            messages: [{"role": "system", "content": "..."},
                        {"role": "user", "content": "..."}]
            **kwargs: 同 invoke

        Returns:
            DashScope API 响应
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_invoke_messages, messages, kwargs)

    def _sync_invoke_messages(self, messages: List[Dict[str, str]], kwargs) -> Any:
        """同步调用 Messages 模式（在线程池中执行）"""
        response = Generation.call(
            model=self.model,
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            result_format="message",
        )
        return response

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """异步流式调用"""
        loop = asyncio.get_event_loop()
        queue: Queue = asyncio.Queue(maxsize=10)

        def _worker():
            """在单独线程中运行的工作函数"""
            try:
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    result_format="message",
                    stream=True,
                )

                last_content = ""
                for chunk in response:
                    if chunk.status_code == 200:
                        content = chunk.output["choices"][0]["message"]["content"]
                        delta = content[len(last_content) :]
                        if delta:
                            asyncio.run_coroutine_threadsafe(queue.put(delta), loop)
                        last_content = content
                    else:
                        asyncio.run_coroutine_threadsafe(queue.put(f"[错误: {chunk.message}]"), loop)
                        break
            except Exception as e:
                asyncio.run_coroutine_threadsafe(queue.put(f"[错误: {str(e)}]"), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        # 使用线程池执行
        self._executor.submit(_worker)

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    def close(self):
        """关闭线程池"""
        self._executor.shutdown(wait=True)


class SimpleLLM:
    """简化版 LLM 封装"""

    def __init__(self):
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self._executor = ThreadPoolExecutor(max_workers=2)

    def invoke(self, prompt: str, **kwargs) -> Any:
        """同步调用"""
        response = Generation.call(
            model=self.model,
            prompt=prompt,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            result_format="message",
        )
        return response

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """异步流式调用（使用线程池避免线程泄漏）"""
        loop = asyncio.get_event_loop()
        queue: Queue = asyncio.Queue(maxsize=10)

        def _worker():
            """在单独线程中运行的工作函数"""
            response = Generation.call(
                model=self.model,
                prompt=prompt,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                result_format="message",
                stream=True,
            )

            last_content = ""
            for chunk in response:
                if chunk.status_code == 200:
                    content = chunk.output["choices"][0]["message"]["content"]
                    delta = content[len(last_content) :]
                    if delta:
                        asyncio.run_coroutine_threadsafe(queue.put(delta), loop)
                    last_content = content
                else:
                    asyncio.run_coroutine_threadsafe(queue.put(f"[错误: {chunk.message}]"), loop)
                    break
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        self._executor.submit(_worker)

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    def close(self):
        """关闭线程池"""
        self._executor.shutdown(wait=True)


class SimpleEmbeddings:
    """简化版嵌入模型封装"""

    def __init__(self):
        self.model = settings.embedding_model

    def embed_query(self, text: str) -> List[float]:
        """单个文本嵌入"""
        response = TextEmbedding.call(model=self.model, input=text)
        if response.status_code == 200:
            return response.output["embeddings"][0]["embedding"]
        raise Exception(f"嵌入失败: {response.message}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量文本嵌入"""
        response = TextEmbedding.call(model=self.model, input=texts)
        if response.status_code == 200:
            return [item["embedding"] for item in response.output["embeddings"]]
        raise Exception(f"嵌入失败: {response.message}")


class CachedEmbeddings:
    """带缓存的嵌入模型封装 - 性能优化"""

    def __init__(self):
        self.model = settings.embedding_model
        self._cache_enabled = True
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def embed_query(self, text: str) -> List[float]:
        """单个文本嵌入（带缓存）"""
        if self._cache_enabled:
            from backend.memory.cache import cache_manager

            cached = await cache_manager.get_embedding(text)
            if cached:
                return cached

        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(self._executor, self._sync_embed_query, text)

        if self._cache_enabled:
            from backend.memory.cache import cache_manager

            await cache_manager.set_embedding(text, embedding)

        return embedding

    def _sync_embed_query(self, text: str) -> List[float]:
        """同步嵌入查询"""
        response = TextEmbedding.call(model=self.model, input=text)
        if response.status_code == 200:
            return response.output["embeddings"][0]["embedding"]
        raise Exception(f"嵌入失败: {response.message}")

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量文本嵌入（带缓存优化）"""
        if self._cache_enabled:
            from backend.memory.cache import cache_manager

            cached_results = await cache_manager.get_embeddings_batch(texts)

            uncached_texts = [t for t in texts if cached_results[t] is None]

            if uncached_texts:
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(self._executor, self._sync_embed_documents, uncached_texts)

                embeddings_dict = {}
                for text, embedding in zip(uncached_texts, embeddings):
                    embeddings_dict[text] = embedding

                await cache_manager.set_embeddings_batch(embeddings_dict)

            result: List[List[float]] = []
            for text in texts:
                cached = cached_results[text]
                if cached is not None:
                    result.append(cached)
                else:
                    loop = asyncio.get_event_loop()
                    embedding = await loop.run_in_executor(self._executor, self._sync_embed_query, text)
                    result.append(embedding)

            return result

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_embed_documents, texts)

    def _sync_embed_documents(self, texts: List[str]) -> List[List[float]]:
        """同步批量嵌入"""
        response = TextEmbedding.call(model=self.model, input=texts)
        if response.status_code == 200:
            return [item["embedding"] for item in response.output["embeddings"]]
        raise Exception(f"嵌入失败: {response.message}")

    def disable_cache(self):
        """禁用缓存"""
        self._cache_enabled = False

    def enable_cache(self):
        """启用缓存"""
        self._cache_enabled = True

    def close(self):
        """关闭线程池"""
        self._executor.shutdown(wait=True)


@lru_cache()
def get_llm() -> SimpleLLM:
    """获取 LLM 实例（带缓存）"""
    return SimpleLLM()


@lru_cache()
def get_async_llm() -> Any:
    """获取异步 LLM 实例（带线程池和容错机制）"""
    base_llm = AsyncLLM()
    return create_safe_llm(base_llm)


@lru_cache()
def get_embeddings() -> SimpleEmbeddings:
    """获取嵌入模型实例（带缓存）"""
    return SimpleEmbeddings()


@lru_cache()
def get_cached_embeddings() -> CachedEmbeddings:
    """获取带缓存的嵌入模型实例"""
    return CachedEmbeddings()


LLMDep = Annotated[SimpleLLM, Depends(get_llm)]
AsyncLLMDep = Annotated[AsyncLLM, Depends(get_async_llm)]
EmbeddingsDep = Annotated[SimpleEmbeddings, Depends(get_embeddings)]
CachedEmbeddingsDep = Annotated[CachedEmbeddings, Depends(get_cached_embeddings)]
