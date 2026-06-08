"""实体抽取模块 - 基于 HanLP + SpaCy + 规则的三层混合 NER"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ---- SpaCy 检测 ----
try:
    import spacy

    SPACY_AVAILABLE = True
except ImportError:
    spacy = None
    SPACY_AVAILABLE = False
    logger.warning("SpaCy 未安装，将使用基于规则的实体抽取")

# ---- HanLP 检测 ----
try:
    import hanlp as _hanlp_lib

    HANLP_AVAILABLE = True
except ImportError:
    _hanlp_lib = None
    HANLP_AVAILABLE = False
    logger.warning("HanLP 未安装，将回退到 SpaCy / 规则抽取")


# =====================================================
# 共享规则引擎（供 HanLP 补充 & 纯规则降级用）
# =====================================================

# 日期 / 时间 / 数字类模式 —— HanLP 对这类实体覆盖弱，用规则补充
_NUMERIC_PATTERNS: List[Tuple[str, str]] = [
    # 日期
    (r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", "DATE"),
    (r"\d{1,2}:\d{2}(:\d{2})?", "TIME"),
    (r"\d{4}年\d{1,2}月\d{1,2}日", "DATE"),
    (r"\d{4}年\d{1,2}月", "DATE"),
    (r"\d{1,2}月\d{1,2}日", "DATE"),
    (r"\d{4}年", "DATE"),
    # 钱 / 百分比
    (r"\d+(\.\d+)?%", "PERCENT"),
    (r"\d+(\.\d+)?亿(美元|欧元|元)?", "MONEY"),
    (r"\d+(\.\d+)?万(美元|欧元|元)?", "MONEY"),
    (r"\d+(\.\d+)?美元", "MONEY"),
    (r"\d+(\.\d+)?欧元", "MONEY"),
    (r"\d+(\.\d+)?元", "MONEY"),
    (r"\d+%[以]?[上下]", "PERCENT"),
    # 数量
    (r"\d+(\.\d+)?\s*(个|只|台|件|次|倍|人|家)", "QUANTITY"),
]

# 完整规则库 —— 包含 NUMERIC + ORG/PERSON/GPE/PRODUCT/TECHNOLOGY
_FULL_RULE_PATTERNS: List[Tuple[str, str]] = _NUMERIC_PATTERNS + [
    # 组织
    (r"[\u4e00-\u9fa5]+公司", "ORG"),
    (r"[\u4e00-\u9fa5]+集团", "ORG"),
    (r"[\u4e00-\u9fa5]+科技", "ORG"),
    (r"[\u4e00-\u9fa5]+股份", "ORG"),
    (r"[\u4e00-\u9fa5]+股份有限公司", "ORG"),
    (r"[\u4e00-\u9fa5]+有限公司", "ORG"),
    (r"[\u4e00-\u9fa5]+科技有限公司", "ORG"),
    (r"[\u4e00-\u9fa5]+技术有限公司", "ORG"),
    (r"[\u4e00-\u9fa5]+互联网", "ORG"),
    (r"[\u4e00-\u9fa5]+网络", "ORG"),
    (r"[\u4e00-\u9fa5]+软件", "ORG"),
    (r"[\u4e00-\u9fa5]+数据", "ORG"),
    (r"[\u4e00-\u9fa5]+智能", "ORG"),
    (r"[\u4e00-\u9fa5]+研究院", "ORG"),
    (r"[\u4e00-\u9fa5]+研究所", "ORG"),
    (r"[\u4e00-\u9fa5]+大学", "ORG"),
    (r"[\u4e00-\u9fa5]+学院", "ORG"),
    (r"[\u4e00-\u9fa5]+中学", "ORG"),
    (r"[\u4e00-\u9fa5]+小学", "ORG"),
    (r"[\u4e00-\u9fa5]+医院", "ORG"),
    (r"[\u4e00-\u9fa5]+银行", "ORG"),
    (r"[\u4e00-\u9fa5]+基金", "ORG"),
    (r"[\u4e00-\u9fa5]+保险", "ORG"),
    (r"[\u4e00-\u9fa5]+证券", "ORG"),
    # 常见国家
    (
        r"美国|中国|日本|韩国|英国|法国|德国|加拿大|澳大利亚|新加坡|马来西亚|印度|俄罗斯|泰国|越南|印度尼西亚|菲律宾|意大利|西班牙|荷兰|瑞士|瑞典|挪威|丹麦|芬兰|新西兰|巴西|阿根廷|墨西哥|南非",
        "GPE",
    ),
    # 中国城市
    (
        r"北京|上海|广州|深圳|杭州|南京|武汉|成都|重庆|天津|苏州|西安|郑州|长沙|沈阳|青岛|宁波|厦门|大连|无锡|佛山|东莞|珠海|中山",
        "GPE",
    ),
    (
        r"北京市|上海市|广州市|深圳市|杭州市|南京市|武汉市|成都市|重庆市|天津市|苏州市|西安市|郑州市|长沙市|沈阳市|青岛市|宁波市|厦门市|大连市|无锡市|佛山市|东莞市|珠海市|中山市",
        "GPE",
    ),
    # 中国省份
    (
        r"江苏省|浙江省|广东省|山东省|四川省|湖北省|湖南省|河南省|河北省|安徽省|福建省|江西省|山西省|陕西省|辽宁省|吉林省|黑龙江省|云南省|贵州省|海南省|台湾省|广西壮族自治区|西藏自治区|新疆维吾尔自治区|内蒙古自治区|宁夏回族自治区|香港特别行政区|澳门特别行政区",
        "GPE",
    ),
    # 人物（含职位后缀）
    (
        r"[\u4e00-\u9fa5]{2,4}(创始人|CEO|董事长|总裁|总经理|首席执行官|首席技术官|首席运营官|首席财务官|CTO|COO|CFO|副总裁|总监|经理|博士|教授|研究员|院士)",
        "PERSON",
    ),
    (r"([\u4e00-\u9fa5]{2,4})是创始人", "PERSON"),
    (r"([\u4e00-\u9fa5]{2,4})(创立|创建|创办)了", "PERSON"),
    (r"由([\u4e00-\u9fa5]{2,4})(创立|创建)", "PERSON"),
    # 知名人物（硬编码常见名，提高召回）
    (
        r"乔布斯|比尔·盖茨|马斯克|马云|马化腾|李彦宏|雷军|任正非|董明珠|王健林|许家印|丁磊|张一鸣|黄峥|刘强东|俞敏洪|周鸿祎|李开复|沈南鹏|孙正义|巴菲特|查理·芒格",
        "PERSON",
    ),
    # 产品
    (r"微信|支付宝|淘宝|天猫|京东|拼多多|抖音|快手|美团|滴滴|小红书|微博|B站|知乎|百度", "PRODUCT"),
    (r"iPhone|iPad|Mac|华为|小米|OPPO|vivo|荣耀|联想|戴尔|华硕|三星|索尼|微软|Windows|Office", "PRODUCT"),
    # 技术
    (
        r"人工智能|机器学习|深度学习|神经网络|自然语言处理|NLP|计算机视觉|CV|RAG|检索增强生成|LLM|大语言模型|GPT|Transformer|向量数据库|知识图谱|云计算|大数据|区块链|元宇宙|物联网|IoT|边缘计算|量子计算|5G|6G|API|REST|GraphQL|微服务|容器化|Docker|Kubernetes|K8s|CI/CD|DevOps",
        "TECHNOLOGY",
    ),
]

# HanLP 辅助规则 —— 仅补充 HanLP 不覆盖的类型（NUMERIC + PRODUCT + TECHNOLOGY）
# 不包含 PERSON/ORG/GPE 规则，避免与 HanLP 的高精度模型冲突
_SUPPLEMENT_PATTERNS: List[Tuple[str, str]] = _NUMERIC_PATTERNS + [
    # 产品
    (r"微信|支付宝|淘宝|天猫|京东|拼多多|抖音|快手|美团|滴滴|小红书|微博|B站|知乎|百度", "PRODUCT"),
    (r"iPhone|iPad|Mac|华为|小米|OPPO|vivo|荣耀|联想|戴尔|华硕|三星|索尼|微软|Windows|Office", "PRODUCT"),
    # 技术
    (
        r"人工智能|机器学习|深度学习|神经网络|自然语言处理|NLP|计算机视觉|CV|RAG|检索增强生成|LLM|大语言模型|GPT|Transformer|向量数据库|知识图谱|云计算|大数据|区块链|元宇宙|物联网|IoT|边缘计算|量子计算|5G|6G|API|REST|GraphQL|微服务|容器化|Docker|Kubernetes|K8s|CI/CD|DevOps",
        "TECHNOLOGY",
    ),
    # 硬编码人物名（HanLP 对其余不覆盖的知名人物做兜底）
    (
        r"乔布斯|比尔·盖茨|马斯克|马云|马化腾|李彦宏|雷军|任正非|董明珠|王健林|许家印|丁磊|张一鸣|黄峥|刘强东|俞敏洪|周鸿祎|李开复|沈南鹏|孙正义|巴菲特|查理·芒格",
        "PERSON",
    ),
]


def _apply_rule_patterns(
    text: str,
    patterns: List[Tuple[str, str]],
    entities_filter: Optional[List[str]],
    source_name: str,
    confidence: float,
) -> List["Entity"]:
    """通用规则匹配引擎

    Args:
        text: 输入文本
        patterns: (正则, 标签) 模式列表
        entities_filter: 类型过滤器
        source_name: 来源标记名
        confidence: 统一置信度

    Returns:
        实体列表
    """
    entities: List[Entity] = []
    seen: Set[Tuple[str, str, int]] = set()

    for pattern, label in patterns:
        if entities_filter and label not in entities_filter:
            continue

        for match in re.finditer(pattern, text):
            matched_text = match.group()
            if len(matched_text) == 1:
                continue

            key = (matched_text, label, match.start())
            if key in seen:
                continue
            seen.add(key)

            entities.append(
                Entity(
                    text=matched_text,
                    label=label,
                    start=match.start(),
                    end=match.start() + len(matched_text),
                    confidence=confidence,
                    metadata={"source": source_name},
                )
            )

    return entities


def _deduplicate_entities(entities: List[Entity], prefer_sources: Optional[List[str]] = None) -> List[Entity]:
    """去重重叠 span 的实体

    当两个实体 span 重叠时，保留更长的实体。
    等长时优先保留 prefer_sources 中的来源（如 hanlp > rule_supplement）。

    Args:
        entities: 实体列表
        prefer_sources: 优先来源列表（靠前的优先级更高）

    Returns:
        去重后的实体列表
    """
    if not entities:
        return []

    if prefer_sources is None:
        prefer_sources = ["hanlp", "spacy", "rule_supplement", "rule_based", "rule_fallback"]

    # 按优先级排序：长 span 优先，同长按来源优先级
    source_rank = {src: i for i, src in enumerate(prefer_sources)}

    def sort_key(e: Entity) -> Tuple[int, int]:
        span_len = e.end - e.start
        rank = source_rank.get(e.metadata.get("source", "") if e.metadata else "", len(prefer_sources))
        return (-span_len, rank)

    entities_sorted = sorted(entities, key=sort_key)
    kept: List[Entity] = []

    for entity in entities_sorted:
        entity_start = entity.start
        entity_end = entity.end
        overlaps = False
        for existing in kept:
            if entity_start < existing.end and entity_end > existing.start:
                overlaps = True
                break
        if not overlaps:
            kept.append(entity)

    return kept


# =====================================================
# Entity 数据模型
# =====================================================


class Entity(BaseModel):
    """实体模型"""

    text: str = Field(..., description="实体文本")
    label: str = Field(..., description="实体类型")
    start: int = Field(..., description="起始位置")
    end: int = Field(..., description="结束位置")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    metadata: Optional[Dict[str, str]] = Field(default=None, description="额外元数据")


# =====================================================
# 方案 1: 原有 NERExtractor（SpaCy + 规则）—— 保持向后兼容
# =====================================================


class NERExtractor:
    """命名实体识别抽取器（SpaCy + 规则降级）

    使用 SpaCy 进行实体识别，支持中文和英文，
    提供自定义实体类型扩展能力。
    当 SpaCy 不可用时，自动降级到基于规则的实体抽取。
    """

    def __init__(self, model_name: str = "zh_core_web_sm"):
        """初始化 NER 抽取器

        Args:
            model_name: SpaCy 模型名称，默认为中文模型
        """
        self.model_name = model_name
        self.nlp = self._load_model()
        self.custom_entity_types = self._init_custom_entity_types()

    def _load_model(self) -> Any:
        """加载 SpaCy 模型，失败时返回 None"""
        if not SPACY_AVAILABLE:
            logger.warning("SpaCy 不可用，将使用基于规则的实体抽取")
            return None

        try:
            return spacy.load(self.model_name)
        except OSError:
            logger.warning(f"模型 {self.model_name} 未找到，将使用基于规则的实体抽取")
            return None

    def _init_custom_entity_types(self) -> Dict[str, str]:
        """初始化自定义实体类型映射"""
        return {
            "PRODUCT": "产品",
            "EVENT": "事件",
            "WORK_OF_ART": "艺术作品",
            "LAW": "法律",
            "LANGUAGE": "语言",
            "DATE": "日期",
            "TIME": "时间",
            "PERCENT": "百分比",
            "MONEY": "货币",
            "QUANTITY": "数量",
            "ORDINAL": "序数",
            "CARDINAL": "基数",
        }

    def extract_entities(self, text: str, entities_filter: Optional[List[str]] = None) -> List[Entity]:
        """从文本中抽取实体

        Args:
            text: 输入文本
            entities_filter: 实体类型过滤器，如果指定则只返回这些类型的实体

        Returns:
            实体列表
        """
        if not text or not text.strip():
            return []

        if self.nlp is None:
            return self._rule_based_extract(text, entities_filter)

        try:
            doc = self.nlp(text)
            entities = []

            for ent in doc.ents:
                if entities_filter and ent.label_ not in entities_filter:
                    continue

                entity = Entity(
                    text=ent.text,
                    label=ent.label_,
                    start=ent.start_char,
                    end=ent.end_char,
                    confidence=1.0,
                    metadata={"source": "spacy"},
                )
                entities.append(entity)

            logger.info(f"从文本中抽取了 {len(entities)} 个实体")
            return entities

        except Exception as e:
            logger.error(f"实体抽取失败: {str(e)}")
            return self._rule_based_extract(text, entities_filter)

    def _rule_based_extract(self, text: str, entities_filter: Optional[List[str]] = None) -> List[Entity]:
        """基于规则的实体抽取（降级方案）"""
        entities = _apply_rule_patterns(text, _FULL_RULE_PATTERNS, entities_filter, "rule_based", 0.7)
        logger.info(f"基于规则抽取了 {len(entities)} 个实体")
        return entities

    def extract_with_custom_types(
        self, text: str, custom_patterns: Optional[Dict[str, List[Dict]]] = None
    ) -> List[Entity]:
        """使用自定义模式抽取实体"""
        entities = self.extract_entities(text)

        if custom_patterns:
            for entity_type, patterns in custom_patterns.items():
                for pattern_config in patterns:
                    pattern = pattern_config.get("pattern")
                    if pattern:
                        for match in re.finditer(pattern, text):
                            entity = Entity(
                                text=match.group(),
                                label=entity_type,
                                start=match.start(),
                                end=match.end(),
                                confidence=0.9,
                                metadata={"source": "custom_pattern"},
                            )
                            entities.append(entity)

        return entities

    def get_entity_types(self) -> List[str]:
        """获取所有可用的实体类型"""
        if hasattr(self.nlp, "pipe_labels"):
            return list(self.nlp.pipe_labels.get("ner", []))
        return []

    def batch_extract(self, texts: List[str], entities_filter: Optional[List[str]] = None) -> List[List[Entity]]:
        """批量抽取实体"""
        if not texts:
            return []

        if self.nlp is None:
            return [self._rule_based_extract(text, entities_filter) for text in texts]

        try:
            results = []
            for doc in self.nlp.pipe(texts):
                entities = []
                for ent in doc.ents:
                    if entities_filter and ent.label_ not in entities_filter:
                        continue

                    entity = Entity(
                        text=ent.text,
                        label=ent.label_,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=1.0,
                        metadata={"source": "spacy"},
                    )
                    entities.append(entity)
                results.append(entities)

            logger.info(f"批量抽取完成，共处理 {len(texts)} 个文本")
            return results

        except Exception as e:
            logger.error(f"批量实体抽取失败: {str(e)}")
            return [self._rule_based_extract(text, entities_filter) for text in texts]

    def add_custom_entity_ruler(self, patterns: List[Dict[str, str]]):
        """添加自定义实体规则"""
        try:
            ruler = self.nlp.add_pipe("entity_ruler", before="ner")
            ruler.add_patterns(patterns)
            logger.info(f"添加了 {len(patterns)} 个自定义实体模式")
        except Exception as e:
            logger.error(f"添加自定义实体规则失败: {str(e)}")

    def get_entity_stats(self, entities: List[Entity]) -> Dict[str, int]:
        """获取实体统计信息"""
        stats: Dict[str, int] = {}
        for entity in entities:
            stats[entity.label] = stats.get(entity.label, 0) + 1
        return stats


# =====================================================
# 方案 2: HanLPNERExtractor（HanLP + 规则补充）
# =====================================================


class HanLPNERExtractor:
    """基于 HanLP 的命名实体识别抽取器

    使用 HanLP 的中文 NER 模型（MSRA ELECTRA Small），
    对中文人名/地名/机构名的识别准确率远超 SpaCy zh_core_web_sm。
    对日期/金钱/百分比等补充规则抽取。
    当 HanLP 不可用时自动降级到规则。

    模型规格:
        - Tokenizer: COARSE_ELECTRA_SMALL_ZH
        - NER: MSRA_NER_ELECTRA_SMALL_ZH
        - 实体类型: PERSON / ORG / LOC（+ 规则的 DATE/MONEY/PERCENT/QUANTITY 等）
    """

    # HanLP MSRA 标签 → 标准标签
    LABEL_MAPPING: Dict[str, str] = {
        "PERSON": "PERSON",
        "ORGANIZATION": "ORG",
        "ORG": "ORG",
        "LOCATION": "GPE",
        "LOC": "GPE",
        "GPE": "GPE",
        "DATE": "DATE",
        "TIME": "TIME",
        "MONEY": "MONEY",
        "NR": "PERSON",
        "NS": "GPE",
        "NT": "ORG",
    }

    def __init__(self):
        """初始化 HanLP 抽取器，延迟加载模型"""
        self._tokenizer: Any = None
        self._recognizer: Any = None
        self._loaded: bool = False
        self._load_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """HanLP 是否可用"""
        self._ensure_loaded()
        return self._loaded and self._tokenizer is not None and self._recognizer is not None

    @property
    def load_error(self) -> Optional[str]:
        """加载失败原因（调试用）"""
        self._ensure_loaded()
        return self._load_error

    def _ensure_loaded(self):
        """延迟加载模型（仅首次调用时触发）"""
        if self._loaded:
            return
        self._loaded = True

        if not HANLP_AVAILABLE:
            self._load_error = "HanLP not installed"
            return

        try:
            self._tokenizer = _hanlp_lib.load(_hanlp_lib.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)
            self._recognizer = _hanlp_lib.load(_hanlp_lib.pretrained.ner.MSRA_NER_ELECTRA_SMALL_ZH)
            logger.info("HanLP 模型加载成功（COARSE_ELECTRA_SMALL_ZH + MSRA_NER_ELECTRA_SMALL_ZH）")
        except Exception as e:
            self._load_error = str(e)
            logger.warning(f"HanLP 模型加载失败，将降级到规则: {e}")

    def extract_entities(self, text: str, entities_filter: Optional[List[str]] = None) -> List[Entity]:
        """从文本中抽取实体

        Args:
            text: 输入文本
            entities_filter: 实体类型过滤器

        Returns:
            实体列表
        """
        if not text or not text.strip():
            return []

        if not self.is_available:
            logger.debug(f"HanLP 不可用（{self._load_error}），使用规则抽取")
            return _apply_rule_patterns(text, _FULL_RULE_PATTERNS, entities_filter, "rule_fallback", 0.7)

        try:
            entities: List[Entity] = []
            seen: Set[Tuple[str, str, int]] = set()

            # 1. HanLP 分词 + NER
            tokens = self._tokenizer(text)
            ner_results: List[Tuple[str, str, int, int]] = self._recognizer(tokens)

            # 计算每个 token 在原文中的字符偏移
            char_offsets = self._compute_char_offsets(text, tokens)

            for entity_text, entity_type, start_token, end_token in ner_results:
                label = self.LABEL_MAPPING.get(entity_type, entity_type)

                if entities_filter and label not in entities_filter:
                    continue

                # 根据 token 索引计算字符位置
                char_start = char_offsets[start_token]
                char_end = char_offsets[end_token] if end_token < len(char_offsets) else len(text)

                # 后处理：单字人名前有"小/老/阿"前缀时扩展实体
                # 例如 HanLP 词条"小"+"张"→NER 只识别"张"为 PERSON，应扩展为"小张"
                if label == "PERSON" and len(entity_text) == 1 and char_start > 0:
                    prefix = text[char_start - 1]
                    if prefix in ("小", "老", "阿"):
                        entity_text = prefix + entity_text
                        char_start -= 1

                key = (entity_text, label, char_start)
                if key in seen:
                    continue
                seen.add(key)

                entities.append(
                    Entity(
                        text=entity_text,
                        label=label,
                        start=char_start,
                        end=char_end,
                        confidence=0.95,
                        metadata={"source": "hanlp"},
                    )
                )

            # 2. 规则补充（TECHNOLOGY/PRODUCT/DATE/MONEY/PERCENT 等 HanLP 不覆盖的类型）
            rule_entities = _apply_rule_patterns(text, _SUPPLEMENT_PATTERNS, entities_filter, "rule_supplement", 0.85)
            for re_entity in rule_entities:
                key = (re_entity.text, re_entity.label, re_entity.start)
                if key not in seen:
                    seen.add(key)
                    entities.append(re_entity)

            # 3. 去重重叠 span（如 "2023年" 与 "2023年第三季度"）
            entities = _deduplicate_entities(entities)

            logger.info(f"HanLP 抽取了 {len(entities)} 个实体")
            return entities

        except Exception as e:
            logger.error(f"HanLP 实体抽取失败: {e}", exc_info=True)
            return _apply_rule_patterns(text, _FULL_RULE_PATTERNS, entities_filter, "rule_fallback", 0.7)

    @staticmethod
    def _compute_char_offsets(text: str, tokens: List[str]) -> List[int]:
        """计算每个 token 在原文中的起始字符位置

        由于 HanLP 的分词会合并/处理字符，用贪心匹配方式对齐。
        """
        offsets: List[int] = []
        pos = 0
        for token in tokens:
            # 跳过原文中的空白
            while pos < len(text) and text[pos].isspace():
                pos += 1
            offsets.append(pos)
            pos += len(token)
        return offsets

    def batch_extract(self, texts: List[str], entities_filter: Optional[List[str]] = None) -> List[List[Entity]]:
        """批量抽取实体

        Args:
            texts: 文本列表
            entities_filter: 实体类型过滤器

        Returns:
            每个文本对应的实体列表
        """
        if not texts:
            return []
        return [self.extract_entities(t, entities_filter) for t in texts]

    def get_entity_types(self) -> List[str]:
        """获取所有可用的实体类型"""
        return list(self.LABEL_MAPPING.values()) + ["DATE", "TIME", "MONEY", "PERCENT", "QUANTITY"]

    def get_entity_stats(self, entities: List[Entity]) -> Dict[str, int]:
        """获取实体统计信息"""
        stats: Dict[str, int] = {}
        for entity in entities:
            stats[entity.label] = stats.get(entity.label, 0) + 1
        return stats


# =====================================================
# 方案 3: HybridNERExtractor（HanLP > SpaCy > 规则）—— 推荐默认方案
# =====================================================


class HybridNERExtractor:
    """混合 NER 抽取器

    抽取链路:
        1. HanLP（MSRA ELECTRA Small）—— 中文 NER 首选，准确率最高
        2. SpaCy zh_core_web_sm      —— HanLP 不可用时的备选
        3. 规则引擎                    —— 最终降级方案

    用法:
        extractor = HybridNERExtractor()
        entities = extractor.extract_entities("小王2024年毕业于北京大学")
        # → [Entity("小王", PERSON), Entity("2024年", DATE), Entity("北京大学", ORG)]
    """

    def __init__(self, spacy_model: str = "zh_core_web_sm"):
        """初始化混合抽取器

        Args:
            spacy_model: SpaCy 模型名称（作为 HanLP 不可用时的备选）
        """
        self._hanlp: Optional[HanLPNERExtractor] = None
        self._spacy: Optional[NERExtractor] = None
        self._spacy_model = spacy_model

    @property
    def hanlp(self) -> HanLPNERExtractor:
        """获取 HanLP 实例（延迟加载）"""
        if self._hanlp is None:
            self._hanlp = HanLPNERExtractor()
        return self._hanlp

    @property
    def spacy(self) -> NERExtractor:
        """获取 SpaCy 实例（延迟加载）"""
        if self._spacy is None:
            self._spacy = NERExtractor(self._spacy_model)
        return self._spacy

    def extract_entities(self, text: str, entities_filter: Optional[List[str]] = None) -> List[Entity]:
        """从文本中抽取实体

        链路: HanLP → SpaCy → 规则引擎

        Args:
            text: 输入文本
            entities_filter: 实体类型过滤器

        Returns:
            实体列表
        """
        if not text or not text.strip():
            return []

        # Layer 1: HanLP
        if self.hanlp.is_available:
            try:
                return self.hanlp.extract_entities(text, entities_filter)
            except Exception as e:
                logger.warning(f"HanLP 抽取失败，回退到 SpaCy: {e}")

        # Layer 2: SpaCy
        try:
            result = self.spacy.extract_entities(text, entities_filter)
            if result:
                return result
        except Exception as e:
            logger.warning(f"SpaCy 抽取失败，回退到规则: {e}")

        # Layer 3: 规则（最终降级）
        logger.warning("所有 NER 模型均不可用，使用规则引擎")
        return _apply_rule_patterns(text, _FULL_RULE_PATTERNS, entities_filter, "rule_final_fallback", 0.65)

    def batch_extract(self, texts: List[str], entities_filter: Optional[List[str]] = None) -> List[List[Entity]]:
        """批量抽取实体"""
        if not texts:
            return []

        if self.hanlp.is_available:
            try:
                return self.hanlp.batch_extract(texts, entities_filter)
            except Exception as e:
                logger.warning(f"HanLP 批量抽取失败，回退到 SpaCy: {e}")

        try:
            return self.spacy.batch_extract(texts, entities_filter)
        except Exception as e:
            logger.warning(f"SpaCy 批量抽取失败，回退到规则: {e}")

        return [
            _apply_rule_patterns(t, _FULL_RULE_PATTERNS, entities_filter, "rule_final_fallback", 0.65) for t in texts
        ]

    def get_entity_types(self) -> List[str]:
        """获取所有可用的实体类型"""
        if self._hanlp is not None and self.hanlp.is_available:
            return self.hanlp.get_entity_types()
        return self.spacy.get_entity_types()

    def get_entity_stats(self, entities: List[Entity]) -> Dict[str, int]:
        """获取实体统计信息"""
        stats: Dict[str, int] = {}
        for entity in entities:
            stats[entity.label] = stats.get(entity.label, 0) + 1
        return stats
