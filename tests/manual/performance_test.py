"""全面性能测试模块
测试覆盖：负载测试、压力测试、并发测试、响应时间测试
"""

import asyncio
import time
import statistics
import psutil
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""

    test_name: str
    concurrent_users: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    error_rate: float
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p50_response_time: float
    p95_response_time: float
    p99_response_time: float
    throughput: float
    avg_cpu_usage: float
    avg_memory_usage: float
    peak_memory_mb: float
    timestamp: str


class SystemMonitor:
    """系统资源监控器"""

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.cpu_samples: List[float] = []
        self.memory_samples: List[float] = []
        self.peak_memory = 0.0

    def start_monitoring(self):
        """开始监控"""
        self.cpu_samples.clear()
        self.memory_samples.clear()
        self.peak_memory = 0.0

    def sample(self):
        """采样系统资源"""
        try:
            cpu_percent = self.process.cpu_percent(interval=0.1)
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            self.cpu_samples.append(cpu_percent)
            self.memory_samples.append(memory_mb)
            self.peak_memory = max(self.peak_memory, memory_mb)
        except Exception as e:
            logger.error(f"资源采样失败: {e}")

    def get_stats(self) -> Dict[str, float]:
        """获取资源统计"""
        return {
            "avg_cpu": statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
            "avg_memory": (
                statistics.mean(self.memory_samples) if self.memory_samples else 0
            ),
            "peak_memory": self.peak_memory,
        }


