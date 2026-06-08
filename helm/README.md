# 企业级智能文档问答平台 Helm Chart

这是企业级智能文档问答平台的 Kubernetes Helm Chart，用于将应用部署到 Kubernetes 集群。

## 🚀 快速开始

### 1. 添加 Helm Repository

```bash
helm repo add sushi-digital-human https://huang-song-liang.github.io/sushi_digital_human/
helm repo update
```

### 2. 安装 Chart

```bash
helm install sushi-digital-human sushi-digital-human/sushi-digital-human \
  --namespace sushi \
  --create-namespace \
  --set backend.env.DASHSCOPE_API_KEY=your-api-key
```

### 3. 使用自定义值文件

创建 `values.yaml` 文件：

```yaml
backend:
  env:
    DASHSCOPE_API_KEY: "your-api-key"

  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10

redis:
  enabled: true
  auth:
    password: "your-redis-password"

ingress:
  enabled: true
  hosts:
    - host: sushi.example.com
```

然后安装：

```bash
helm install sushi-digital-human sushi-digital-human/sushi-digital-human \
  --namespace sushi \
  --create-namespace \
  -f values.yaml
```

## 📋 配置选项

### 后端配置

| 参数 | 描述 | 默认值 |
|------|------|--------|
| `backend.replicaCount` | Pod 副本数 | `2` |
| `backend.image.repository` | 镜像仓库 | `ghcr.io/huang-song-liang/sushi-digital-human` |
| `backend.image.tag` | 镜像标签 | `latest` |
| `backend.resources.requests.cpu` | CPU 请求 | `100m` |
| `backend.resources.requests.memory` | 内存请求 | `512Mi` |
| `backend.resources.limits.cpu` | CPU 限制 | `2` |
| `backend.resources.limits.memory` | 内存限制 | `4Gi` |
| `backend.env.DASHSCOPE_API_KEY` | DashScope API Key | `""` |
| `backend.env.LLM_MODEL` | LLM 模型名称 | `qwen-max` |
| `backend.env.EMBEDDING_MODEL` | 嵌入模型名称 | `text_embedding_v2` |

### Redis 配置

| 参数 | 描述 | 默认值 |
|------|------|--------|
| `redis.enabled` | 是否启用内置 Redis | `true` |
| `redis.auth.enabled` | 是否启用认证 | `true` |
| `redis.persistence.enabled` | 是否启用持久化 | `true` |
| `redis.persistence.size` | 持久化存储大小 | `10Gi` |

### MySQL 配置

| 参数 | 描述 | 默认值 |
|------|------|--------|
| `mysql.enabled` | 是否启用内置 MySQL | `false` |
| `mysql.auth.rootPassword` | Root 密码 | `""` |
| `mysql.auth.database` | 数据库名称 | `sushi` |
| `mysql.persistence.size` | 持久化存储大小 | `20Gi` |

### Ingress 配置

| 参数 | 描述 | 默认值 |
|------|------|--------|
| `ingress.enabled` | 是否启用 Ingress | `false` |
| `ingress.hosts[0].host` | 主机名 | `sushi.example.com` |

### 自动扩缩容配置

| 参数 | 描述 | 默认值 |
|------|------|--------|
| `backend.autoscaling.enabled` | 是否启用自动扩缩容 | `false` |
| `backend.autoscaling.minReplicas` | 最小副本数 | `2` |
| `backend.autoscaling.maxReplicas` | 最大副本数 | `10` |
| `backend.autoscaling.targetCPUUtilizationPercentage` | CPU 目标使用率 | `80` |

## 📡 暴露服务

### 使用 NodePort

```bash
helm upgrade sushi-digital-human sushi-digital-human/sushi-digital-human \
  --set backend.service.type=NodePort \
  --set backend.service.nodePort=30080
```

### 使用 LoadBalancer

```bash
helm upgrade sushi-digital-human sushi-digital-human/sushi-digital-human \
  --set backend.service.type=LoadBalancer
```

### 使用 Ingress

```bash
helm upgrade sushi-digital-human sushi-digital-human/sushi-digital-human \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=sushi.example.com
```

## 📊 监控配置

### 启用 Prometheus ServiceMonitor

```bash
helm upgrade sushi-digital-human sushi-digital-human/sushi-digital-human \
  --set monitoring.serviceMonitor.enabled=true
```

## 🗑️ 卸载

```bash
helm uninstall sushi-digital-human --namespace sushi
```

## 📁 Chart 结构

```
helm/
├── Chart.yaml          # Chart 元数据
├── values.yaml         # 默认配置值
├── README.md           # 使用说明
└── templates/
    ├── _helpers.tpl    # 模板函数
    ├── deployment.yaml # Deployment 配置
    ├── service.yaml     # Service 配置
    ├── ingress.yaml     # Ingress 配置
    ├── hpa.yaml         # 自动扩缩容配置
    └── servicemonitor.yaml # Prometheus 监控配置
```

## 📝 版本历史

| 版本 | 说明 |
|------|------|
| 0.1.0 | 初始版本 |

## 📄 许可证

MIT License
