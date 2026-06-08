# 企业级智能文档问答平台 - 部署指南

## 📋 目录

1. [环境要求](#环境要求)
2. [快速开始](#快速开始)
3. [部署模式](#部署模式)
4. [配置说明](#配置说明)
5. [扩展与监控](#扩展与监控)
6. [故障排查](#故障排查)

---

## 🛠️ 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 至少 4GB 内存（推荐 8GB+）
- 至少 2 核 CPU

---

## 🚀 快速开始

### 方式一：使用部署脚本（推荐）

```bash
# 启动生产环境
./deploy.sh --prod

# 启动开发环境
./deploy.sh --dev

# 查看帮助
./deploy.sh --help
```

### 方式二：手动启动

```bash
# 构建镜像
docker build -t sushi-api:latest .
docker build -t sushi-frontend:latest ./frontend

# 启动生产环境
docker-compose -f docker-compose.prod.yml up -d

# 查看服务状态
docker-compose -f docker-compose.prod.yml ps
```

---

## 🔧 部署模式

### 1. 开发环境（开发测试）

```bash
docker-compose up -d
```

**特点：**
- 单实例运行
- 支持热重载
- 适合开发调试

### 2. 简化版（轻量级部署）

```bash
docker-compose -f docker-compose.simple.yml up -d
```

**特点：**
- 3 个 API 实例
- Redis 缓存
- Nginx 负载均衡

### 3. 生产环境（完整部署）

```bash
docker-compose -f docker-compose.prod.yml up -d
```

**特点：**
- 3 个 API 实例（可扩展）
- Redis 缓存（2GB 内存限制）
- Nginx 负载均衡
- 前端静态资源服务
- 健康检查
- 日志持久化

---

## ⚙️ 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `ENV` | 运行环境 | `production` |
| `REDIS_URL` | Redis 连接地址 | `redis://redis:6379/0` |
| `USE_REDIS_STORAGE` | 是否使用 Redis 存储任务 | `true` |
| `UVICORN_WORKERS` | Uvicorn worker 数量 | `4` |
| `LOG_LEVEL` | 日志级别 | `info` |

### 端口映射

| 端口 | 服务 | 说明 |
|------|------|------|
| 80 | Nginx | 对外服务端口 |
| 6379 | Redis | 缓存服务端口 |
| 8000 | API | 内部 API 端口 |

### 数据卷

```
redis-data:    # Redis 持久化数据
frontend-dist: # 前端静态文件
nginx-logs:    # Nginx 日志
```

---

## 📈 扩展与监控

### 水平扩展

```bash
# 扩展到 5 个 API 实例
docker-compose -f docker-compose.prod.yml up -d --scale api=5

# 查看当前实例数
docker-compose -f docker-compose.prod.yml ps | grep api | wc -l
```

### 查看日志

```bash
# 查看所有服务日志
docker-compose -f docker-compose.prod.yml logs -f

# 查看特定服务日志
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs -f nginx
```

### 健康检查

```bash
# 检查 API 健康状态
curl http://localhost/api/health

# 检查 Redis 连接
docker exec -it sushi-redis redis-cli ping
```

---

## 🐛 故障排查

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| API 无法启动 | Redis 未就绪 | 等待 Redis 健康检查通过 |
| 前端无法访问 | Nginx 配置错误 | 检查 `config/nginx/nginx.conf` |
| 内存不足 | 容器内存限制 | 调整 `deploy.resources.limits` |
| 构建失败 | 网络问题 | 使用国内镜像源 |

### 日志位置

```
# Nginx 日志
./config/nginx/logs/

# 应用日志
./logs/

# Docker 容器日志
docker-compose -f docker-compose.prod.yml logs
```

### 重启服务

```bash
# 重启所有服务
docker-compose -f docker-compose.prod.yml restart

# 重启特定服务
docker-compose -f docker-compose.prod.yml restart api
```

---

## 📝 启动验证

启动完成后，访问以下地址验证：

| 地址 | 说明 |
|------|------|
| `http://localhost` | 前端应用 |
| `http://localhost/api/health` | API 健康检查 |
| `http://localhost/api/docs/count` | 文档数量 |

---

## 📁 项目结构

```
.
├── backend/           # 后端 API 服务
├── frontend/          # 前端应用
├── config/
│   └── nginx/        # Nginx 配置
├── docker-compose.yml        # 开发环境
├── docker-compose.simple.yml # 简化版
├── docker-compose.prod.yml   # 生产环境
├── Dockerfile                # 后端镜像
├── frontend/Dockerfile       # 前端镜像
├── deploy.sh                 # 部署脚本
└── DEPLOYMENT.md            # 部署文档
```
