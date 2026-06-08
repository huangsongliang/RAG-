# 企业级智能文档问答平台

> 基于 RAG（Retrieval-Augmented Generation）的企业级知识库问答系统
> **246 API 端点 · ReAct Agent · 知识图谱 · 8 容器全栈部署**

---

## 核心特性

- **统一对话入口**：一个输入框自动路由到 RAG / Agent / 多模态，无需手动切换模式
- **ReAct Agent**：8 工具（文档问答、知识图谱、数据查询、图表生成、摘要、计算器、时间、多模态），动态步数控制，三层降级
- **混合检索**：BM25（jieba 分词）+ 向量（1536d）双路召回，RRF 无参融合，BGE-reranker Cross-Encoder 精排
- **流式输出**：SSE 实时推送，前端纯文本首字渲染后切 Markdown
- **知识图谱**：HanLP NER + 38 条正则关系抽取 + LLM 兜底，代词消解，ECharts 力导向图可视化
- **文档管理**：PDF（PyMuPDF + OCR）、TXT、Markdown 上传，智能分块（语义感知 / 递归分割），内容指纹去重
- **会话持久化**：MySQL 存储对话历史，退出重进不丢失
- **RBAC 权限**：角色/用户/文档三级权限，JWT 认证，登录限流
- **审计日志**：完整操作记录，安全事件追踪，统计图表
- **工程化**：熔断器 + 指数退避重试 + 静态降级，Redis 令牌桶限流，RequestID 全链路追踪
- **监控**：Prometheus + Grafana + Loki + Promtail
- **测试**：92 Python 单测 + 26 前端单测 + 22 知识图谱 UI 自动化测试

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Element Plus + Vite + Pinia |
| 后端 | FastAPI + Python 3.11+ + LangChain 0.3+ |
| LLM | 通义千问 qwen-max（DashScope） |
| 嵌入模型 | text-embedding-v2（1536 维） |
| 向量库 | ChromaDB 0.5+ |
| 全文检索 | rank-bm25 + jieba |
| 重排序 | BGE-reranker-base（Cross-Encoder） |
| 缓存 | Redis 7.0+ |
| 数据库 | MySQL 8.0（SQLAlchemy 2.0 async + Alembic） |
| 包管理 | uv（后端）/ npm（前端） |
| 部署 | Docker Compose（8 容器） |

---

## 快速开始

### 环境要求

- Python >= 3.11，uv，Redis 7.0+，npm

### 1. 安装

```bash
uv sync                       # 后端
cd frontend && npm install    # 前端
```

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入 `DASHSCOPE_API_KEY` 和 `SECRET_KEY`。

### 3. 启动

```bash
# Redis
docker run -d -p 6379:6379 redis:7-alpine

# 后端（终端 1）
uv run uvicorn backend.main:app --reload --port 8000

# 前端（终端 2）
cd frontend && npm run dev
```

### 4. 访问

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| API 文档 | http://localhost:8000/docs |

---

## 架构概览

```
用户 → Nginx :8080 → API :8000 → 统一路由 /api/chat/send
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                  ▼
                 CHAT 模式         AGENT 模式        MULTIMODAL
              (纯 RAG 问答)     (ReAct 8 工具)    (qwen-vl-max)
                    │
     ┌──────────────┼──────────────┐
     ▼              ▼              ▼
  BM25 检索     向量检索       重排序
 (jieba+BM25) (ChromaDB)   (bge-reranker)
     │              │              │
     └──────────────┴──────────────┘
                    ▼
              RRF 融合 → qwen-max 生成 → SSE 流式
```

**LLM 容错**：指数退避重试（1s/2s/4s）→ 熔断器（5 次失败 OPEN 30s）→ 静态降级响应

---

## 项目结构（关键路径）

```
backend/
  api/unified_chat.py      # 统一对话入口，自动路由 CHAT/AGENT/MULTIMODAL
  agent/__init__.py        # ReAct Agent 引擎，8 工具注册，三层降级
  retrieval/hybrid_retriever.py  # BM25 + 向量 + RRF + Cross-Encoder
  chain/rag_chain.py       # RAG 流水线：检索→上下文→提示词→LLM
  generator/llm.py         # DashScope LLM + Embedding（同步/异步/缓存）
  generator/llm_fault_tolerance.py  # SafeLLM：重试+熔断+降级
  knowledge_graph/         # NER(HanLP) + 关系抽取(正则+LLM) + 图存储
  middleware/security.py    # XSS/SQL注入防护 + 限流
  core/config.py           # pydantic-settings 统一配置
  main.py                  # FastAPI 入口，25+ 路由注册
frontend/src/
  components/ChatArea.vue          # 统一对话界面（流式+Markdown+工具面板）
  components/KnowledgeGraphPage.vue # 知识图谱：文本抽取/浏览/统计三 Tab
  stores/auth.ts                   # 认证状态（localStorage JWT）
  router/index.ts                  # 路由守卫（requiresAuth）
tests/
  unit/            # 92 个 Python 单测
  ui/              # 22 个知识图谱 Playwright UI 测试 + conftest
```

---

## 生产部署

```bash
# 构建前端
cd frontend && npm run build

# 启动全部 8 个容器
docker compose -f docker-compose.prod.yml up -d
```

| 服务 | 端口 |
|------|------|
| Nginx（前端 + API 代理） | 8080 / 8443 |
| FastAPI | 8082 |
| MySQL | 3307 |
| Redis | 6379 |
| Prometheus | 9090 |
| Grafana | 3000 |
| Loki | 3100 |

---

## 测试

```bash
# Python 单测
uv run pytest tests/unit/ -v

# 前端单测
cd frontend && node node_modules/vitest/vitest.mjs run

# 知识图谱 UI 自动化（需前后端运行中）
uv run pytest tests/ui/test_knowledge_graph.py -v
```

---

## 许可证

MIT License
