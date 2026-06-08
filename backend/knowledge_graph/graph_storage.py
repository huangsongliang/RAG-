"""图谱存储模块 - Neo4j 连接器封装和图谱 CRUD 操作（含内存降级存储）"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class Node(BaseModel):
    """节点模型"""

    id: Optional[str] = Field(default=None, description="节点 ID")
    label: str = Field(..., description="节点标签")
    properties: Dict[str, str] = Field(default_factory=dict, description="节点属性")
    metadata: Optional[Dict[str, str]] = Field(default=None, description="额外元数据")


class Edge(BaseModel):
    """边模型"""

    source_id: str = Field(..., description="源节点 ID")
    target_id: str = Field(..., description="目标节点 ID")
    relation_type: str = Field(..., description="关系类型")
    properties: Dict[str, str] = Field(default_factory=dict, description="边属性")
    metadata: Optional[Dict[str, str]] = Field(default=None, description="额外元数据")


class GraphStorage:
    """图谱存储管理

    封装 Neo4j 连接器，提供节点和边的 CRUD 操作，
    支持批量操作和事务管理。
    当 Neo4j 不可用时，自动降级为内存存储（mock 模式）。
    """

    def __init__(self, uri: str = "bolt://localhost:7687", username: str = "neo4j", password: str = "password"):
        """初始化图谱存储

        Args:
            uri: Neo4j 连接 URI
            username: Neo4j 用户名
            password: Neo4j 密码
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.driver = None
        # 内存存储（mock 模式用）
        self._mock_nodes: Dict[str, Node] = {}
        self._mock_edges: List[Edge] = []
        self._connect()

    def _connect(self):
        """建立 Neo4j 连接"""
        try:
            from neo4j import GraphDatabase

            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            logger.info(f"成功连接到 Neo4j: {self.uri}")
        except ImportError:
            logger.warning("neo4j 驱动未安装，图谱功能将使用模拟模式")
            self.driver = None
        except Exception as e:
            logger.error(f"连接 Neo4j 失败: {str(e)}")
            self.driver = None

    def close(self):
        """关闭 Neo4j 连接"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j 连接已关闭")

    def create_node(self, node: Node) -> Optional[str]:
        """创建节点

        Args:
            node: 节点对象

        Returns:
            节点 ID
        """
        if not self.driver:
            return self._mock_create_node(node)

        try:
            with self.driver.session() as session:
                query = f"CREATE (n:{node.label} $props) RETURN id(n) as node_id"
                result = session.run(query, props=node.properties)
                record = result.single()
                node_id = str(record["node_id"]) if record else None
                logger.info(f"创建节点成功: {node_id}")
                return node_id
        except Exception as e:
            logger.error(f"创建节点失败: {str(e)}")
            return None

    def _mock_create_node(self, node: Node) -> Optional[str]:
        """内存存储创建节点"""
        import uuid

        node_id = str(uuid.uuid4())
        node.id = node_id
        self._mock_nodes[node_id] = Node(
            id=node_id,
            label=node.label,
            properties=node.properties,
        )
        logger.debug(f"内存存储创建节点: {node_id} [{node.label}] {node.properties.get('text', '')}")
        return node_id

    def create_nodes_batch(self, nodes: List[Node]) -> List[Optional[str]]:
        """批量创建节点

        Args:
            nodes: 节点列表

        Returns:
            节点 ID 列表
        """
        if not self.driver:
            return [self._mock_create_node(node) for node in nodes]

        node_ids = []
        with self.driver.session() as session:
            with session.begin_transaction() as tx:
                for node in nodes:
                    query = f"CREATE (n:{node.label} $props) RETURN id(n) as node_id"
                    result = tx.run(query, props=node.properties)
                    record = result.single()
                    node_id = str(record["node_id"]) if record else None
                    node_ids.append(node_id)

        logger.info(f"批量创建节点完成: {len(node_ids)} 个")
        return node_ids

    def create_edge(self, edge: Edge) -> bool:
        """创建边

        Args:
            edge: 边对象

        Returns:
            是否成功
        """
        if not self.driver:
            return self._mock_create_edge(edge)

        try:
            with self.driver.session() as session:
                query = (
                    """
                MATCH (source), (target)
                WHERE id(source) = $source_id AND id(target) = $target_id
                CREATE (source)-[r:%s $props]->(target)
                RETURN r
                """
                    % edge.relation_type
                )

                result = session.run(
                    query,
                    source_id=int(edge.source_id),
                    target_id=int(edge.target_id),
                    props=edge.properties,
                )
                success = result.single() is not None
                logger.info(f"创建边成功: {edge.relation_type}")
                return success
        except Exception as e:
            logger.error(f"创建边失败: {str(e)}")
            return False

    def _mock_create_edge(self, edge: Edge) -> bool:
        """内存存储创建边"""
        # 检查源/目标节点是否存在
        if edge.source_id not in self._mock_nodes or edge.target_id not in self._mock_nodes:
            logger.warning(f"边的端点不存在: {edge.source_id} -> {edge.target_id}")
            return False
        self._mock_edges.append(
            Edge(
                source_id=edge.source_id,
                target_id=edge.target_id,
                relation_type=edge.relation_type,
                properties=edge.properties,
            )
        )
        logger.debug(f"内存存储创建边: {edge.relation_type}")
        return True

    def create_edges_batch(self, edges: List[Edge]) -> List[bool]:
        """批量创建边

        Args:
            edges: 边列表

        Returns:
            创建结果列表
        """
        results = []
        for edge in edges:
            results.append(self.create_edge(edge))

        logger.info(f"批量创建边完成: {sum(results)}/{len(edges)} 个成功")
        return results

    def get_node(self, node_id: str) -> Optional[Node]:
        """获取节点

        Args:
            node_id: 节点 ID

        Returns:
            节点对象
        """
        if not self.driver:
            return self._mock_get_node(node_id)

        try:
            with self.driver.session() as session:
                query = "MATCH (n) WHERE id(n) = $node_id RETURN labels(n) as labels, properties(n) as props"
                result = session.run(query, node_id=int(node_id))
                record = result.single()

                if record:
                    label = record["labels"][0] if record["labels"] else "Unknown"
                    return Node(id=node_id, label=label, properties=record["props"])

                return None
        except Exception as e:
            logger.error(f"获取节点失败: {str(e)}")
            return None

    def _mock_get_node(self, node_id: str) -> Optional[Node]:
        """内存存储获取节点"""
        return self._mock_nodes.get(node_id)

    def update_node(self, node_id: str, properties: Dict[str, str]) -> bool:
        """更新节点属性

        Args:
            node_id: 节点 ID
            properties: 要更新的属性

        Returns:
            是否成功
        """
        if not self.driver:
            if node_id in self._mock_nodes:
                self._mock_nodes[node_id].properties.update(properties)
                return True
            return False

        try:
            with self.driver.session() as session:
                query = "MATCH (n) WHERE id(n) = $node_id SET n += $props"
                session.run(query, node_id=int(node_id), props=properties)
                logger.info(f"更新节点成功: {node_id}")
                return True
        except Exception as e:
            logger.error(f"更新节点失败: {str(e)}")
            return False

    def delete_node(self, node_id: str) -> bool:
        """删除节点

        Args:
            node_id: 节点 ID

        Returns:
            是否成功
        """
        if not self.driver:
            if node_id in self._mock_nodes:
                del self._mock_nodes[node_id]
                # 级联删除相关边
                self._mock_edges = [e for e in self._mock_edges if e.source_id != node_id and e.target_id != node_id]
                return True
            return False

        try:
            with self.driver.session() as session:
                query = "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n"
                session.run(query, node_id=int(node_id))
                logger.info(f"删除节点成功: {node_id}")
                return True
        except Exception as e:
            logger.error(f"删除节点失败: {str(e)}")
            return False

    def delete_edge(self, source_id: str, target_id: str, relation_type: str) -> bool:
        """删除边

        Args:
            source_id: 源节点 ID
            target_id: 目标节点 ID
            relation_type: 关系类型

        Returns:
            是否成功
        """
        if not self.driver:
            before = len(self._mock_edges)
            self._mock_edges = [
                e
                for e in self._mock_edges
                if not (e.source_id == source_id and e.target_id == target_id and e.relation_type == relation_type)
            ]
            return len(self._mock_edges) < before

        try:
            with self.driver.session() as session:
                query = (
                    """
                MATCH (source)-[r:%s]->(target)
                WHERE id(source) = $source_id AND id(target) = $target_id
                DELETE r
                """
                    % relation_type
                )

                session.run(query, source_id=int(source_id), target_id=int(target_id))
                logger.info(f"删除边成功: {relation_type}")
                return True
        except Exception as e:
            logger.error(f"删除边失败: {str(e)}")
            return False

    def find_nodes_by_label(self, label: str, limit: int = 100) -> List[Node]:
        """根据标签查找节点

        Args:
            label: 节点标签
            limit: 返回数量限制

        Returns:
            节点列表
        """
        if not self.driver:
            return [n for n in list(self._mock_nodes.values())[:limit] if n.label == label]

        try:
            with self.driver.session() as session:
                query = f"MATCH (n:{label}) RETURN id(n) as node_id, properties(n) as props LIMIT $limit"
                result = session.run(query, limit=limit)

                nodes = []
                for record in result:
                    nodes.append(Node(id=str(record["node_id"]), label=label, properties=record["props"]))

                return nodes
        except Exception as e:
            logger.error(f"查找节点失败: {str(e)}")
            return []

    def find_nodes_by_property(self, label: str, property_key: str, property_value: str) -> List[Node]:
        """根据属性查找节点

        Args:
            label: 节点标签
            property_key: 属性键
            property_value: 属性值

        Returns:
            节点列表
        """
        if not self.driver:
            return [
                n
                for n in self._mock_nodes.values()
                if n.label == label and n.properties.get(property_key) == property_value
            ]

        try:
            with self.driver.session() as session:
                query = f"""
                MATCH (n:{label})
                WHERE n.`{property_key}` = $value
                RETURN id(n) as node_id, properties(n) as props
                """
                result = session.run(query, value=property_value)

                nodes = []
                for record in result:
                    nodes.append(Node(id=str(record["node_id"]), label=label, properties=record["props"]))

                return nodes
        except Exception as e:
            logger.error(f"根据属性查找节点失败: {str(e)}")
            return []

    def get_graph_stats(self) -> Dict[str, int]:
        """获取图谱统计信息

        Returns:
            统计信息字典
        """
        if not self.driver:
            entity_types: Dict[str, int] = {}
            for n in self._mock_nodes.values():
                entity_types[n.label] = entity_types.get(n.label, 0) + 1
            relation_types: Dict[str, int] = {}
            for e in self._mock_edges:
                relation_types[e.relation_type] = relation_types.get(e.relation_type, 0) + 1
            return {
                "nodes": len(self._mock_nodes),
                "edges": len(self._mock_edges),
                "entity_types": entity_types,
                "relation_types": relation_types,
            }

        try:
            with self.driver.session() as session:
                node_count_result = session.run("MATCH (n) RETURN count(n) as count")
                node_count = node_count_result.single()["count"]

                edge_count_result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                edge_count = edge_count_result.single()["count"]

                return {"nodes": node_count, "edges": edge_count}
        except Exception as e:
            logger.error(f"获取图谱统计失败: {str(e)}")
            return {"nodes": 0, "edges": 0}

    def clear_graph(self) -> bool:
        """清空图谱

        Returns:
            是否成功
        """
        if not self.driver:
            self._mock_nodes.clear()
            self._mock_edges.clear()
            logger.info("内存存储图谱已清空")
            return True

        try:
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                logger.info("图谱已清空")
                return True
        except Exception as e:
            logger.error(f"清空图谱失败: {str(e)}")
            return False
