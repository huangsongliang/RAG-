"""部署A/B测试模块 - 支持实验配置、分组分配和效果统计"""

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ExperimentStatus(Enum):
    """实验状态"""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@dataclass
class ExperimentConfig:
    """实验配置"""

    min_sample_size: int = 100
    confidence_level: float = 0.95
    test_duration_days: int = 7
    auto_stop: bool = False
    primary_metric: str = "ctr"
    secondary_metrics: List[str] = field(default_factory=list)


@dataclass
class ExperimentGroup:
    """实验分组"""

    group_id: str
    name: str
    description: str
    version_id: str
    traffic_percentage: float
    config: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Experiment:
    """实验"""

    experiment_id: str
    name: str
    description: str
    status: ExperimentStatus
    groups: List[ExperimentGroup]
    config: ExperimentConfig
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: str = "system"
    tags: List[str] = field(default_factory=list)

    def get_group_by_id(self, group_id: str) -> Optional[ExperimentGroup]:
        """根据ID获取分组"""
        for group in self.groups:
            if group.group_id == group_id:
                return group
        return None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "groups": [
                {
                    "group_id": g.group_id,
                    "name": g.name,
                    "description": g.description,
                    "version_id": g.version_id,
                    "traffic_percentage": g.traffic_percentage,
                    "config": g.config,
                    "metrics": g.metrics,
                }
                for g in self.groups
            ],
            "config": {
                "min_sample_size": self.config.min_sample_size,
                "confidence_level": self.config.confidence_level,
                "test_duration_days": self.config.test_duration_days,
                "auto_stop": self.config.auto_stop,
                "primary_metric": self.config.primary_metric,
                "secondary_metrics": self.config.secondary_metrics,
            },
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by": self.created_by,
            "tags": self.tags,
        }


@dataclass
class ExperimentResult:
    """实验结果"""

    experiment_id: str
    group_id: str
    timestamp: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0.0
    latency_ms: float = 0.0
    custom_metrics: Dict[str, Any] = field(default_factory=dict)


