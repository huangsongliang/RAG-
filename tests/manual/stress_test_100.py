"""
100并发用户压力测试脚本
目标：模拟100并发用户，监控响应时间、错误率、系统资源使用率
"""

import asyncio
import time
import statistics
import random
import psutil
import os
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import httpx
from collections import defaultdict
import json

# ==================== 配置 ====================
TARGET_CONCURRENT_USERS = 100  # 目标并发用户数
TEST_DURATION = 120  # 测试持续时间（秒）
WARMUP_DURATION = 10  # 预热时间（秒）
BASE_URL = "http://localhost:8000"

# 性能目标
TARGET_P95_RESPONSE_TIME = 5.0  # 秒
TARGET_ERROR_RATE = 0.05  # 5%
TARGET_THROUGHPUT = 50  # 请求/秒

# 测试查询
TEST_QUERIES = [
    "企业级文档问答平台如何部署？",
    "系统支持哪些数据库类型？",
    "混合检索是如何工作的？",
    "如何配置文档分块策略？",
    "RAG架构的核心组件有哪些？",
    "通义千问模型如何接入？",
    "系统支持哪些认证方式？",
    "如何进行性能优化配置？",
    "知识库文档如何上传和管理？",
    "流式输出功能是如何实现的？",
]


# ==================== 数据模型 ====================
@dataclass
class ResourceMetrics:
    """系统资源指标"""

    timestamp: float
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    network_sent_mb: float
    network_recv_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float


@dataclass
class RequestMetrics:
    """请求指标"""

    success_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    status_codes: Dict[int, int] = field(default_factory=dict)
    response_times: List[float] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)

    @property
    def total_requests(self) -> int:
        return self.success_count + self.error_count + self.timeout_count

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.error_count + self.timeout_count) / self.total_requests

    def get_percentile(self, p: float) -> float:
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * p)
        return sorted_times[min(index, len(sorted_times) - 1)]


@dataclass
class TestResult:
    """测试结果"""

    concurrent_users: int
    duration: float
    total_requests: int
    success_count: int
    error_count: int
    timeout_count: int
    error_rate: float
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p50_response_time: float
    p95_response_time: float
    p99_response_time: float
    throughput: float
    resource_metrics: List[ResourceMetrics]
    status_codes: Dict[int, int]
    timestamp: str


# ==================== 资源监控器 ====================
class ResourceMonitor:
    """系统资源监控器"""

    def __init__(self):
        self.metrics: List[ResourceMetrics] = []
        self._monitoring = False
        self._start_network = None
        self._start_disk_io = None

    def start(self):
        """开始监控"""
        self._monitoring = True
        self.metrics = []

        # 获取初始网络和磁盘IO
        net_io = psutil.net_io_counters()
        disk_io = psutil.disk_io_counters()
        self._start_network = (net_io.bytes_sent, net_io.bytes_recv)
        self._start_disk_io = (disk_io.read_bytes, disk_io.write_bytes)

    def sample(self) -> ResourceMetrics:
        """采样当前资源使用"""
        timestamp = time.time()

        # CPU 使用率
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # 内存使用
        memory = psutil.virtual_memory()
        memory_mb = memory.used / (1024 * 1024)
        memory_percent = memory.percent

        # 网络 IO
        net_io = psutil.net_io_counters()
        network_sent_mb = (net_io.bytes_sent - self._start_network[0]) / (1024 * 1024)
        network_recv_mb = (net_io.bytes_recv - self._start_network[1]) / (1024 * 1024)

        # 磁盘 IO
        disk_io = psutil.disk_io_counters()
        disk_io_read_mb = (disk_io.read_bytes - self._start_disk_io[0]) / (1024 * 1024)
        disk_io_write_mb = (disk_io.write_bytes - self._start_disk_io[1]) / (
            1024 * 1024
        )

        metric = ResourceMetrics(
            timestamp=timestamp,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            memory_percent=memory_percent,
            network_sent_mb=network_sent_mb,
            network_recv_mb=network_recv_mb,
            disk_io_read_mb=disk_io_read_mb,
            disk_io_write_mb=disk_io_write_mb,
        )

        if self._monitoring:
            self.metrics.append(metric)

        return metric

    def stop(self):
        """停止监控"""
        self._monitoring = False

    def get_summary(self) -> Dict[str, Any]:
        """获取资源统计摘要"""
        if not self.metrics:
            return {}

        cpu_values = [m.cpu_percent for m in self.metrics]
        memory_values = [m.memory_percent for m in self.metrics]

        return {
            "avg_cpu": statistics.mean(cpu_values),
            "max_cpu": max(cpu_values),
            "avg_memory": statistics.mean(memory_values),
            "max_memory": max(memory_values),
            "avg_network_sent_mb": statistics.mean(
                [m.network_sent_mb for m in self.metrics]
            ),
            "avg_network_recv_mb": statistics.mean(
                [m.network_recv_mb for m in self.metrics]
            ),
            "total_network_sent_mb": (
                self.metrics[-1].network_sent_mb if self.metrics else 0
            ),
            "total_network_recv_mb": (
                self.metrics[-1].network_recv_mb if self.metrics else 0
            ),
        }


