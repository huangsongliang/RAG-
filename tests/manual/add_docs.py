"""添加文档到知识库"""

import httpx

BASE_URL = "http://localhost:8000"

# 企业级知识库文档
documents = [
    """企业级智能文档问答平台基于RAG架构构建，支持多种文档格式上传和智能检索。系统采用FastAPI作为后端框架，Vue3+TypeScript作为前端构建，提供文档管理、智能问答、数据分析等功能。""",
    """混合检索系统结合向量检索和BM25全文检索。向量检索使用Text Embedding V2模型生成1536维嵌入向量存入ChromaDB；BM25检索使用jieba分词器和rank-bm25算法。默认向量权重0.7、BM25权重0.3，通过BGE-reranker-base重排序。""",
    """平台集成通义千问(DashScope)作为核心大语言模型，默认使用qwen-max模型。支持流式输出、多轮对话记忆、上下文管理和Token统计。Redis用于缓存加速和会话管理。""",
    """系统部署架构包含Nginx反向代理、FastAPI后端服务集群、Redis缓存、ChromaDB向量数据库和MySQL关系数据库。支持Docker Compose单机部署和Kubernetes集群部署两种模式。""",
    """平台提供完整的监控方案：Prometheus采集应用和基础设施指标，Grafana提供可视化面板，AlertManager处理告警通知。管理员可通过监控面板实时查看请求量、响应时间、错误率等关键指标。""",
]

print("添加文档到知识库...")
response = httpx.post(
    f"{BASE_URL}/api/docs/add", json={"documents": documents}, timeout=30
)

print(f"状态码: {response.status_code}")
print(f"响应: {response.text}")
