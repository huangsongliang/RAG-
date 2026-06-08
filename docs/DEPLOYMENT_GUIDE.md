# 企业级智能文档问答平台 - 万人并发部署指南

**文档版本**: 1.0
**创建日期**: 2026-05-16
**适用场景**: 万人并发生产环境部署

---

## 一、系统要求

### 1.1 硬件要求

| 组件 | 最低配置 | 推荐配置 | 数量 |
|-----|---------|---------|------|
| API 服务器 | 4C8G | 8C16G | 4-10 台 |
| Redis 服务器 | 2C4G | 4C8G | 1-3 台 |
| Nginx 服务器 | 2C4G | 4C8G | 1-2 台 |
| 监控服务器 | 2C4G | 4C8G | 1 台 |

### 1.2 软件要求

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+
- Redis 7.0+
- Nginx 1.20+

---

## 二、快速部署

### 2.1 单机快速启动（开发/测试）

```bash
# 1. 克隆项目
git clone <repository-url>
cd sushi_digital_human

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入必要的 API Key

# 3. 启动所有服务
docker-compose up -d

# 4. 查看服务状态
docker-compose ps

# 5. 检查服务健康
curl http://localhost/health
```

### 2.2 生产环境部署（多机器）

```bash
# 1. 在每台服务器上安装 Docker
curl -fsSL https://get.docker.com | sh

# 2. 配置 Docker Swarm
docker swarm init
docker node join <manager-token>

# 3. 部署 stack
docker stack deploy -c docker-compose.yml sushi
```

---

## 三、架构说明

### 3.1 组件架构

```
                    ┌─────────────────┐
                    │   Nginx (80)   │
                    │   负载均衡      │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │ API #1   │       │ API #2   │       │ API #N   │
    │ (8001)   │       │ (8002)   │       │ (800N)   │
    └────┬─────┘       └────┬─────┘       └────┬─────┘
         │                  │                  │
         └──────────────────┼──────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
   ┌──────────┐       ┌──────────┐       ┌──────────┐
   │  Redis   │       │  Celery  │       │ Prometheus│
   │  缓存    │       │  异步队列 │       │   监控   │
   └──────────┘       └──────────┘       └──────────┘
```

### 3.2 端口映射

| 服务 | 端口 | 说明 |
|-----|------|------|
| Nginx | 80, 443 | 入口，所有流量经过 |
| API-1 | 8001 | API 实例 1 |
| API-2 | 8002 | API 实例 2 |
| API-3 | 8003 | API 实例 3 |
| API-4 | 8004 | API 实例 4 |
| Redis | 6379 | 缓存和消息队列 |
| Prometheus | 9090 | 监控数据 |
| Grafana | 3000 | 可视化面板 |

---

## 四、配置说明

### 4.1 环境变量

创建 `.env` 文件：

```env
# API 配置
ENV=production
LOG_LEVEL=info

# DashScope API (阿里云)
DASHSCOPE_API_KEY=your-api-key-here

# Redis 配置
REDIS_HOST=redis
REDIS_PORT=6379

# LLM 配置
LLM_MODEL=qwen-max
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000

# 嵌入模型配置
EMBEDDING_MODEL=text-embedding-v2
```

### 4.2 Nginx 配置

主配置：`config/nginx/nginx.conf`
负载均衡：`config/nginx/conf.d/upstream.conf`

### 4.3 Redis 配置

配置文件：`config/redis.conf`

---

## 五、运维命令

### 5.1 服务管理

```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启特定服务
docker-compose restart api-1

# 查看服务日志
docker-compose logs -f api-1
docker-compose logs -f nginx

# 扩展 API 实例
docker-compose up -d --scale api-1=8
```

### 5.2 健康检查

```bash
# 检查所有服务健康状态
curl http://localhost/health

# 检查 Nginx 后端
docker-compose exec nginx nginx -t

# 检查 Redis
docker-compose exec redis redis-cli ping

# 查看 Celery 队列
docker-compose exec celery-worker-1 celery inspect active
```

### 5.3 监控访问

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin123)
- **API Metrics**: http://localhost:8001/metrics

---

## 六、性能测试

### 6.1 运行压力测试

```bash
# 安装依赖
pip install -r requirements.txt

# 运行万人并发测试
python tests/stress_test_10k.py

# 运行自定义并发测试
python tests/stress_test_10k.py 5000  # 5000 并发
```

### 6.2 Locust Web 界面测试

```bash
# 启动 Locust
locust -f tests/locustfile.py --host=http://localhost

# 访问 Web 界面
# http://localhost:8089
```

---

## 七、故障排查

### 7.1 常见问题

#### 问题 1: API 返回 502 Bad Gateway

**原因**: 后端 API 服务未启动或健康检查失败

**解决**:
```bash
# 检查 API 日志
docker-compose logs api-1

# 重启 API 服务
docker-compose restart api-1
```

#### 问题 2: Redis 连接失败

**原因**: Redis 服务未启动或网络问题

**解决**:
```bash
# 检查 Redis 状态
docker-compose ps redis

# 重启 Redis
docker-compose restart redis
```

#### 问题 3: 内存溢出 (OOM)

**原因**: Docker 容器内存限制过低

**解决**: 在 docker-compose.yml 中调整内存限制

#### 问题 4: 限流触发 (429 Too Many Requests)

**原因**: 请求频率超过限制

**解决**: 调整 Nginx 限流配置或增加 API 实例

### 7.2 日志查看

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f api-1 nginx redis

# 保存日志到文件
docker-compose logs > debug.log 2>&1
```

---

## 八、扩展指南

### 8.1 水平扩展

```bash
# 增加 API 实例数量
docker-compose up -d --scale api-1=10 --scale api-2=10

# 增加 Celery Worker
docker-compose up -d --scale celery-worker-1=5
```

### 8.2 垂直扩展

编辑 `docker-compose.yml` 中的资源限制：

```yaml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 4G
```

### 8.3 添加新的 API 实例

1. 在 `docker-compose.yml` 中添加新服务
2. 更新 Nginx `upstream.conf`
3. 重启 Nginx

---

## 九、安全配置

### 9.1 SSL 证书

```bash
# 创建 SSL 证书目录
mkdir -p config/nginx/ssl

# 复制证书
cp your-cert.crt config/nginx/ssl/cert.crt
cp your-key.key config/nginx/ssl/key.key
```

### 9.2 防火墙配置

```bash
# 只开放必要端口
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw allow 22/tcp   # SSH
```

---

## 十、性能优化建议

### 10.1 系统级优化

```bash
# 调整文件描述符限制
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf

# 调整内核参数
echo "net.core.somaxconn = 65535" >> /etc/sysctl.conf
echo "net.ipv4.tcp_tw_reuse = 1" >> /etc/sysctl.conf
sysctl -p
```

### 10.2 Docker 优化

```bash
# 编辑 Docker daemon 配置
sudo nano /etc/docker/daemon.json

{
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 65535,
      "Soft": 65535
    }
  },
  "max-concurrent-downloads": 10,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

---

## 十一、联系与支持

- **文档版本**: 1.0
- **最后更新**: 2026-05-16
- **技术支持**: <your-email@example.com>

---

**下一步行动**:
1. 部署系统到测试环境
2. 运行压力测试验证性能
3. 根据测试结果调整配置
4. 部署到生产环境