class LoadTester:
    """负载测试器"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/api/chat"
        self.health_endpoint = f"{base_url}/health"
        self.system_monitor = SystemMonitor()

        # 基准性能指标
        self.baseline = {
            "response_time_p95": 2.0,  # 95%请求应在2秒内完成
            "error_rate_max": 5.0,  # 最大错误率5%
            "min_throughput": 10,  # 最小吞吐量 10 req/s
            "max_concurrent": 100,  # 最大并发数
        }

        # 测试查询列表
        self.test_queries = [
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

    async def check_health(self) -> bool:
        """检查服务健康状态"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.health_endpoint)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False

    async def send_request(
        self, client: httpx.AsyncClient, query: str, use_stream: bool = False
    ) -> Dict[str, Any]:
        """发送单个请求"""
        start_time = time.time()
        success = False
        error_msg = ""

        try:
            payload = {
                "message": query,
                "session_id": f"perf_test_{time.time()}",
                "use_rag": True,
                "top_k": 3,
            }

            if use_stream:
                async with client.stream(
                    "POST", self.api_endpoint + "/stream", json=payload, timeout=30.0
                ) as response:
                    full_content = ""
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            full_content += data
                    success = response.status_code == 200
            else:
                response = await client.post(
                    self.api_endpoint, json=payload, timeout=30.0
                )
                success = response.status_code == 200

            response_time = time.time() - start_time

        except Exception as e:
            response_time = time.time() - start_time
            error_msg = str(e)

        return {"success": success, "response_time": response_time, "error": error_msg}

    async def concurrent_load_test(
        self,
        concurrent_users: int,
        requests_per_user: int = 5,
        use_stream: bool = False,
    ) -> PerformanceMetrics:
        """并发负载测试"""
        test_name = f"concurrent_{concurrent_users}_users"
        logger.info(f"开始 {test_name} 测试...")

        self.system_monitor.start_monitoring()

        response_times = []
        success_count = 0
        fail_count = 0

        async def user_session(user_id: int):
            """模拟单个用户会话"""
            user_times = []
            user_success = 0
            user_fail = 0

            async with httpx.AsyncClient(timeout=30.0) as client:
                for i in range(requests_per_user):
                    query = self.test_queries[user_id % len(self.test_queries)]
                    result = await self.send_request(client, query, use_stream)

                    user_times.append(result["response_time"])
                    if result["success"]:
                        user_success += 1
                    else:
                        user_fail += 1

                    self.system_monitor.sample()

            return user_times, user_success, user_fail

        start_time = time.time()
        tasks = [user_session(i) for i in range(concurrent_users)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        for times, success, fail in results:
            response_times.extend(times)
            success_count += success
            fail_count += fail

        resource_stats = self.system_monitor.get_stats()

        sorted_times = sorted(response_times)
        total_requests = success_count + fail_count

        metrics = PerformanceMetrics(
            test_name=test_name,
            concurrent_users=concurrent_users,
            total_requests=total_requests,
            successful_requests=success_count,
            failed_requests=fail_count,
            error_rate=(fail_count / total_requests * 100) if total_requests > 0 else 0,
            avg_response_time=statistics.mean(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            p50_response_time=(
                sorted_times[len(sorted_times) // 2] if sorted_times else 0
            ),
            p95_response_time=(
                sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0
            ),
            p99_response_time=(
                sorted_times[int(len(sorted_times) * 0.99)] if sorted_times else 0
            ),
            throughput=total_requests / total_time if total_time > 0 else 0,
            avg_cpu_usage=resource_stats["avg_cpu"],
            avg_memory_usage=resource_stats["avg_memory"],
            peak_memory_mb=resource_stats["peak_memory"],
            timestamp=datetime.now().isoformat(),
        )

        logger.info(
            f"{test_name} 完成: {success_count}/{total_requests} 成功, "
            f"平均响应时间: {metrics.avg_response_time:.2f}s, "
            f"P95: {metrics.p95_response_time:.2f}s"
        )

        return metrics

    async def sustained_load_test(
        self, duration_seconds: int, requests_per_second: int = 5
    ) -> PerformanceMetrics:
        """持续负载测试"""
        test_name = f"sustained_{duration_seconds}s"
        logger.info(f"开始 {test_name} 持续负载测试...")

        self.system_monitor.start_monitoring()

        response_times = []
        success_count = 0
        fail_count = 0
        request_count = 0

        interval = 1.0 / requests_per_second
        end_time = time.time() + duration_seconds

        async with httpx.AsyncClient(timeout=30.0) as client:
            while time.time() < end_time:
                query = self.test_queries[request_count % len(self.test_queries)]
                result = await self.send_request(client, query)

                response_times.append(result["response_time"])
                if result["success"]:
                    success_count += 1
                else:
                    fail_count += 1

                request_count += 1
                self.system_monitor.sample()

                await asyncio.sleep(interval)

        resource_stats = self.system_monitor.get_stats()

        sorted_times = sorted(response_times)
        total_requests = success_count + fail_count
        total_time = duration_seconds

        metrics = PerformanceMetrics(
            test_name=test_name,
            concurrent_users=1,
            total_requests=total_requests,
            successful_requests=success_count,
            failed_requests=fail_count,
            error_rate=(fail_count / total_requests * 100) if total_requests > 0 else 0,
            avg_response_time=statistics.mean(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            p50_response_time=(
                sorted_times[len(sorted_times) // 2] if sorted_times else 0
            ),
            p95_response_time=(
                sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0
            ),
            p99_response_time=(
                sorted_times[int(len(sorted_times) * 0.99)] if sorted_times else 0
            ),
            throughput=total_requests / total_time if total_time > 0 else 0,
            avg_cpu_usage=resource_stats["avg_cpu"],
            avg_memory_usage=resource_stats["avg_memory"],
            peak_memory_mb=resource_stats["peak_memory"],
            timestamp=datetime.now().isoformat(),
        )

        logger.info(
            f"{test_name} 完成: {success_count}/{total_requests} 成功, "
            f"吞吐量: {metrics.throughput:.2f} req/s"
        )

        return metrics

    async def spike_load_test(
        self, normal_load: int, spike_load: int, spike_duration: int = 10
    ) -> Dict[str, PerformanceMetrics]:
        """负载峰值测试（突然增加负载）"""
        logger.info(f"开始负载峰值测试: 正常={normal_load}, 峰值={spike_load}")

        results = {}

        # 正常负载阶段
        results["normal"] = await self.concurrent_load_test(
            concurrent_users=normal_load, requests_per_user=3
        )

        await asyncio.sleep(5)

        # 峰值负载阶段
        results["spike"] = await self.concurrent_load_test(
            concurrent_users=spike_load, requests_per_user=3
        )

        await asyncio.sleep(5)

        # 恢复阶段
        results["recovery"] = await self.concurrent_load_test(
            concurrent_users=normal_load, requests_per_user=3
        )

        return results

    async def run_full_suite(self) -> Dict[str, Any]:
        """运行完整测试套件"""
        logger.info("=" * 60)
        logger.info("开始全面性能测试套件")
        logger.info("=" * 60)

        all_results = {"baseline": self.baseline, "tests": {}, "summary": {}}

        # 1. 健康检查
        logger.info("检查服务健康状态...")
        is_healthy = await self.check_health()
        all_results["service_healthy"] = is_healthy

        if not is_healthy:
            logger.error("服务不可用，测试终止")
            return all_results

        # 2. 正常负载测试 (10 并发)
        logger.info("\n[1/6] 正常负载测试 (10 并发用户)")
        all_results["tests"]["normal_load_10"] = await self.concurrent_load_test(
            concurrent_users=10, requests_per_user=5
        )
        await asyncio.sleep(3)

        # 3. 中等负载测试 (30 并发)
        logger.info("\n[2/6] 中等负载测试 (30 并发用户)")
        all_results["tests"]["medium_load_30"] = await self.concurrent_load_test(
            concurrent_users=30, requests_per_user=5
        )
        await asyncio.sleep(3)

        # 4. 高负载测试 (50 并发)
        logger.info("\n[3/6] 高负载测试 (50 并发用户)")
        all_results["tests"]["high_load_50"] = await self.concurrent_load_test(
            concurrent_users=50, requests_per_user=5
        )
        await asyncio.sleep(3)

        # 5. 压力测试 (100 并发)
        logger.info("\n[4/6] 压力测试 (100 并发用户)")
        all_results["tests"]["stress_load_100"] = await self.concurrent_load_test(
            concurrent_users=100, requests_per_user=3
        )
        await asyncio.sleep(3)

        # 6. 极限负载测试 (200 并发)
        logger.info("\n[5/6] 极限负载测试 (200 并发用户)")
        all_results["tests"]["extreme_load_200"] = await self.concurrent_load_test(
            concurrent_users=200, requests_per_user=2
        )
        await asyncio.sleep(3)

        # 7. 持续负载测试 (30秒)
        logger.info("\n[6/6] 持续负载测试 (30秒)")
        all_results["tests"]["sustained_load"] = await self.sustained_load_test(
            duration_seconds=30, requests_per_second=10
        )

        # 生成摘要
        all_results["summary"] = self.generate_summary(all_results["tests"])

        logger.info("\n" + "=" * 60)
        logger.info("性能测试完成")
        logger.info("=" * 60)

        return all_results

    def generate_summary(self, tests: Dict[str, PerformanceMetrics]) -> Dict[str, Any]:
        """生成测试摘要"""
        summary = {"total_tests": len(tests), "all_passed": True, "results": []}

        for test_name, metrics in tests.items():
            result = {
                "test_name": test_name,
                "concurrent_users": metrics.concurrent_users,
                "total_requests": metrics.total_requests,
                "error_rate": metrics.error_rate,
                "avg_response_time": metrics.avg_response_time,
                "p95_response_time": metrics.p95_response_time,
                "throughput": metrics.throughput,
                "passed": self.evaluate_test(metrics),
            }
            summary["results"].append(result)

            if not result["passed"]:
                summary["all_passed"] = False

        return summary

    def evaluate_test(self, metrics: PerformanceMetrics) -> bool:
        """评估测试是否通过基准"""
        checks = [
            metrics.p95_response_time <= self.baseline["response_time_p95"],
            metrics.error_rate <= self.baseline["error_rate_max"],
            metrics.throughput >= self.baseline["min_throughput"],
        ]
        return all(checks)

    def print_report(self, results: Dict[str, Any]):
        """打印测试报告"""
        report = f"""
{'=' * 80}
                        企业级智能文档问答平台 - 性能测试报告
{'=' * 80}

测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
服务状态: {'健康' if results.get('service_healthy') else '不健康'}

一、基准性能指标
------------------
- P95 响应时间: ≤ {self.baseline['response_time_p95']}s
- 最大错误率: ≤ {self.baseline['error_rate_max']}%
- 最小吞吐量: ≥ {self.baseline['min_throughput']} req/s
- 最大并发: {self.baseline['max_concurrent']} 用户

二、测试结果汇总
------------------
"""

        for result in results["summary"].get("results", []):
            status_icon = "✓" if result["passed"] else "✗"
            report += f"""
【{status_icon}】{result['test_name']}
  - 并发用户: {result['concurrent_users']}
  - 总请求数: {result['total_requests']}
  - 错误率: {result['error_rate']:.2f}%
  - 平均响应时间: {result['avg_response_time']:.3f}s
  - P95 响应时间: {result['p95_response_time']:.3f}s
  - 吞吐量: {result['throughput']:.2f} req/s
  - 状态: {'通过' if result['passed'] else '未通过'}
"""

        report += f"""
三、详细测试结果
------------------
"""

        for test_name, metrics in results.get("tests", {}).items():
            report += f"""
【{test_name}】
  请求统计:
    - 总请求: {metrics.total_requests}
    - 成功: {metrics.successful_requests}
    - 失败: {metrics.failed_requests}

  响应时间:
    - 平均: {metrics.avg_response_time:.3f}s
    - 最小: {metrics.min_response_time:.3f}s
    - 最大: {metrics.max_response_time:.3f}s
    - P50: {metrics.p50_response_time:.3f}s
    - P95: {metrics.p95_response_time:.3f}s
    - P99: {metrics.p99_response_time:.3f}s

  资源使用:
    - 平均 CPU: {metrics.avg_cpu_usage:.1f}%
    - 平均内存: {metrics.avg_memory_usage:.1f} MB
    - 峰值内存: {metrics.peak_memory_mb:.1f} MB

  吞吐量: {metrics.throughput:.2f} req/s
"""

        report += """
四、性能优化建议
------------------
"""

        summary = results.get("summary", {})
        for result in summary.get("results", []):
            if not result["passed"]:
                if result["p95_response_time"] > self.baseline["response_time_p95"]:
                    report += f"- {result['test_name']}: P95响应时间超过基准，建议优化缓存策略或增加资源\n"
                if result["error_rate"] > self.baseline["error_rate_max"]:
                    report += (
                        f"- {result['test_name']}: 错误率过高，建议检查服务稳定性\n"
                    )
                if result["throughput"] < self.baseline["min_throughput"]:
                    report += f"- {result['test_name']}: 吞吐量较低，建议优化查询性能\n"

        if summary.get("all_passed"):
            report += "- 所有测试均已通过！系统性能符合预期。\n"

        report += f"""
{'=' * 80}
                              测试报告结束
{'=' * 80}
"""

        print(report)
        return report


async def main():
    """主函数"""
    tester = LoadTester(base_url="http://localhost:8000")

    results = await tester.run_full_suite()
    report = tester.print_report(results)

    return results, report


if __name__ == "__main__":
    asyncio.run(main())
