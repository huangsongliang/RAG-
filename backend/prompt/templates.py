"""提示词管理模块
集中管理所有提示词模板，支持动态配置和多语言
"""

from typing import Dict


class PromptTemplate:
    """提示词模板基类"""

    def __init__(self, template: str, variables: list):
        self.template = template
        self.variables = variables

    def format(self, **kwargs) -> str:
        """格式化提示词"""
        missing_vars = [v for v in self.variables if v not in kwargs]
        if missing_vars:
            raise ValueError(f"缺少必要变量: {missing_vars}")
        return self.template.format(**kwargs)


class PromptManager:
    """提示词管理器"""

    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {}

    def register(self, name: str, template: str, variables: list):
        """注册提示词模板"""
        self.templates[name] = PromptTemplate(template, variables)

    def get(self, name: str) -> PromptTemplate:
        """获取提示词模板"""
        if name not in self.templates:
            raise ValueError(f"未找到提示词模板: {name}")
        return self.templates[name]

    def format(self, name: str, **kwargs) -> str:
        """获取并格式化提示词"""
        template = self.get(name)
        return template.format(**kwargs)


# 默认提示词模板
default_prompts = PromptManager()

# RAG 问答提示词 - 正常助手风格
default_prompts.register(
    name="rag_qa",
    template="""你是一个智能助手，擅长根据提供的参考资料回答用户的问题。

【参考资料】
{context}

【问题】
{question}

【回答要求】
1. 必须基于提供的参考资料进行回答，不要编造信息
2. 如果参考资料中没有相关信息，直接告诉我："抱歉，关于这个问题我没有找到相关的资料"
3. 用简洁、清晰、易懂的语言回答
4. 保持回答的准确性和专业性
5. 如果需要，可以适当举例说明

【回答】
""",
    variables=["context", "question"],
)

# 文档总结提示词
default_prompts.register(
    name="document_summary",
    template="""请总结以下文档内容：

文档内容：
{document}

要求：
1. 提取关键信息
2. 保持原文意思不变
3. 用简洁的语言总结
4. 用中文回答

总结：
""",
    variables=["document"],
)

# 问题重写提示词
default_prompts.register(
    name="question_rewrite",
    template="""请将以下问题重写为更清晰、更准确的形式：

原问题：{question}

重写后的问题：
""",
    variables=["question"],
)

# 多模态问答提示词
default_prompts.register(
    name="multimodal_qa",
    template="""你是一个智能助手，擅长理解图片内容并结合文本资料回答用户的问题。

【图片描述】
{context}

【问题】
{question}

【回答要求】
1. 结合图片描述中的信息回答问题
2. 如果图片描述中有相关信息，优先基于图片内容回答
3. 用简洁、清晰、易懂的语言回答
4. 保持回答的准确性和专业性

【回答】
""",
    variables=["context", "question"],
)

# 多轮对话提示词 - 正常助手风格
default_prompts.register(
    name="multi_turn",
    template="""你是一个智能助手，擅长根据提供的参考资料和对话历史回答用户的问题。

【对话历史】
{history}

【当前问题】
{question}

【参考资料】
{context}

【回答要求】
1. 必须基于提供的参考资料和对话历史进行回答，不要编造信息
2. 如果参考资料中没有相关信息，直接告诉我："抱歉，关于这个问题我没有找到相关的资料"
3. 用简洁、清晰、易懂的语言回答
4. 保持回答的准确性和专业性
5. 要记得之前的对话内容，保持回答的连贯性
6. 如果需要，可以适当举例说明

【回答】
""",
    variables=["history", "question", "context"],
)