class DeploymentABTestManager:
    """部署A/B测试管理器"""

    def __init__(self):
        self._experiments: Dict[str, Experiment] = {}
        self._results: Dict[str, List[ExperimentResult]] = {}
        self._user_assignments: Dict[str, str] = {}

    def create_experiment(
        self,
        name: str,
        description: str,
        groups: List[Dict[str, Any]],
        config: Optional[Dict[str, Any]] = None,
        created_by: str = "system",
        tags: Optional[List[str]] = None,
    ) -> Experiment:
        """创建实验"""
        experiment_id = self._generate_experiment_id(name)

        total_traffic = sum(g.get("traffic_percentage", 0) for g in groups)
        if abs(total_traffic - 100.0) > 0.01:
            raise ValueError(f"分组流量分配总和必须为100%，当前为{total_traffic}%")

        experiment_groups = [
            ExperimentGroup(
                group_id=self._generate_group_id(experiment_id, i),
                name=g["name"],
                description=g.get("description", ""),
                version_id=g["version_id"],
                traffic_percentage=g.get("traffic_percentage", 0),
                config=g.get("config", {}),
            )
            for i, g in enumerate(groups)
        ]

        experiment_config = ExperimentConfig(
            min_sample_size=config.get("min_sample_size", 100) if config else 100,
            confidence_level=config.get("confidence_level", 0.95) if config else 0.95,
            test_duration_days=config.get("test_duration_days", 7) if config else 7,
            auto_stop=config.get("auto_stop", False) if config else False,
            primary_metric=config.get("primary_metric", "ctr") if config else "ctr",
            secondary_metrics=config.get("secondary_metrics", []) if config else [],
        )

        experiment = Experiment(
            experiment_id=experiment_id,
            name=name,
            description=description,
            status=ExperimentStatus.DRAFT,
            groups=experiment_groups,
            config=experiment_config,
            created_at=datetime.now(),
            created_by=created_by,
            tags=tags or [],
        )

        self._experiments[experiment_id] = experiment
        self._results[experiment_id] = []

        logger.info(f"创建实验: {name} ({experiment_id})")
        return experiment

    def start_experiment(self, experiment_id: str) -> bool:
        """启动实验"""
        if experiment_id not in self._experiments:
            return False

        experiment = self._experiments[experiment_id]
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now()

        logger.info(f"启动实验: {experiment.name}")
        return True

    def pause_experiment(self, experiment_id: str) -> bool:
        """暂停实验"""
        if experiment_id not in self._experiments:
            return False

        experiment = self._experiments[experiment_id]
        experiment.status = ExperimentStatus.PAUSED

        logger.info(f"暂停实验: {experiment.name}")
        return True

    def complete_experiment(self, experiment_id: str) -> bool:
        """完成实验"""
        if experiment_id not in self._experiments:
            return False

        experiment = self._experiments[experiment_id]
        experiment.status = ExperimentStatus.COMPLETED
        experiment.completed_at = datetime.now()

        logger.info(f"完成实验: {experiment.name}")
        return True

    def archive_experiment(self, experiment_id: str) -> bool:
        """归档实验"""
        if experiment_id not in self._experiments:
            return False

        experiment = self._experiments[experiment_id]
        experiment.status = ExperimentStatus.ARCHIVED

        logger.info(f"归档实验: {experiment.name}")
        return True

    def delete_experiment(self, experiment_id: str) -> bool:
        """删除实验及其结果数据"""
        if experiment_id not in self._experiments:
            return False

        experiment_name = self._experiments[experiment_id].name
        del self._experiments[experiment_id]
        self._results.pop(experiment_id, None)

        # 清理相关用户分配缓存
        keys_to_remove = [k for k in self._user_assignments if k.startswith(f"{experiment_id}:")]
        for key in keys_to_remove:
            del self._user_assignments[key]

        logger.info(f"删除实验: {experiment_name} ({experiment_id})")
        return True

    def assign_group(
        self,
        experiment_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[ExperimentGroup]:
        """为用户分配实验分组

        Args:
            experiment_id: 实验 ID
            user_id: 用户 ID（已登录用户），用于确定性的分桶
            session_id: 会话 ID（未登录用户），用于确定性的分桶

        Returns:
            分配的实验分组，或 None

        分桶策略：
        - 优先使用 user_id 做确定性哈希分桶
        - 其次使用 session_id
        - 两者都无时，使用固定 key "anonymous" 保证同批次匿名用户在同一分组
        """
        if experiment_id not in self._experiments:
            return None

        experiment = self._experiments[experiment_id]
        if experiment.status != ExperimentStatus.RUNNING:
            return None

        identifier = user_id or session_id or "anonymous"

        cache_key = f"{experiment_id}:{identifier}"
        if cache_key in self._user_assignments:
            group_id = self._user_assignments[cache_key]
            return experiment.get_group_by_id(group_id)

        hash_value = self._calculate_hash(identifier)
        percentage = hash_value % 10000 / 100.0

        cumulative = 0.0
        for group in experiment.groups:
            cumulative += group.traffic_percentage
            if percentage < cumulative:
                self._user_assignments[cache_key] = group.group_id
                return group

        return experiment.groups[0] if experiment.groups else None

    def record_result(self, result: ExperimentResult) -> bool:
        """记录实验结果"""
        if result.experiment_id not in self._experiments:
            return False

        self._results[result.experiment_id].append(result)

        experiment = self._experiments[result.experiment_id]
        group = experiment.get_group_by_id(result.group_id)
        if group:
            self._update_group_metrics(group, result)

        return True

    def _update_group_metrics(self, group: ExperimentGroup, result: ExperimentResult):
        """更新分组指标"""
        if "total_impressions" not in group.metrics:
            group.metrics["total_impressions"] = 0
            group.metrics["total_clicks"] = 0
            group.metrics["total_conversions"] = 0
            group.metrics["total_revenue"] = 0.0
            group.metrics["total_latency"] = 0.0
            group.metrics["sample_count"] = 0

        group.metrics["total_impressions"] += result.impressions
        group.metrics["total_clicks"] += result.clicks
        group.metrics["total_conversions"] += result.conversions
        group.metrics["total_revenue"] += result.revenue
        group.metrics["total_latency"] += result.latency_ms
        group.metrics["sample_count"] += 1

        if group.metrics["total_impressions"] > 0:
            group.metrics["ctr"] = group.metrics["total_clicks"] / group.metrics["total_impressions"]

        if group.metrics["total_clicks"] > 0:
            group.metrics["conversion_rate"] = group.metrics["total_conversions"] / group.metrics["total_clicks"]

        if group.metrics["sample_count"] > 0:
            group.metrics["avg_latency"] = group.metrics["total_latency"] / group.metrics["sample_count"]

        for key, value in result.custom_metrics.items():
            if key not in group.metrics:
                group.metrics[key] = 0
            group.metrics[key] += value

    def get_experiment_results(self, experiment_id: str) -> Dict[str, Any]:
        """获取实验结果分析"""
        if experiment_id not in self._experiments:
            return {}

        experiment = self._experiments[experiment_id]
        results = self._results.get(experiment_id, [])

        group_stats = {}
        for group in experiment.groups:
            group_results = [r for r in results if r.group_id == group.group_id]

            total_impressions = sum(r.impressions for r in group_results)
            total_clicks = sum(r.clicks for r in group_results)
            total_conversions = sum(r.conversions for r in group_results)
            total_revenue = sum(r.revenue for r in group_results)
            latencies = [r.latency_ms for r in group_results if r.latency_ms > 0]

            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
            avg_latency = (sum(latencies) / len(latencies)) if latencies else 0

            group_stats[group.group_id] = {
                "group_name": group.name,
                "version_id": group.version_id,
                "traffic_percentage": group.traffic_percentage,
                "sample_count": len(group_results),
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_conversions": total_conversions,
                "total_revenue": round(total_revenue, 2),
                "ctr": round(ctr, 2),
                "conversion_rate": round(conversion_rate, 2),
                "avg_latency_ms": round(avg_latency, 2),
                "sample_size_met": len(group_results) >= experiment.config.min_sample_size,
            }

        significance = self._calculate_statistical_significance(experiment, group_stats)

        return {
            "experiment_id": experiment_id,
            "name": experiment.name,
            "status": experiment.status.value,
            "total_samples": len(results),
            "minimum_sample_size": experiment.config.min_sample_size,
            "group_stats": group_stats,
            "significance": significance,
            "recommendation": self._generate_recommendation(group_stats, significance),
        }

    def _calculate_statistical_significance(
        self,
        experiment: Experiment,
        group_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        """计算统计显著性"""
        if len(experiment.groups) < 2:
            return {"is_significant": False, "confidence_level": 0, "p_value": 1.0}

        control_group = max(experiment.groups, key=lambda g: g.traffic_percentage)
        control_stats = group_stats.get(control_group.group_id, {})

        if not control_stats.get("sample_size_met"):
            return {"is_significant": False, "confidence_level": 0, "p_value": 1.0}

        primary_metric = experiment.config.primary_metric
        # ctr/conversion_rate 以百分比存储（如 2.5 表示 2.5%），Z 检验需归一化到 [0,1]
        proportion_metrics = {"ctr", "conversion_rate"}
        is_proportion = primary_metric in proportion_metrics

        improvements = []
        for group in experiment.groups:
            if group.group_id == control_group.group_id:
                continue

            group_stat = group_stats.get(group.group_id, {})
            if not group_stat.get("sample_size_met"):
                continue

            control_value = control_stats.get(primary_metric, 0)
            group_value = group_stat.get(primary_metric, 0)

            if control_value > 0:
                improvement = ((group_value - control_value) / control_value) * 100
            else:
                improvement = 0

            # Z 检验使用归一化后的比例值
            if is_proportion:
                z_control = control_value / 100.0
                z_group = group_value / 100.0
            else:
                z_control = control_value
                z_group = group_value

            p_value = self._calculate_p_value(
                control_stats.get("sample_count", 0),
                group_stat.get("sample_count", 0),
                z_control,
                z_group,
            )

            improvements.append(
                {
                    "group_id": group.group_id,
                    "group_name": group.name,
                    "improvement_percent": round(improvement, 2),
                    "p_value": round(p_value, 4),
                    "is_significant": p_value < (1 - experiment.config.confidence_level),
                }
            )

        is_significant = any(imp["is_significant"] for imp in improvements)
        confidence_level = 50
        if improvements:
            avg_improvement = sum(imp["improvement_percent"] for imp in improvements) / len(improvements)
            confidence_level = min(95, 50 + abs(avg_improvement))

        return {
            "is_significant": is_significant,
            "confidence_level": round(confidence_level, 2),
            "improvements": improvements,
        }

    def _calculate_p_value(
        self,
        n_control: int,
        n_treatment: int,
        p_control: float,
        p_treatment: float,
    ) -> float:
        """计算p值（简化的Z检验）"""
        if n_control == 0 or n_treatment == 0:
            return 1.0

        p_pooled = (p_control * n_control + p_treatment * n_treatment) / (n_control + n_treatment)

        if p_pooled == 0 or p_pooled == 1:
            return 1.0

        se = math.sqrt(p_pooled * (1 - p_pooled) * (1 / n_control + 1 / n_treatment))
        if se == 0:
            return 1.0

        z_score = abs(p_treatment - p_control) / se

        p_value = 2 * (1 - 0.5 * (1 + math.erf(z_score / math.sqrt(2))))

        return max(0.0, min(1.0, p_value))

    def _generate_recommendation(
        self,
        group_stats: Dict[str, Any],
        significance: Dict[str, Any],
    ) -> str:
        """生成推荐建议"""
        if not significance.get("is_significant"):
            return "样本量不足或差异不显著，建议继续收集数据"

        improvements = significance.get("improvements", [])
        if not improvements:
            return "未发现显著差异"

        best = max(improvements, key=lambda x: abs(x["improvement_percent"]))

        if best["improvement_percent"] > 0:
            return f"分组 '{best['group_name']}' 表现最佳，建议推广 (提升 {best['improvement_percent']}%)"
        else:
            return "对照组表现最佳，建议继续使用当前方案"

    def list_experiments(
        self,
        status: Optional[ExperimentStatus] = None,
    ) -> List[Dict[str, Any]]:
        """列出实验"""
        experiments = list(self._experiments.values())

        if status:
            experiments = [e for e in experiments if e.status == status]

        experiments.sort(key=lambda e: e.created_at, reverse=True)

        return [exp.to_dict() for exp in experiments]

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """获取实验详情"""
        return self._experiments.get(experiment_id)

    def _calculate_hash(self, identifier: str) -> int:
        """计算哈希值"""
        hash_bytes = hashlib.md5(identifier.encode(), usedforsecurity=False).digest()
        return int.from_bytes(hash_bytes[:4], byteorder="big")

    def _generate_experiment_id(self, name: str) -> str:
        """生成实验ID"""
        import time

        hash_input = f"{name}{time.time()}"
        return hashlib.md5(hash_input.encode(), usedforsecurity=False).hexdigest()[:12]

    def _generate_group_id(self, experiment_id: str, index: int) -> str:
        """生成分组ID"""
        return f"{experiment_id}_group_{index}"


_deployment_ab_test_manager = DeploymentABTestManager()


def get_deployment_ab_test_manager() -> DeploymentABTestManager:
    """获取部署A/B测试管理器实例"""
    return _deployment_ab_test_manager