# ==================== 测试客户端 ====================
class LoadTestClient:
    """负载测试客户端"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.session_id = f"user_{user_id}_{int(time.time())}"
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.response_times: List[float] = []
        self.status_codes: Dict[int, int] = defaultdict(int)
        self.errors: List[str] = []
        self._client = None

    async def initialize(self):
        """初始化客户端"""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
        )

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()

    async def send_request(self) -> Dict[str, Any]:
        """发送单个请求"""
        start_time = time.time()
        query = random.choice(TEST_QUERIES)

        try:
            response = await self._client.post(
                f"{BASE_URL}/api/chat",
                json={
                    "message": query,
                    "session_id": self.session_id,
                    "use_rag": True,
                    "top_k": 3,
                },
                headers={"X-User-ID": str(self.user_id)},
            )

            response_time = time.time() - start_time
            self.response_times.append(response_time)
            self.status_codes[response.status_code] += 1

            if response.status_code == 200:
                self.success_count += 1
                return {"success": True, "response_time": response_time, "status": 200}
            else:
                self.error_count += 1
                self.errors.append(f"HTTP {response.status_code}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "status": response.status_code,
                }

        except httpx.TimeoutException:
            self.error_count += 1
            self.errors.append("Timeout")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            self.error_count += 1
            self.errors.append(str(e))
            return {"success": False, "error": str(e)}
        finally:
            self.request_count += 1


# ==================== 主测试类 ====================
class StressTester:
    """压力测试器"""

    def __init__(self):
        self.clients: List[LoadTestClient] = []
        self.global_metrics = RequestMetrics()
        self.resource_monitor = ResourceMonitor()
        self.test_start_time = 0
        self.running = False
        self.progress = 0

    async def setup_clients(self, count: int):
        """初始化客户端池"""
        print(f"初始化 {count} 个测试客户端...")
        self.clients = [LoadTestClient(i) for i in range(count)]

        tasks = [client.initialize() for client in self.clients]
        await asyncio.gather(*tasks)
        print(f"客户端初始化完成")

    async def cleanup_clients(self):
        """清理客户端"""
        print("清理客户端...")
        tasks = [client.close() for client in self.clients]
        await asyncio.gather(*tasks)

    async def run_user_session(self, client: LoadTestClient, duration: int):
        """运行单个用户会话"""
        end_time = time.time() + duration

        while self.running and time.time() < end_time:
            await client.send_request()
            # 随机等待 0.5-2 秒
            await asyncio.sleep(random.uniform(0.5, 2.0))

    async def monitor_resources(self, interval: float = 1.0):
        """监控资源使用"""
        while self.running:
            self.resource_monitor.sample()
            await asyncio.sleep(interval)

    async def run_concurrent_load_test(
        self, concurrent_users: int, duration: int, warmup_duration: int = 10
    ) -> TestResult:
        """运行并发负载测试"""
        print(f"\n{'='*80}")
        print(f"开始100并发压力测试")
        print(f"{'='*80}\n")
        print(f"测试配置:")
        print(f"  - 并发用户: {concurrent_users}")
        print(f"  - 预热时间: {warmup_duration}秒")
        print(f"  - 测试持续: {duration}秒")
        print(f"  - 目标P95响应: <{TARGET_P95_RESPONSE_TIME}秒")
        print(f"  - 目标错误率: <{TARGET_ERROR_RATE*100}%\n")

        # 初始化客户端
        await self.setup_clients(concurrent_users)

        # 开始监控
        self.resource_monitor.start()

        self.running = True
        self.test_start_time = time.time()

        # 预热阶段
        print(f"[阶段1] 预热中 ({warmup_duration}秒)...")

        # 资源监控
        monitor_task = asyncio.create_task(self.monitor_resources(1.0))

        # 预热任务
        warmup_tasks = [
            self.run_user_session(client, warmup_duration) for client in self.clients
        ]
        await asyncio.gather(*warmup_tasks)

        # 正式测试阶段
        print(f"[阶段2] 正式测试中 ({duration}秒)...")
        phase_start = time.time()

        while self.running and (time.time() - phase_start) < duration:
            # 显示进度
            elapsed = time.time() - phase_start
            progress = min(100, (elapsed / duration) * 100)
            print(
                f"\r        进度: {progress:5.1f}% ({int(elapsed)}/{duration}秒)",
                end="",
                flush=True,
            )

            # 运行测试
            test_tasks = [self.run_user_session(client, 5) for client in self.clients]
            await asyncio.gather(*test_tasks)

            # 短暂休息
            await asyncio.sleep(1)

        print(f"\n[阶段3] 收集结果...")

        # 停止监控
        self.running = False
        await monitor_task
        self.resource_monitor.stop()

        # 收集所有客户端的指标
        for client in self.clients:
            self.global_metrics.success_count += client.success_count
            self.global_metrics.error_count += client.error_count
            self.global_metrics.response_times.extend(client.response_times)
            self.global_metrics.timeout_count += client.errors.count("Timeout")

            for status_code, count in client.status_codes.items():
                self.global_metrics.status_codes[status_code] = (
                    self.global_metrics.status_codes.get(status_code, 0) + count
                )

            self.global_metrics.error_messages.extend(
                client.errors[:10]
            )  # 只保留前10个错误

        # 计算最终结果
        test_duration = time.time() - self.test_start_time
        total_requests = self.global_metrics.total_requests
        resource_summary = self.resource_monitor.get_summary()

        result = TestResult(
            concurrent_users=concurrent_users,
            duration=test_duration,
            total_requests=total_requests,
            success_count=self.global_metrics.success_count,
            error_count=self.global_metrics.error_count,
            timeout_count=self.global_metrics.timeout_count,
            error_rate=self.global_metrics.error_rate,
            avg_response_time=(
                statistics.mean(self.global_metrics.response_times)
                if self.global_metrics.response_times
                else 0
            ),
            min_response_time=(
                min(self.global_metrics.response_times)
                if self.global_metrics.response_times
                else 0
            ),
            max_response_time=(
                max(self.global_metrics.response_times)
                if self.global_metrics.response_times
                else 0
            ),
            p50_response_time=self.global_metrics.get_percentile(0.50),
            p95_response_time=self.global_metrics.get_percentile(0.95),
            p99_response_time=self.global_metrics.get_percentile(0.99),
            throughput=total_requests / test_duration if test_duration > 0 else 0,
            resource_metrics=self.resource_monitor.metrics,
            status_codes=self.global_metrics.status_codes,
            timestamp=datetime.now().isoformat(),
        )

        await self.cleanup_clients()

        return result

    def generate_report(self, result: TestResult) -> str:
        """生成详细测试报告"""
        resource_summary = self.resource_monitor.get_summary()

        # 性能评估
        p95_pass = result.p95_response_time <= TARGET_P95_RESPONSE_TIME
        error_rate_pass = result.error_rate <= TARGET_ERROR_RATE

        report = f"""
{'='*80}
              企业级智能文档问答平台 - 100并发压力测试报告
{'='*80}

