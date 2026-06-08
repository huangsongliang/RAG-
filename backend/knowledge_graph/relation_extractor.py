"""关系抽取模块 - 基于规则和 LLM 的关系抽取"""

import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from backend.generator import get_async_llm
from backend.knowledge_graph.ner_extractor import Entity
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# 中文标点符号（需要从前缀中清除）
_CHINESE_PUNCTUATION = "，。！？；：、（）【】《》\"\"''…—～,.;:!?"


def _clean_entity_text(text: str) -> str:
    """清洗捕获的实体文本：去除前后标点和空白"""
    return text.strip().strip(_CHINESE_PUNCTUATION)


class Relation(BaseModel):
    """关系模型"""

    source: str = Field(..., description="源实体文本")
    source_type: str = Field(..., description="源实体类型")
    target: str = Field(..., description="目标实体文本")
    target_type: str = Field(..., description="目标实体类型")
    relation_type: str = Field(..., description="关系类型")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    context: Optional[str] = Field(default=None, description="关系上下文")
    metadata: Optional[Dict[str, str]] = Field(default=None, description="额外元数据")


class RelationExtractor:
    """关系抽取器

    结合基于规则的方法和 LLM 进行关系抽取，
    支持自定义关系类型和规则配置。
    """

    def __init__(self):
        """初始化关系抽取器"""
        self.rule_patterns = self._init_rule_patterns()
        self.relation_templates = self._init_relation_templates()

    def _init_rule_patterns(self) -> Dict[str, List[str]]:
        """初始化基于规则的关系模式

        所有模式设计为恰好 2 个捕获组（source, target），
        动词/连词/后缀统一用非捕获组 (?:...)。
        目标实体用 [\u4e00-\u9fa5a-zA-Z]+ 限定词字符范围，避免贪婪跨越标点。
        复杂语义由 LLM 兜底。
        """
        # 中文词字符（含英文/数字，不含标点空白）
        E = r"[\u4e00-\u9fa5a-zA-Z0-9]+"
        return {
            "工作于": [
                rf"(.+?)(?:在|于|就职于|工作于|任职于)({E})",
                rf"(.+?)是({E})(?:公司|企业|机构|组织)的",
            ],
            "位于": [
                rf"(.+?)位于({E})",
                rf"(.+?)坐落于({E})",
            ],
            "创作": [
                rf"(.+?)(?:创作|编写|著|著作|编写)了?({E})",
                rf"(.+?)是({E})(?:著|编写|创作)的",
            ],
            "属于": [
                rf"(.+?)(?:属于|隶属于)({E})",
                rf"(.+?)是({E})的一部分",
            ],
            "合作": [
                rf"(.+?)(?:与|和)({E})(?:合作|协作|搭档|共同)",
                rf"(.+?)与({E})(?:合作|协作)",
            ],
            "研发": [
                rf"(.+?)(?:研发|开发|研制|设计)了?({E})",
                rf"(.+?)由({E})研发",
            ],
            "发布": [
                rf"(.+?)(?:发布|推出|上线)了?({E})",
                rf"(.+?)于({E})(?:发布|推出|上线)",
            ],
            "使用": [
                rf"(.+?)(?:使用|采用|运用)了?({E})",
                rf"(.+?)基于({E})",
            ],
            "毕业": [
                rf"(.+?)(?:毕业于|毕业自|就读于|就学于)({E})",
            ],
            "亲属关系": [
                # --- "X和/与Y是关系" 模式 ---
                rf"({E})和({E})(?:是|为)(?:兄弟|姐妹|夫妻|夫妇|父子|母子|父女|母女|兄妹|姐弟|姐俩|哥俩|亲戚|亲属|一家人|长辈|晚辈|连襟|妯娌)",
                rf"({E})与({E})(?:是|为)(?:兄弟|姐妹|夫妻|夫妇|父子|母子|父女|母女|兄妹|姐弟|姐俩|哥俩|亲戚|亲属|一家人|长辈|晚辈|连襟|妯娌)",
                # --- "X是Y的亲属称谓" 模式（最常用） ---
                rf"({E})是({E})(?:的)(?:爸爸|妈妈|父亲|母亲|儿子|女儿|哥哥|姐姐|弟弟|妹妹|丈夫|妻子|老公|老婆|爱人|孩子|小孩|子女|双亲|家长)",
                rf"({E})是({E})(?:的)(?:爷爷|奶奶|外公|外婆|孙子|孙女|外孙|外孙女|叔叔|阿姨|伯伯|伯父|伯母|舅舅|舅妈|姑姑|姑父|姨妈|姨父|堂兄|堂弟|堂姐|堂妹|表兄|表弟|表姐|表妹)",
                rf"({E})是({E})(?:的)(?:岳父|岳母|婆婆|公公|女婿|儿媳|嫂子|姐夫|妹夫|弟媳|嫂嫂|小叔|小姑|大伯|大姑|小舅子|小姨子|连襟|妯娌|亲家|干爹|干妈|干儿子|干女儿)",
                rf"({E})是({E})(?:的)(?:亲属|亲戚|家属|亲人|家人|后代|祖先|先辈|后辈|亲戚|远亲|近亲)",
                # --- "X的亲属称谓Y" 模式（紧凑型，无"是"） ---
                rf"({E})(?:的)(?:爸爸|妈妈|父亲|母亲|儿子|女儿|哥哥|姐姐|弟弟|妹妹|丈夫|妻子|老公|老婆|爱人)({E})",
                # --- "X的亲属称谓是Y" 模式 ---
                rf"({E})(?:的)(?:爸爸|妈妈|父亲|母亲|儿子|女儿|哥哥|姐姐|弟弟|妹妹|丈夫|妻子|老公|老婆|爱人)是({E})",
                rf"({E})(?:的)(?:爷爷|奶奶|外公|外婆|孙子|孙女|外孙|外孙女|叔叔|阿姨|伯伯|伯父|伯母|舅舅|舅妈|姑姑|姑父|姨妈|姨父)是({E})",
                rf"({E})(?:的)(?:岳父|岳母|婆婆|公公|女婿|儿媳|嫂子|姐夫|妹夫|弟媳)是({E})",
                # --- 代词消解：他们/两人是亲属 ---
                rf"({E})和({E})，?(?:他们|两人|二者|双方|彼此)(?:是|为)(?:兄弟|姐妹|夫妻|夫妇|父子|母子|父女|母女|兄妹|姐弟)",
            ],
            "共同特征": [
                rf"(.+?)和(.+?)有共同({E})",
            ],
        }

    def _init_relation_templates(self) -> Dict[str, str]:
        """初始化关系模板，用于 LLM 关系抽取"""
        return {
            "prompt": """从以下文本中抽取实体之间的关系。

文本: {text}

已识别的实体:
{entities}

请以 JSON 格式返回关系列表，格式如下:
{{
    "relations": [
        {{
            "source": "源实体",
            "source_type": "源实体类型",
            "target": "目标实体",
            "target_type": "目标实体类型",
            "relation_type": "关系类型",
            "confidence": 0.9,
            "context": "关系所在上下文"
        }}
    ]
}}

关系类型包括但不限于:
- **亲属关系**: 父子、母子、父女、母女、夫妻、兄弟、姐妹、兄妹、姐弟、爷孙、祖孙、叔侄、姑侄、舅甥、姨甥、堂亲、表亲、岳婿、婆媳、连襟、妯娌等
- **工作于**: 在某公司/机构任职
- **位于**: 地理位置关系
- **毕业**: 毕业于某学校
- **共同特征**: 有共同属性
- **创作**: 创作/编写了某作品
- **属于**: 隶属/归属关系
- **合作**: 协作/搭档关系
- **研发**: 研发/开发了某产品
- **发布**: 发布/推出了某产品
- **使用**: 使用/采用了某技术

请根据文本实际语义自由判断关系类型。

**重要提示**:
1. **代词消解**: 如果出现"他们是兄弟"、"他们是夫妻"、"两人是父子"等，请将代词"他们/两人/二者"还原为文本中已识别的具体人名实体
2. **亲属表述识别**: 中文亲属有多种表述方式，请识别以下模式:
   - "X是Y的爸爸/妈妈/儿子/女儿/哥哥..." → X是亲属关系中长辈/晚辈，Y是参照点
   - "X的父亲/母亲/儿子/女儿是Y" → X与Y有亲属关系
   - "X和Y是兄弟/夫妻/父子..." → X与Y直接是某种亲属
   - 请从整体语义判断具体亲属类型（父子/母子/夫妻/兄弟等），不要笼统标注为"亲属关系"
3. 一个实体可以参与多个关系（如小明的父亲张伟，可能同时有[工作于]某公司和[亲属关系]）
4. 如果文本中不存在明显的关系，返回空列表
5. 只返回 JSON，不要包含其他解释性文本。""",
        }

    def _lookup_entity(self, text: str, entities: List[Entity]) -> Optional[Entity]:
        """实体查找：先精确匹配，再尝试模糊匹配（处理如'小张'→'张'的NER截断）"""
        # 精确匹配
        entity = next((e for e in entities if e.text == text), None)
        if entity:
            return entity
        # 模糊匹配：NER 把"小张"截断成"张" → 正则捕获"小张"，实体名为"张"
        for e in entities:
            if text.endswith(e.text) and text.startswith(("小", "老", "阿")) and len(text) <= len(e.text) + 2:
                logger.info(f"[RuleExtract] 模糊匹配: '{text}' → entity '{e.text}'")
                return e
        return None

    def _resolve_pronouns(self, text: str, entities: List[Entity]) -> str:
        """代词消解：将文本中的"他/她"替换为上下文中最新的 PERSON 实体

        例如: "小明是CEO，他的哥哥张强" → "小明是CEO，小明的哥哥张强"

        Args:
            text: 原始文本
            entities: 已抽取的实体列表

        Returns:
            消解代词后的文本
        """
        person_entities = sorted(
            [e for e in entities if e.label == "PERSON"],
            key=lambda e: e.start,
        )
        if not person_entities:
            return text

        result_parts: list[str] = []
        current_pos = 0
        for i, ch in enumerate(text):
            if ch in ("他", "她") and i > 0:
                prev_char = text[i - 1]
                if prev_char in "，。！？；：、的了他她它":
                    closest = None
                    for pe in person_entities:
                        if pe.end <= i:
                            closest = pe
                        else:
                            break
                    if closest:
                        result_parts.append(text[current_pos:i])
                        result_parts.append(closest.text)
                        current_pos = i + 1
        result_parts.append(text[current_pos:])
        resolved = "".join(result_parts)

        if resolved != text:
            logger.info(f"[PronounResolve] 代词消解: '{text[:60]}...' → '{resolved[:60]}...'")
        return resolved

    def extract_relations_with_rules(self, text: str, entities: List[Entity]) -> List[Relation]:
        """使用规则方法抽取关系

        Args:
            text: 输入文本
            entities: 实体列表

        Returns:
            关系列表
        """
        if not text or not entities:
            return []

        relations = []
        entity_texts = [e.text for e in entities]
        logger.info(f"[RuleExtract] 输入文本: {text[:100]}")
        logger.info(f"[RuleExtract] 实体列表: {entity_texts}")

        # 代词消解：把 "他的哥哥张强" 变成 "小明的哥哥张强"
        resolved_text = self._resolve_pronouns(text, entities)

        for relation_type, patterns in self.rule_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, resolved_text)
                for match in matches:
                    groups = match.groups()
                    logger.info(f"[RuleExtract] Pattern '{relation_type}' 匹配成功: groups={groups}")
                    if len(groups) >= 2:
                        source_text = _clean_entity_text(groups[0])
                        target_text = _clean_entity_text(groups[1])
                        if not source_text or not target_text:
                            continue
                        logger.info(
                            f"[RuleExtract] 尝试匹配: source='{source_text}' "
                            f"target='{target_text}' in {entity_texts}"
                        )

                        source_entity = self._lookup_entity(source_text, entities)
                        target_entity = self._lookup_entity(target_text, entities)

                        # 紧凑模式兜底：第二组捕获了多余文本时，用子串查找
                        # 例如 "X的哥哥张强是..." → group2="张强是..." → 子串匹配到"张强"
                        if source_entity and not target_entity:
                            for e in entities:
                                if e.text in target_text:
                                    target_entity = e
                                    logger.info(f"[RuleExtract] 子串兜底: '{target_text}' → '{e.text}'")
                                    break
                        if target_entity and not source_entity:
                            for e in entities:
                                if e.text in source_text:
                                    source_entity = e
                                    logger.info(f"[RuleExtract] 子串兜底: '{source_text}' → '{e.text}'")
                                    break

                        if source_entity and target_entity:
                            relation = Relation(
                                source=source_entity.text,
                                source_type=source_entity.label,
                                target=target_entity.text,
                                target_type=target_entity.label,
                                relation_type=relation_type,
                                confidence=0.85,
                                context=match.group(),
                                metadata={"source": "rule_based"},
                            )
                            relations.append(relation)
                            logger.info(
                                f"[RuleExtract] 关系建立: {source_entity.text} "
                                f"--[{relation_type}]--> {target_entity.text}"
                            )

        logger.info(f"[RuleExtract] 规则抽取完成，找到 {len(relations)} 个关系")
        return relations

    async def extract_relations_with_llm(self, text: str, entities: List[Entity]) -> List[Relation]:
        """使用 LLM 抽取关系

        Args:
            text: 输入文本
            entities: 实体列表

        Returns:
            关系列表
        """
        if not text or not entities:
            return []

        try:
            prompt = self.relation_templates["prompt"].format(
                text=text, entities="\n".join([f"- {e.text} ({e.label})" for e in entities])
            )

            llm = get_async_llm()
            response = await llm.async_generate(prompt, temperature=0.3)

            relations = self._parse_llm_response(response, text, entities)
            logger.info(f"LLM 抽取找到 {len(relations)} 个关系")
            return relations

        except Exception as e:
            logger.error(f"LLM 关系抽取失败: {str(e)}")
            return []

    def _parse_llm_response(self, response: str, original_text: str, entities: List[Entity]) -> List[Relation]:
        """解析 LLM 返回的关系

        Args:
            response: LLM 响应
            original_text: 原始文本
            entities: 实体列表

        Returns:
            关系列表
        """
        relations = []

        try:
            import json

            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                data = json.loads(json_match.group())
                relation_list = data.get("relations", [])

                for rel_data in relation_list:
                    source_text = rel_data.get("source", "")
                    target_text = rel_data.get("target", "")

                    source_entity = next((e for e in entities if e.text == source_text), None)
                    target_entity = next((e for e in entities if e.text == target_text), None)

                    if source_entity and target_entity:
                        relation = Relation(
                            source=source_text,
                            source_type=rel_data.get("source_type", source_entity.label),
                            target=target_text,
                            target_type=rel_data.get("target_type", target_entity.label),
                            relation_type=rel_data.get("relation_type", "相关"),
                            confidence=rel_data.get("confidence", 0.8),
                            context=rel_data.get("context"),
                            metadata={"source": "llm_based"},
                        )
                        relations.append(relation)

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"解析 LLM 响应失败: {str(e)}")

        return relations

    async def extract_relations_hybrid(self, text: str, entities: List[Entity], use_llm: bool = True) -> List[Relation]:
        """混合方法抽取关系

        先使用规则抽取，再使用 LLM 补充

        Args:
            text: 输入文本
            entities: 实体列表
            use_llm: 是否使用 LLM

        Returns:
            关系列表
        """
        rule_relations = self.extract_relations_with_rules(text, entities)

        if use_llm:
            llm_relations = await self.extract_relations_with_llm(text, entities)

            existing_relations = set()
            for rel in rule_relations:
                key = (rel.source, rel.target, rel.relation_type)
                existing_relations.add(key)

            for rel in llm_relations:
                key = (rel.source, rel.target, rel.relation_type)
                if key not in existing_relations:
                    rule_relations.append(rel)

        return rule_relations

    def get_relation_types(self) -> List[str]:
        """获取所有关系类型

        Returns:
            关系类型列表
        """
        return list(self.rule_patterns.keys())

    def add_custom_relation_pattern(self, relation_type: str, patterns: List[str]):
        """添加自定义关系模式

        Args:
            relation_type: 关系类型
            patterns: 正则表达式模式列表
        """
        if relation_type in self.rule_patterns:
            self.rule_patterns[relation_type].extend(patterns)
        else:
            self.rule_patterns[relation_type] = patterns

        logger.info(f"为关系类型 '{relation_type}' 添加了 {len(patterns)} 个模式")

    def batch_extract_relations(
        self, texts: List[str], entities_list: List[List[Entity]], use_llm: bool = False
    ) -> List[List[Relation]]:
        """批量抽取关系

        Args:
            texts: 文本列表
            entities_list: 实体列表列表
            use_llm: 是否使用 LLM

        Returns:
            每个文本对应的关系列表
        """
        if len(texts) != len(entities_list):
            logger.error("文本数量和实体列表数量不匹配")
            return []

        results = []
        for text, entities in zip(texts, entities_list):
            if use_llm:
                import asyncio

                relations = asyncio.run(self.extract_relations_hybrid(text, entities, use_llm=False))
            else:
                relations = self.extract_relations_with_rules(text, entities)
            results.append(relations)

        logger.info(f"批量关系抽取完成，共处理 {len(texts)} 个文本")
        return results
