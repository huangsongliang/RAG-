# 项目技术栈文档

## 项目名称
企业级智能文档问答平台（基于 RAG 的企业知识库）

---

## 一、总体架构

采用前后端分离架构，核心编排层使用 LangChain，支持未来扩展为 Agent。

---

## 二、技术栈详细清单

### 1. 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | ^3.4 | 渐进式 JavaScript 框架 |
| TypeScript | ^5.0 | 类型安全 |
| Vite | ^5.0 | 构建工具 |
| Element Plus | ^2.6 | UI 组件库 |
| Axios | ^1.6 | HTTP 客户端 |
| marked | ^11.0 | Markdown 渲染 |
| vue-router | ^4.2 | 路由管理 |

### 2. 后端框架
| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 运行环境 |
| FastAPI | ^0.115 | Web 框架，自动生成 OpenAPI |
| Uvicorn | ^0.30 | ASGI 服务器 |
| Pydantic | ^2.7 | 数据验证与配置管理 |

### 3. 核心 AI 框架
| 技术 | 版本 | 用途 |
|------|------|------|
| LangChain | ^0.3 | 核心编排：链、检索器、记忆、代理 |
| langchain-community | ^0.3 | 第三方集成（DashScope、Redis 等） |
| langchain-core | ^0.3 | LCEL 基础组件 |

### 4. 大语言模型与嵌入
| 技术 | 用途 | 集成方式 |
|------|------|----------|
| DashScope (通义千问) | 文本生成 (qwen-max) | `ChatDashScope` |
| DashScope | 文本嵌入 (text_embedding_v2) | `DashScopeEmbeddings` |

### 5. 向量数据库
| 技术 | 环境 | 用途 |
|------|------|------|
| ChromaDB | 开发/测试 | 轻量级向量存储，支持内存/持久化 |
| Milvus | 生产（可选） | 分布式向量数据库，高可用 |

### 6. 混合检索与重排序
| 技术 | 用途 | 集成方式 |
|------|------|----------|
| rank_bm25 | BM25 关键词检索 | 自定义 `BM25Retriever` |
| BGE-reranker-base | 重排序模型 | `CrossEncoder` + `ContextualCompressionRetriever` |
| EnsembleRetriever | 多路召回融合 | LangChain 内置 |

### 7. 对话记忆与缓存
| 技术 | 用途 | 集成方式 |
|------|------|----------|
| Redis | 对话历史存储、高频结果缓存、限流 | `RedisChatMessageHistory` |
| LangChain Memory | 对话记忆管理 | `ConversationBufferMemory` |

### 8. 关系数据库
| 技术 | 用途 | 说明 |
|------|------|------|
| MySQL (生产) | 用户反馈、评估集、文档元数据 | 使用 SQLAlchemy 2.0 异步驱动 |
| SQLite (开发) | 原型快速验证 | 可选 |

### 9. 异步任务
| 技术 | 用途 | 说明 |
|------|------|------|
| Celery | 处理文档索引、批量评估 | 调用 LangChain 链 |
| Redis | Celery Broker & Result Backend | 与记忆缓存共用 Redis |

### 10. 监控与日志
| 技术 | 用途 | 说明 |
|------|------|------|
| Prometheus | 指标采集 | FastAPI 中间件自动埋点 |
| Grafana | 可视化仪表盘 | 查询延迟、命中率等 |
| Loguru | 日志记录 | 结构化日志输出 |

### 11. 部署与运维
| 技术 | 用途 | 说明 |
|------|------|------|
| Docker | 容器化 | 每个服务独立镜像 |
| Docker Compose | 本地编排 | 一键启动全套服务 |
| Nginx | 反向代理 + 静态文件 | 前端与 API 路由 |
| GitHub Actions | CI/CD | 自动化测试、评估脚本运行 |

### 12. 安全与认证
| 技术 | 用途 | 说明 |
|------|------|------|
| JWT | 用户身份认证 | FastAPI 依赖 `python-jose` |
| OAuth2 | 第三方登录（可选） | 对接微信/Google |
| 限流 | API 保护 | Redis + 自定义中间件 |
| CORS | 跨域资源共享 | FastAPI CORS Middleware |

### 13. 错误处理与边界
| 场景 | 处理策略 |
|------|----------|
| LLM 调用超时 | 重试机制（最多3次）+ 降级响应 |
| 向量库连接失败 | 优雅降级 + 告警通知 |
| 检索结果为空 | 返回预设兜底答案 |
| 文档解析失败 | 跳过并记录日志 |
| Redis 连接异常 | 降级为内存缓存 |