测试时间: {result.timestamp}
测试配置:
  - 并发用户数: {result.concurrent_users}
  - 测试持续时间: {result.duration:.2f} 秒
  - 预热时间: {WARMUP_DURATION} 秒

一、性能指标
{'='*80}

1. 请求统计
   - 总请求数: {result.total_requests:,}
   - 成功请求: {result.success_count:,} ({(result.success_count/result.total_requests*100) if result.total_requests > 0 else 0:.2f}%)
   - 失败请求: {result.error_count:,} ({result.error_rate*100:.2f}%)
   - 超时请求: {result.timeout_count:,}

2. HTTP 状态码分布
"""

        for status_code, count in sorted(result.status_codes.items()):
            percentage = (
                (count / result.total_requests * 100)
                if result.total_requests > 0
                else 0
            )
            report += f"   - {status_code}: {count:,} ({percentage:.2f}%)\n"

        report += f"""
3. 响应时间
   - 平均响应时间: {result.avg_response_time:.3f}s
   - 最小响应时间: {result.min_response_time:.3f}s
   - 最大响应时间: {result.max_response_time:.3f}s
   - P50 (中位数): {result.p50_response_time:.3f}s
   - P95 (重要指标): {result.p95_response_time:.3f}s {'✓' if p95_pass else '✗'}
   - P99: {result.p99_response_time:.3f}s

