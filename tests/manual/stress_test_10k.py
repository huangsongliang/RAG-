"""
万人并发压力测试脚本
目标：模拟 10,000 并发用户，P95 < 5s，错误率 < 1%
"""

import asyncio
import time
import statistics
import random
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import httpx
from concurrent.futures import ThreadPoolExecutor
import sys

# ==================== 配置 ====================
TARGET_CONCURRENT_USERS = 10000  # 目标并发用户数
RAMP_UP_TIME = 60  # 预热时间（秒）
TEST_DURATION = 300  # 测试持续时间（秒）
BASE_URL = "http://localhost:80"  # Nginx 入口

# 性能目标
TARGET_P95_RESPONSE_TIME = 5.0  # 秒
TARGET_ERROR_RATE = 0.01  # 1%
TARGET_THROUGHPUT = 1000  # 请求/秒

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
class RequestMetrics:
    """请求指标"""

    success_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    response_times: List[float] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    @property
    def total_requests(self) -> int:
        return self.success_count + self.error_count + self.timeout_count

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.error_count + self.timeout_count) / self.total_requests

    @property
    def success_rate(self) -> float:
        return 1.0 - self.error_rate

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
    duration: float
    timestamp: str


# ==================== 测试客户端 ====================
class LoadTestClient:
    """负载测试客户端"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.session_id = f"user_{user_id}_{int(time.time())}"
        self.query_count = 0
        self.metrics = RequestMetrics()
        self._client = None

    async def initialize(self):
        """初始化客户端"""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
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

            if response.status_code == 200:
                self.metrics.success_count += 1
                self.metrics.response_times.append(response_time)
                return {"success": True, "response_time": response_time}
            else:
                self.metrics.error_count += 1
                return {"success": False, "error": f"HTTP {response.status_code}"}

        except httpx.TimeoutException:
            self.metrics.timeout_count += 1
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            self.metrics.error_count += 1
            return {"success": False, "error": str(e)}


# ==================== 主测试类 ====================
class StressTester:
    """压力测试器"""

    def __init__(self):
        self.clients: List[LoadTestClient] = []
        self.global_metrics = RequestMetrics()
        self.test_start_time = 0
        self.running = False

    async def setup_clients(self, count: int):
        """初始化客户端池"""
        print(f"初始化 {count} 个测试客户端...")
        self.clients = [LoadTestClient(i) for i in range(count)]

        # 并发初始化
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
            # 随机等待 0.5-3 秒
            await asyncio.sleep(random.uniform(0.5, 3.0))

    async def run_concurrent_load_test(
        self, concurrent_users: int, duration: int, ramp_up_time: int = 60
    ) -> TestResult:
        """运行并发负载测试"""
        print(f"\n{'='*80}")
        print(f"开始压力测试: {concurrent_users} 并发用户, 持续 {duration} 秒")
        print(f"{'='*80}\n")

        # 初始化客户端
        await self.setup_clients(concurrent_users)

        self.running = True
        self.test_start_time = time.time()

        # 分阶段启动用户
        print(f"预热阶段 ({ramp_up_time}秒)...")

        # 第一阶段：渐进式增加用户
        phases = [
            (concurrent_users // 4, ramp_up_time // 4),
            (concurrent_users // 2, ramp_up_time // 2),
            (int(concurrent_users * 0.75), ramp_up_time // 4),
            (concurrent_users, ramp_up_time // 4),
        ]

        for target_users, phase_duration in phases:
            print(f"  -> 增加到 {target_users} 用户...")

            # 启动目标数量的用户
            active_clients = self.clients[:target_users]
            tasks = [
                self.run_user_session(client, phase_duration)
                for client in active_clients
            ]
            await asyncio.gather(*tasks)

        # 收集所有客户端的指标
        print("\n收集测试结果...")
        for client in self.clients:
            self.global_metrics.success_count += client.metrics.success_count
            self.global_metrics.error_count += client.metrics.error_count
            self.global_metrics.timeout_count += client.metrics.timeout_count
            self.global_metrics.response_times.extend(client.metrics.response_times)

        self.running = False

        # 计算最终结果
        duration = time.time() - self.test_start_time
        total_requests = self.global_metrics.total_requests

        result = TestResult(
            concurrent_users=concurrent_users,
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
            throughput=total_requests / duration if duration > 0 else 0,
            duration=duration,
            timestamp=datetime.now().isoformat(),
        )

        await self.cleanup_clients()

        return result

    def print_result(self, result: TestResult):
        """打印测试结果"""
        print(f"\n{'='*80}")
        print(f"                          压力测试结果报告")
        print(f"{'='*80}\n")

        print(f"测试配置:")
        print(f"  - 并发用户数: {result.concurrent_users:,}")
        print(f"  - 测试时长: {result.duration:.2f} 秒")
        print(f"  - 目标 P95 响应时间: {TARGET_P95_RESPONSE_TIME}s")
        print(f"  - 目标错误率: {TARGET_ERROR_RATE * 100}%\n")

        print(f"请求统计:")
        print(f"  - 总请求数: {result.total_requests:,}")
        print(
            f"  - 成功请求: {result.success_count:,} ({result.success_rate * 100:.2f}%)"
        )
        print(f"  - 失败请求: {result.error_count:,} ({result.error_rate * 100:.2f}%)")
        print(f"  - 超时请求: {result.timeout_count:,}\n")

        print(f"响应时间:")
        print(f"  - 平均: {result.avg_response_time:.3f}s")
        print(f"  - 最小: {result.min_response_time:.3f}s")
        print(f"  - 最大: {result.max_response_time:.3f}s")
        print(f"  - P50: {result.p50_response_time:.3f}s")
        print(f"  - P95: {result.p95_response_time:.3f}s")
        print(f"  - P99: {result.p99_response_time:.3f}s\n")

        print(f"吞吐量: {result.throughput:.2f} req/s\n")

        # 性能评估
        print(f"性能评估:")

        p95_pass = result.p95_response_time <= TARGET_P95_RESPONSE_TIME
        error_rate_pass = result.error_rate <= TARGET_ERROR_RATE
        throughput_pass = result.throughput >= TARGET_THROUGHPUT

        print(
            f"  - P95 响应时间: {'✅ 通过' if p95_pass else '❌ 未通过'} "
            f"(目标 ≤ {TARGET_P95_RESPONSE_TIME}s, 实际 {result.p95_response_time:.3f}s)"
        )
        print(
            f"  - 错误率: {'✅ 通过' if error_rate_pass else '❌ 未通过'} "
            f"(目标 ≤ {TARGET_ERROR_RATE * 100}%, 实际 {result.error_rate * 100:.2f}%)"
        )
        print(
            f"  - 吞吐量: {'✅ 通过' if throughput_pass else '❌ 未通过'} "
            f"(目标 ≥ {TARGET_THROUGHPUT} req/s, 实际 {result.throughput:.2f} req/s)"
        )

        overall_pass = p95_pass and error_rate_pass and throughput_pass
        print(f"\n总体评估: {'🎉 测试通过' if overall_pass else '⚠️  测试未通过'}")

        print(f"\n{'='*80}\n")


# ==================== 主函数 ====================
async def main():
    """主函数"""
    print("=" * 80)
    print("        企业级智能文档问答平台 - 万人并发压力测试")
    print("=" * 80)
    print(f"\n目标性能指标:")
    print(f"  - 并发用户: {TARGET_CONCURRENT_USERS:,}")
    print(f"  - P95 响应时间: < {TARGET_P95_RESPONSE_TIME}s")
    print(f"  - 错误率: < {TARGET_ERROR_RATE * 100}%")
    print(f"  - 吞吐量: > {TARGET_THROUGHPUT} req/s")

    # 检查服务是否可用
    print(f"\n检查服务状态...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BASE_URL}/health")
            if response.status_code != 200:
                print(f"❌ 服务不可用 (HTTP {response.status_code})")
                return
            print(f"✅ 服务正常")
    except Exception as e:
        print(f"❌ 无法连接到服务: {e}")
        print(f"请确保服务已启动: docker-compose up -d")
        return

    # 创建测试器并运行测试
    tester = StressTester()

    try:
        result = await tester.run_concurrent_load_test(
            concurrent_users=TARGET_CONCURRENT_USERS,
            duration=TEST_DURATION,
            ramp_up_time=RAMP_UP_TIME,
        )

        tester.print_result(result)

    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("提示: 万人并发测试需要大量系统资源")
    print("建议在生产环境或高配服务器上运行\n")

    # 允许通过命令行参数调整并发数
    if len(sys.argv) > 1:
        TARGET_CONCURRENT_USERS = int(sys.argv[1])
        print(f"使用自定义并发数: {TARGET_CONCURRENT_USERS}")

    asyncio.run(main())
