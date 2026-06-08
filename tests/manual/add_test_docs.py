"""
添加测试文档到知识库
"""

import httpx

BASE_URL = "http://localhost:8001"

documents = [
    """企业级智能文档问答平台基于RAG（检索增强生成）架构构建，支持多种文档格式上传和智能检索。系统采用FastAPI作为后端框架，Vue3+TypeScript作为前端框架，提供企业级的文档管理和智能问答功能。平台集成了通义千问大语言模型，支持流式输出、多轮对话记忆、混合检索等高级特性。""",
    """混合检索系统是平台的核心检索引擎，结合了向量检索和BM25全文检索两种方式。向量检索使用Text Embedding V2模型生成1536维嵌入向量存入ChromaDB；BM25全文检索使用jieba分词器进行中文分词和rank-bm25算法计算相关性。默认配置为向量权重0.7、BM25权重0.3进行加权融合，并通过BGE-reranker-base进行结果重排序。""",
    """平台部署支持多种方式：单机部署使用Docker Compose一键启动Redis、后端API和前端服务；生产环境使用Kubernetes Helm Chart进行容器化编排部署；数据库层支持MySQL持久化存储和Redis缓存加速。系统提供完整的监控方案，包括Prometheus指标采集、Grafana可视化面板和AlertManager告警通知。""",
]

print("=" * 50)
print("  添加测试文档到知识库")
print("=" * 50)
print(f"\n文档数量: {len(documents)}")

try:
    resp = httpx.post(
        f"{BASE_URL}/api/docs/add", json={"documents": documents}, timeout=30
    )
    print(f"\n状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 添加成功！count: {data.get('count')}")
        print(f"IDs: {data.get('ids')}")
    else:
        print(f"⚠️ 响应: {resp.text}")
except Exception as e:
    print(f"\n❌ 出错: {e}")
    import traceback

    traceback.print_exc()
