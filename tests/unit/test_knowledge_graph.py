"""知识图谱模块单元测试"""

from backend.knowledge_graph.graph_query import GraphQuery
from backend.knowledge_graph.ner_extractor import NERExtractor, Entity
from backend.knowledge_graph.relation_extractor import Relation, RelationExtractor


class TestRelation:
    """Relation 模型测试"""

    def test_relation_creation(self):
        rel = Relation(
            source="张三",
            source_type="PERSON",
            target="北京",
            target_type="LOCATION",
            relation_type="LIVES_IN",
            confidence=0.9,
            context="张三住在北京",
        )
        assert rel.source == "张三"
        assert rel.target == "北京"
        assert rel.relation_type == "LIVES_IN"
        assert rel.confidence == 0.9
        assert rel.context == "张三住在北京"


def _make_person_entity(name: str) -> Entity:
    """快捷创建 PERSON 类型实体"""
    return Entity(text=name, label="PERSON", start=0, end=len(name), confidence=0.95)


class TestRelationExtractor:
    """RelationExtractor 测试"""

    def test_extractor_creation(self):
        extractor = RelationExtractor()
        assert extractor is not None
        assert isinstance(extractor.rule_patterns, dict)
        assert len(extractor.rule_patterns) > 0

    def test_rule_patterns_exist(self):
        extractor = RelationExtractor()
        assert "工作于" in extractor.rule_patterns
        assert "位于" in extractor.rule_patterns

    # ---------- 亲属关系：规则抽取测试 ----------

    def test_kinship_x_shi_y_de_baba(self):
        """X是Y的爸爸 → 亲属关系"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("张伟"), _make_person_entity("小明")]
        text = "张伟是小明的爸爸"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == "亲属关系"
        assert {relations[0].source, relations[0].target} == {"张伟", "小明"}

    def test_kinship_x_de_baba_shi_y(self):
        """X的爸爸是Y → 亲属关系"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("小明"), _make_person_entity("张伟")]
        text = "小明的爸爸是张伟"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == "亲属关系"
        assert {relations[0].source, relations[0].target} == {"小明", "张伟"}

    def test_kinship_x_he_y_shi_fuzi(self):
        """X和Y是父子 → 亲属关系"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("张伟"), _make_person_entity("小明")]
        text = "张伟和小明是父子"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == "亲属关系"

    def test_kinship_x_he_y_shi_fuqi(self):
        """X和Y是夫妻 → 亲属关系"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("张伟"), _make_person_entity("李丽")]
        text = "张伟和李丽是夫妻"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == "亲属关系"

    def test_kinship_x_shi_y_de_yeye(self):
        """X是Y的爷爷 → 亲属关系（爷孙关系）"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("张爷爷"), _make_person_entity("小张")]
        text = "张爷爷是小张的爷爷"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == "亲属关系"

    def test_kinship_x_shi_y_de_yuefu(self):
        """X是Y的岳父 → 亲属关系（姻亲关系）"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("老王"), _make_person_entity("小王")]
        text = "老王是小王的岳父"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == "亲属关系"

    def test_kinship_x_shi_y_de_tangxiong(self):
        """X是Y的堂兄 → 亲属关系（堂表亲）"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("张大明"), _make_person_entity("张小明")]
        text = "张大明是张小明的堂兄"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == "亲属关系"

    def test_kinship_x_shi_y_de_qinshu(self):
        """X是Y的亲属 → 亲属关系（泛指）"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("张三"), _make_person_entity("李四")]
        text = "张三是李四的亲属"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == "亲属关系"

    def test_kinship_no_entity_no_match(self):
        """没有 PERSON 实体时不应匹配亲属关系"""
        extractor = RelationExtractor()
        entities: list[Entity] = []  # type: ignore[var-annotated]
        text = "小明的爸爸是张伟"
        relations = extractor.extract_relations_with_rules(text, entities)
        assert len(relations) == 0

    def test_kinship_not_confused_with_gongtong_texing(self):
        """亲属关系不应被误识别为共同特征"""
        extractor = RelationExtractor()
        entities = [_make_person_entity("张伟"), _make_person_entity("小明")]
        text = "张伟和小明是父子"
        relations = extractor.extract_relations_with_rules(text, entities)
        # 必须是亲属关系，不能是共同特征
        kinship = [r for r in relations if r.relation_type == "亲属关系"]
        assert len(kinship) >= 1


class TestEntity:
    """Entity 模型测试"""

    def test_entity_creation(self):
        entity = Entity(
            text="张三",
            label="PERSON",
            start=0,
            end=2,
            confidence=0.95,
        )
        assert entity.text == "张三"
        assert entity.label == "PERSON"
        assert entity.confidence == 0.95


class TestNERExtractor:
    """NERExtractor 测试"""

    def test_extractor_creation(self):
        extractor = NERExtractor()
        assert extractor is not None

    def test_extract_entities_empty_text(self):
        extractor = NERExtractor()
        results = extractor.extract_entities("")
        assert results == []

    def test_extract_entities_basic(self):
        extractor = NERExtractor()
        text = "张三和李四在北京见面。"
        results = extractor.extract_entities(text)
        assert isinstance(results, list)


class TestGraphQuery:
    """GraphQuery 测试"""

    def test_query_creation(self):
        query = GraphQuery()
        assert query is not None

    def test_find_neighbors_no_storage(self):
        query = GraphQuery()
        neighbors = query.find_neighbors("test_node")
        assert isinstance(neighbors, dict)

    def test_find_path_no_storage(self):
        query = GraphQuery()
        path = query.find_path("node_a", "node_b")
        assert isinstance(path, list)