4. 吞吐量
   - 总吞吐量: {result.throughput:.2f} req/s
   - 目标吞吐量: >{TARGET_THROUGHPUT} req/s {'✓' if result.throughput >= TARGET_THROUGHPUT else '✗'}

二、系统资源使用
{'='*80}

1. CPU 使用率
   - 平均: {resource_summary.get('avg_cpu', 0):.1f}%
   - 峰值: {resource_summary.get('max_cpu', 0):.1f}%
"""

        # 警告信息
        if resource_summary.get("max_cpu", 0) > 80:
            report += f"   ⚠️ CPU 使用率较高，峰值达到 {resource_summary.get('max_cpu', 0):.1f}%\n"

        report += f"""
2. 内存使用
   - 平均: {resource_summary.get('avg_memory', 0):.1f}%
   - 峰值: {resource_summary.get('max_memory', 0):.1f}%
"""

        if resource_summary.get("max_memory", 0) > 80:
            report += f"   ⚠️ 内存使用率较高，峰值达到 {resource_summary.get('max_memory', 0):.1f}%\n"

        report += f"""
3. 网络 IO
   - 总发送: {resource_summary.get('total_network_sent_mb', 0):.2f} MB
   - 总接收: {resource_summary.get('total_network_recv_mb', 0):.2f} MB
   - 平均发送: {resource_summary.get('avg_network_sent_mb', 0):.2f} MB/s
   - 平均接收: {resource_summary.get('avg_network_recv_mb', 0):.2f} MB/s

三、性能评估
{'='*80}

| 指标 | 目标值 | 实际值 | 状态 |
|-----|-------|-------|------|
| P95 响应时间 | <{TARGET_P95_RESPONSE_TIME}s | {result.p95_response_time:.3f}s | {'✓ 通过' if p95_pass else '✗ 未通过'} |
| 错误率 | <{TARGET_ERROR_RATE*100}% | {result.error_rate*100:.2f}% | {'✓ 通过' if error_rate_pass else '✗ 未通过'} |
| 吞吐量 | >{TARGET_THROUGHPUT} req/s | {result.throughput:.2f} req/s | {'✓ 通过' if result.throughput >= TARGET_THROUGHPUT else '✗ 未通过'} |

四、性能瓶颈分析
{'='*80}

"""

        # 瓶颈分析
        bottlenecks = []

        if result.p95_response_time > TARGET_P95_RESPONSE_TIME:
            bottlenecks.append(
                {
                    "问题": "P95响应时间过长",
                    "影响": "用户体验下降，页面加载缓慢",
                    "根因": "可能是LLM API调用延迟高、系统处理能力不足、或者缓存未命中",
                    "建议": "1. 检查LLM API响应时间 2. 增加缓存命中率 3. 优化查询处理流程",
                }
            )

        if result.error_rate > TARGET_ERROR_RATE:
            bottlenecks.append(
                {
                    "问题": "错误率过高",
                    "影响": "系统不稳定，用户请求失败",
                    "根因": "可能是限流触发、超时设置过短、或者服务过载",
                    "建议": "1. 调整限流阈值 2. 增加超时时间 3. 扩展系统容量",
                }
            )

        if resource_summary.get("max_cpu", 0) > 80:
            bottlenecks.append(
                {
                    "问题": "CPU使用率过高",
                    "影响": "系统处理能力受限，可能导致响应延迟",
                    "根因": "并发请求过多、缺少异步处理、或者同步阻塞操作",
                    "建议": "1. 增加工作线程数 2. 使用异步处理 3. 考虑水平扩展",
                }
            )

        if resource_summary.get("max_memory", 0) > 80:
            bottlenecks.append(
                {
                    "问题": "内存使用率过高",
                    "影响": "可能导致OOM，系统不稳定",
                    "根因": "内存泄漏、缓存过大、或者连接未释放",
                    "建议": "1. 检查内存泄漏 2. 限制缓存大小 3. 优化连接管理",
                }
            )

        if bottlenecks:
            for i, b in enumerate(bottlenecks, 1):
                report += f"""
