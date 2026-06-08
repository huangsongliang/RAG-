"""多模态视觉处理模块
支持图片理解和视觉问答
"""

import base64
from typing import Dict, List, Optional

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class VisionProcessor:
    """视觉处理器 - 支持多种视觉模型"""

    def __init__(
        self,
        model_provider: str = "openai",
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Args:
            model_provider: 模型提供商 (openai/anthropic/qwen)
            model_name: 模型名称
            api_key: API 密钥
        """
        self.model_provider = model_provider
        self.model_name = model_name or self._get_default_model()
        self.api_key = api_key
        self._client = None

    def _get_default_model(self) -> str:
        """获取默认模型"""
        defaults = {
            "openai": "gpt-4o",
            "anthropic": "claude-3-opus-20240229",
            "qwen": "qwen-vl-max",
        }
        return defaults.get(self.model_provider, "gpt-4o")

    def _init_client(self):
        """初始化客户端"""
        if self._client is None:
            if self.model_provider == "openai":
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
            elif self.model_provider == "anthropic":
                from anthropic import Anthropic

                self._client = Anthropic(api_key=self.api_key)
            elif self.model_provider == "qwen":
                import dashscope
                from dashscope import MultiModalConversation

                self._client = {"dashscope": dashscope, "mmc": MultiModalConversation}
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")

            logger.info(f"视觉客户端初始化成功: {self.model_provider} - {self.model_name}")

    def encode_image(self, image_path: str) -> str:
        """将图片编码为 base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def describe_image(self, image_path: str, prompt: Optional[str] = None) -> str:
        """
        描述图片内容

        Args:
            image_path: 图片路径
            prompt: 可选的描述提示词

        Returns:
            图片描述文本
        """
        self._init_client()

        if prompt is None:
            prompt = "请详细描述这张图片的内容，包括场景、物体、文字等所有重要信息。"

        try:
            if self.model_provider == "openai":
                return self._describe_openai(image_path, prompt)
            elif self.model_provider == "anthropic":
                return self._describe_anthropic(image_path, prompt)
            elif self.model_provider == "qwen":
                return self._describe_qwen(image_path, prompt)
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")

        except Exception as e:
            logger.error(f"图片描述失败: {str(e)}")
            raise

    def _describe_openai(self, image_path: str, prompt: str) -> str:
        """使用 OpenAI GPT-4V 描述图片"""
        base64_image = self.encode_image(image_path)

        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
            max_tokens=1000,
        )

        return response.choices[0].message.content

    def _describe_anthropic(self, image_path: str, prompt: str) -> str:
        """使用 Anthropic Claude 描述图片"""
        base64_image = self.encode_image(image_path)

        response = self._client.messages.create(
            model=self.model_name,
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                    ],
                }
            ],
        )

        return response.content[0].text

    def _describe_qwen(self, image_path: str, prompt: str) -> str:
        """使用阿里 Qwen-VL 描述图片"""
        # 解析为绝对路径（修复 Windows 短名路径如 ~1 的问题）
        import os

        from dashscope import MultiModalConversation

        resolved_path = os.path.abspath(image_path)

        messages = [
            {
                "role": "user",
                "content": [{"text": prompt}, {"image": resolved_path}],
            }
        ]

        response = MultiModalConversation.call(model=self.model_name, messages=messages)

        if response.status_code == 200:
            return response.output.choices[0]["message"]["content"][0]["text"]
        else:
            raise Exception(f"Qwen API 错误: {response.message}")

    def answer_about_image(self, image_path: str, question: str, context: Optional[str] = None) -> str:
        """
        根据图片回答问题

        Args:
            image_path: 图片路径
            question: 问题
            context: 可选的上下文信息

        Returns:
            回答文本
        """
        self._init_client()

        base_prompt = "你是一个专业的图片分析助手，请根据图片内容回答问题。"
        if context:
            base_prompt += f"\n\n上下文信息: {context}"
        base_prompt += f"\n\n问题: {question}"

        try:
            if self.model_provider == "openai":
                return self._answer_openai(image_path, base_prompt)
            elif self.model_provider == "anthropic":
                return self._answer_anthropic(image_path, base_prompt)
            elif self.model_provider == "qwen":
                return self._answer_qwen(image_path, base_prompt)
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")

        except Exception as e:
            logger.error(f"图片问答失败: {str(e)}")
            raise

    def _answer_openai(self, image_path: str, prompt: str) -> str:
        """使用 OpenAI GPT-4V 回答问题"""
        base64_image = self.encode_image(image_path)

        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
            max_tokens=1500,
        )

        return response.choices[0].message.content

    def _answer_anthropic(self, image_path: str, prompt: str) -> str:
        """使用 Anthropic Claude 回答问题"""
        base64_image = self.encode_image(image_path)

        response = self._client.messages.create(
            model=self.model_name,
            max_tokens=1500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                    ],
                }
            ],
        )

        return response.content[0].text

    def _answer_qwen(self, image_path: str, prompt: str) -> str:
        """使用阿里 Qwen-VL 回答问题"""
        from dashscope import MultiModalConversation

        messages = [
            {
                "role": "user",
                "content": [{"text": prompt}, {"image": image_path}],
            }
        ]

        response = MultiModalConversation.call(model=self.model_name, messages=messages)

        if response.status_code == 200:
            return response.output.choices[0]["message"]["content"][0]["text"]
        else:
            raise Exception(f"Qwen API 错误: {response.message}")

    def extract_text_from_image(self, image_path: str) -> str:
        """从图片中提取文字（OCR）"""
        self._init_client()

        prompt = "请提取图片中的所有文字内容，保持原有格式。"

        try:
            if self.model_provider == "openai":
                return self._extract_openai(image_path, prompt)
            elif self.model_provider == "anthropic":
                return self._extract_anthropic(image_path, prompt)
            elif self.model_provider == "qwen":
                return self._extract_qwen(image_path, prompt)
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")

        except Exception as e:
            logger.error(f"图片文字提取失败: {str(e)}")
            raise

    def _extract_openai(self, image_path: str, prompt: str) -> str:
        """使用 OpenAI GPT-4V 提取文字"""
        base64_image = self.encode_image(image_path)

        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
            max_tokens=2000,
        )

        return response.choices[0].message.content

    def _extract_anthropic(self, image_path: str, prompt: str) -> str:
        """使用 Anthropic Claude 提取文字"""
        base64_image = self.encode_image(image_path)

        response = self._client.messages.create(
            model=self.model_name,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                    ],
                }
            ],
        )

        return response.content[0].text

    def _extract_qwen(self, image_path: str, prompt: str) -> str:
        """使用阿里 Qwen-VL 提取文字"""
        from dashscope import MultiModalConversation

        messages = [
            {
                "role": "user",
                "content": [{"text": prompt}, {"image": image_path}],
            }
        ]

        response = MultiModalConversation.call(model=self.model_name, messages=messages)

        if response.status_code == 200:
            return response.output.choices[0]["message"]["content"][0]["text"]
        else:
            raise Exception(f"Qwen API 错误: {response.message}")

    def batch_describe(self, image_paths: List[str]) -> List[Dict[str, str]]:
        """批量描述多张图片"""
        results = []

        for image_path in image_paths:
            try:
                description = self.describe_image(image_path)
                results.append(
                    {
                        "image_path": image_path,
                        "description": description,
                        "status": "success",
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "image_path": image_path,
                        "description": "",
                        "status": "failed",
                        "error": str(e),
                    }
                )

        return results


def get_vision_processor(
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> VisionProcessor:
    """获取视觉处理器实例"""
    return VisionProcessor(
        model_provider=provider,
        model_name=model,
        api_key=api_key,
    )