### 14. 项目目录结构
```
sushi_digital_human/
├── backend/                    # 后端应用
│   ├── api/                   # API 路由层
│   │   ├── __init__.py
│   │   ├── chat.py           # 对话接口
│   │   ├── health.py         # 健康检查
│   │   └── dependencies.py   # 依赖注入
│   ├── chain/                # LangChain 链定义
│   │   ├── __init__.py
│   │   ├── retrieval.py      # 检索链
│   │   └── rag.py            # RAG 主链
│   ├── retrieval/            # 检索模块
│   │   ├── __init__.py
│   │   ├── vector_store.py   # 向量存储
│   │   ├── bm25.py          # BM25 检索
│   │   └── reranker.py      # 重排序
│   ├── memory/               # 记忆模块
│   │   ├── __init__.py
│   │   └── history.py        # 对话历史
│   ├── generator/            # 生成器模块
│   │   ├── __init__.py
│   │   └── llm.py           # LLM 配置
│   ├── models/               # 数据模型
│   │   ├── __init__.py
│   │   ├── schemas.py        # Pydantic 模型
│   │   └── entities.py       # 实体定义
│   ├── core/                 # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py         # 配置管理
│   │   └── security.py       # 安全工具
│   ├── utils/                # 工具函数
│   │   ├── __init__.py
│   │   └── logger.py         # 日志工具
│   └── main.py               # FastAPI 入口
├── frontend/                  # 前端应用（后续）
├── data/                      # 数据目录
│   ├── raw/                  # 原始文档
│   └── processed/           # 处理后文档
├── tests/                     # 测试目录
│   ├── unit/                 # 单元测试
│   ├── integration/          # 集成测试
│   └── data/                 # 测试数据
├── scripts/                   # 脚本工具
├── docs/                      # 项目文档
├── .env                       # 环境变量（不提交）
├── .env.example               # 环境变量模板
├── pyproject.toml             # 项目配置
├── uv.lock                    # 依赖锁定
├── Dockerfile                 # 容器化配置
└── docker-compose.yml         # 编排配置
```

### 15. 依赖管理
| 技术 | 说明 |
|------|------|
| uv | 包管理、虚拟环境、锁文件 |
| pyproject.toml | 项目元数据与依赖声明 |

---

## 三、LangChain 核心组件使用规划

| 组件 | 具体类/方法 | 用途 |
|------|-------------|------|
| Models | `ChatDashScope`, `DashScopeEmbeddings` | LLM 与嵌入统一接口 |
| Prompts | `ChatPromptTemplate`, `MessagesPlaceholder` | 人格化提示、历史注入 |
| Indexes | `Chroma`, `TextLoader`, `RecursiveCharacterTextSplitter` | 文档加载、分块、向量化 |
| Retrievers | `VectorStoreRetriever`, `EnsembleRetriever`, `ContextualCompressionRetriever` | 多路召回与精排 |
| Chains | `create_retrieval_chain`, `create_history_aware_retriever`, `create_stuff_documents_chain` | 构建 RAG 完整链路（LCEL） |
| Memory | `ConversationBufferMemory`, `RedisChatMessageHistory` | 多轮对话持久化 |
| Agents (未来) | `create_react_agent`, `Tool` | 扩展为智能体，调用外部工具 |

---

## 四、数据流转示意图
用户输入（Vue 前端）
↓
FastAPI /chat 接口（携带 session_id）
↓
LangChain 链：
├─ 从 Redis 加载对话历史
├─ 历史感知检索器（改写 query）
├─ 混合检索（向量+BM25）→ 重排序
├─ 与历史、检索结果合并 prompt
├─ 调用 ChatDashScope 生成
└─ 将新消息存入 Redis
↓
流式返回（SSE）到前端
↓
Vue 渲染 Markdown 答案

---

## 五、环境变量示例（.env）

```env
# DashScope（必需）
DASHSCOPE_API_KEY=sk-xxx

# Redis（必需）
REDIS_URL=redis://localhost:6379/0

# MySQL（可选，生产环境使用）
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=sushi
MYSQL_PORT=3306

# ChromaDB 持久化路径
CHROMA_PERSIST_DIR=./data/chroma_db

# 模型与检索配置
EMBEDDING_MODEL=text_embedding_v2
LLM_MODEL=qwen-max
TOP_K=5
VECTOR_WEIGHT=0.7
BM25_WEIGHT=0.3

# 安全配置
SECRET_KEY=your-super-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS 配置
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173

# API 限流配置
RATE_LIMIT_PER_MINUTE=60

# 日志级别
LOG_LEVEL=INFO
```

---

## 六、开发路线图

### 阶段 0：工程化重构（当前）
- [x] 项目结构规划
- [x] 依赖配置整理
- [ ] 基础工具函数实现
- [ ] 核心配置管理
- [ ] 错误处理框架

### 阶段 1：LangChain 基础
- [ ] LLM 与嵌入配置（DashScope）
- [ ] 向量库构建与检索链
- [ ] Redis 记忆模块

### 阶段 2：混合检索
- [ ] BM25 关键词检索
- [ ] 向量检索集成
- [ ] 多路召回融合
- [ ] 检索效果评估

### 阶段 3：重排序与优化
- [ ] BGE-reranker 集成
- [ ] Cross-Encoder 配置
- [ ] 检索结果优化

### 阶段 4：API 开发
- [ ] FastAPI 接口封装
- [ ] 流式输出（SSE）
- [ ] 健康检查与监控
- [ ] API 限流与安全

### 阶段 5：前端开发
- [ ] Vue 项目初始化
- [ ] 对话界面实现
- [ ] Markdown 渲染
- [ ] 历史记录管理

### 阶段 6：部署与运维
- [ ] Docker 容器化
- [ ] Docker Compose 编排
- [ ] 监控告警配置
- [ ] CI/CD 流程

### 阶段 7（可选）：Agent 扩展
- [ ] 工具调用能力
- [ ] 多 Agent 协作
- [ ] 主动学习优化
