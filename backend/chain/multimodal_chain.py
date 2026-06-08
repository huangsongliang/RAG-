"""多模态 RAG 链
支持图片+文本的混合问答
"""

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional

from backend.chain.rag_chain import RAGChain
from backend.multimodal.vision_processor import get_vision_processor
from backend.prompt import default_prompts
from backend.utils.logger import get_logger
from backend.utils.performance import timed_operation

logger = get_logger(__name__)


class MultimodalRAGChain:
    """多模态 RAG 链"""

    def __init__(
        self,
        vision_provider: str = "openai",
        vision_model: Optional[str] = None,
        vision_api_key: Optional[str] = None,
    ):
        """初始化多模态 RAG 链"""
        self.rag_chain = RAGChain()
        self.vision_processor = get_vision_processor(
            provider=vision_provider,
            model=vision_model,
            api_key=vision_api_key,
        )

    def describe_images(self, image_paths: List[str]) -> List[str]:
        """批量描述图片"""
        descriptions = []

        for image_path in image_paths:
            try:
                desc = self.vision_processor.describe_image(image_path)
                descriptions.append(desc)
                logger.info(f"图片描述完成: {image_path}")
            except Exception as e:
                logger.error(f"图片描述失败 {image_path}: {str(e)}")
                descriptions.append(f"[图片描述失败: {str(e)}]")

        return descriptions

    def build_multimodal_context(self, text_context: str, image_descriptions: List[str]) -> str:
        """构建多模态上下文"""
        context_parts = [text_context]

        if image_descriptions:
            context_parts.append("\n\n=== 图片内容 ===")
            for i, desc in enumerate(image_descriptions, 1):
                context_parts.append(f"\n[图片 {i}]: {desc}")

        return "\n".join(context_parts)

    def generate_answer(
        self,
        query: str,
        text_context: str,
        image_descriptions: List[str],
        history: str = "",
    ) -> str:
        """生成多模态回答"""
        multimodal_context = self.build_multimodal_context(text_context, image_descriptions)

        if history:
            prompt = default_prompts.format(
                "multimodal_qa",
                history=history,
                question=query,
                context=multimodal_context,
            )
        else:
            prompt = default_prompts.format(
                "multimodal_qa",
                question=query,
                context=multimodal_context,
            )

        answer = self.rag_chain.generate(prompt)
        return answer

    async def async_generate_answer(
        self,
        query: str,
        text_context: str,
        image_descriptions: List[str],
        history: str = "",
    ) -> str:
        """异步生成多模态回答"""
        multimodal_context = self.build_multimodal_context(text_context, image_descriptions)

        if history:
            prompt = default_prompts.format(
                "multimodal_qa",
                history=history,
                question=query,
                context=multimodal_context,
            )
        else:
            prompt = default_prompts.format(
                "multimodal_qa",
                question=query,
                context=multimodal_context,
            )

        answer = await self.rag_chain.async_generate(prompt)
        return answer

    async def async_run(
        self,
        query: str,
        image_paths: Optional[List[str]] = None,
        top_k: int = 3,
        use_rag: bool = True,
        history: str = "",
    ) -> Dict[str, Any]:
        """异步执行多模态 RAG 流程"""
        with timed_operation("multimodal_rag_async_run"):
            documents = []
            text_context = ""

            if use_rag:
                documents = await self.rag_chain.async_retrieve(query, top_k=top_k)
                text_context = self.rag_chain.build_context(documents)

            image_descriptions = []
            if image_paths:
                loop = asyncio.get_event_loop()
                image_descriptions = await loop.run_in_executor(None, self.describe_images, image_paths)

            answer = await self.async_generate_answer(
                query=query,
                text_context=text_context,
                image_descriptions=image_descriptions,
                history=history,
            )

            return {
                "answer": answer,
                "query": query,
                "references": documents,
                "image_descriptions": image_descriptions,
                "context": text_context,
            }

    async def stream_run(
        self,
        query: str,
        image_descriptions: Optional[List[str]] = None,
        top_k: int = 3,
        use_rag: bool = True,
        history: str = "",
    ) -> AsyncGenerator[str, None]:
        """流式执行多模态 RAG 流程（image_descriptions 由调用方预计算避免重复）"""
        documents = []
        text_context = ""

        if use_rag:
            documents = await self.rag_chain.async_retrieve(query, top_k=top_k)
            text_context = self.rag_chain.build_context(documents)

        descs = image_descriptions or []
        multimodal_context = self.build_multimodal_context(text_context, descs)

        if history:
            prompt = default_prompts.format(
                "multimodal_qa",
                history=history,
                question=query,
                context=multimodal_context,
            )
        else:
            prompt = default_prompts.format(
                "multimodal_qa",
                question=query,
                context=multimodal_context,
            )

        async for chunk in self.rag_chain.async_llm.stream(prompt):
            yield chunk

    def answer_with_images(
        self,
        query: str,
        image_paths: List[str],
        context: str = "",
    ) -> str:
        """直接根据图片回答问题（不进行 RAG 检索）"""
        if not image_paths:
            return "请提供图片"

        image_descriptions = self.describe_images(image_paths)

        answer = self.generate_answer(
            query=query,
            text_context=context,
            image_descriptions=image_descriptions,
        )

        return answer

    async def async_answer_with_images(
        self,
        query: str,
        image_paths: List[str],
        context: str = "",
    ) -> str:
        """异步直接根据图片回答问题"""
        if not image_paths:
            return "请提供图片"

        loop = asyncio.get_event_loop()
        image_descriptions = await loop.run_in_executor(None, self.describe_images, image_paths)

        answer = await self.async_generate_answer(
            query=query,
            text_context=context,
            image_descriptions=image_descriptions,
        )

        return answer


_multimodal_rag_chain: Optional[MultimodalRAGChain] = None


def get_multimodal_rag_chain() -> MultimodalRAGChain:
    """获取多模态 RAG 链实例"""
    global _multimodal_rag_chain
    if _multimodal_rag_chain is None:
        from backend.core.config import settings

        provider = settings.vision_provider
        model = settings.vision_model
        api_key = settings.vision_api_key or None

        _multimodal_rag_chain = MultimodalRAGChain(
            vision_provider=provider,
            vision_model=model,
            vision_api_key=api_key,
        )
        logger.info("多模态 RAG 链已初始化")
    return _multimodal_rag_chain