【瓶颈{i}】{b['问题']}
   影响: {b['影响']}
   根因: {b['根因']}
   建议: {b['建议']}
"""
        else:
            report += "未发现明显性能瓶颈。\n"

        report += f"""
五、优化建议
{'='*80}

"""

        # 生成优化建议
        suggestions = []

        if result.p95_response_time > TARGET_P95_RESPONSE_TIME:
            suggestions.append("""
【高优先级】优化响应时间
1. 增加嵌入结果缓存，减少重复计算
2. 实施异步处理架构，非关键路径异步化
3. 考虑使用更快的嵌入模型或本地模型
4. 优化Redis连接池配置""")

        if result.error_rate > TARGET_ERROR_RATE * 2:
            suggestions.append("""
【高优先级】降低错误率
1. 增加限流阈值或实施动态限流
2. 增加请求超时时间
3. 添加请求重试机制
4. 实施服务降级策略""")

        if resource_summary.get("max_cpu", 0) > 70:
            suggestions.append("""
【中优先级】优化CPU使用
1. 增加Uvicorn工作进程数
2. 使用异步数据库/缓存操作
3. 优化代码中的同步阻塞操作
4. 考虑使用进程池而非线程池""")

        if resource_summary.get("max_memory", 0) > 70:
            suggestions.append("""
【中优先级】优化内存使用
1. 限制Redis缓存大小
2. 实施连接池复用
3. 添加内存监控和告警
4. 定期清理过期数据""")

        if suggestions:
            for i, s in enumerate(suggestions, 1):
                report += f"{s}\n"
        else:
            report += "系统性能表现良好，无需特殊优化。\n"

        # 总结
        overall_pass = p95_pass and error_rate_pass
        report += f"""
六、测试结论
{'='*80}

总体评估: {'🎉 测试通过 - 系统表现良好' if overall_pass else '⚠️ 测试未通过 - 需要优化'}

详细结论:
"""

        if p95_pass:
            report += f"  ✓ P95响应时间 {result.p95_response_time:.3f}s 符合目标 (<{TARGET_P95_RESPONSE_TIME}s)\n"
        else:
            report += f"  ✗ P95响应时间 {result.p95_response_time:.3f}s 超过目标 (<{TARGET_P95_RESPONSE_TIME}s)\n"

        if error_rate_pass:
            report += f"  ✓ 错误率 {result.error_rate*100:.2f}% 符合目标 (<{TARGET_ERROR_RATE*100}%)\n"
        else:
            report += f"  ✗ 错误率 {result.error_rate*100:.2f}% 超过目标 (<{TARGET_ERROR_RATE*100}%)\n"

        if result.throughput >= TARGET_THROUGHPUT:
            report += f"  ✓ 吞吐量 {result.throughput:.2f} req/s 达到目标 (>{TARGET_THROUGHPUT} req/s)\n"
        else:
            report += f"  ⚠ 吞吐量 {result.throughput:.2f} req/s 未达到目标 (>{TARGET_THROUGHPUT} req/s)\n"

        report += f"""
{'='*80}
                          报告结束
{'='*80}
"""

        return report


# ==================== 主函数 ====================
async def main():
    """主函数"""
    print("=" * 80)
    print("        企业级智能文档问答平台 - 100并发用户压力测试")
    print("=" * 80)

    # 检查服务是否可用
    print(f"\n检查服务状态...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                print(f"✅ 服务正常 (状态码: {response.status_code})")
            else:
                print(f"⚠️ 服务返回异常状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 无法连接到服务: {e}")
        print(f"请确保服务已启动: uv run uvicorn backend.main:app")
        return

    # 显示系统信息
    print(f"\n系统信息:")
    print(f"  - CPU 核心数: {psutil.cpu_count()} 核")
    print(f"  - 总内存: {psutil.virtual_memory().total / (1024**3):.1f} GB")
    print(f"  - 可用内存: {psutil.virtual_memory().available / (1024**3):.1f} GB")

    # 创建测试器并运行测试
    tester = StressTester()

    try:
        result = await tester.run_concurrent_load_test(
            concurrent_users=TARGET_CONCURRENT_USERS,
            duration=TEST_DURATION,
            warmup_duration=WARMUP_DURATION,
        )

        # 生成并打印报告
        report = tester.generate_report(result)
        print(report)

        # 保存报告到文件
        report_filename = (
            f"tests/report_100users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n📄 报告已保存到: {report_filename}")

    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
