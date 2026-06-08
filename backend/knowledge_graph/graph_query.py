"""图谱查询模块 - 提供路径查询、邻居查询、子图查询和图谱增强检索"""

from typing import Dict, List, Optional, Set

from backend.knowledge_graph.graph_storage import GraphStorage, Node
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class GraphQuery:
    """图谱查询引擎

    提供复杂的图谱查询功能，包括路径查询、
    邻居查询、子图查询和增强检索能力。
    """

    def __init__(self, storage: Optional[GraphStorage] = None):
        """初始化图谱查询引擎

        Args:
            storage: 图谱存储实例
        """
        self.storage = storage or GraphStorage()

    def find_neighbors(
        self, node_id: str, depth: int = 1, relation_type: Optional[str] = None
    ) -> Dict[str, List[Node]]:
        """查找节点的邻居

        Args:
            node_id: 节点 ID
            depth: 查找深度
            relation_type: 关系类型过滤

        Returns:
            邻居节点字典，键为关系类型
        """
        if not self.storage.driver:
            return self._mock_find_neighbors(node_id, depth)

        try:
            with self.storage.driver.session() as session:
                if relation_type:
                    query = f"""
                    MATCH (source)-[r:{relation_type}]->(target)
                    WHERE id(source) = $node_id
                    RETURN id(target) as node_id, labels(target) as labels,
                           properties(target) as props, type(r) as rel_type
                    """
                    result = session.run(query, node_id=int(node_id))
                else:
                    query = """
                    MATCH (source)-[r]->(target)
                    WHERE id(source) = $node_id
                    RETURN id(target) as node_id, labels(target) as labels,
                           properties(target) as props, type(r) as rel_type
                    """
                    result = session.run(query, node_id=int(node_id))

                neighbors = {}
                for record in result:
                    rel_type = record["rel_type"]
                    if rel_type not in neighbors:
                        neighbors[rel_type] = []

                    node = Node(
                        id=str(record["node_id"]),
                        label=record["labels"][0] if record["labels"] else "Unknown",
                        properties=record["props"],
                    )
                    neighbors[rel_type].append(node)

                logger.info(f"查找邻居完成: {sum(len(v) for v in neighbors.values())} 个节点")
                return neighbors

        except Exception as e:
            logger.error(f"查找邻居失败: {str(e)}")
            return {}

    def _mock_find_neighbors(self, node_id: str, depth: int) -> Dict[str, List[Node]]:
        """内存存储查找邻居"""
        if not hasattr(self.storage, "_mock_nodes") or not hasattr(self.storage, "_mock_edges"):
            return {}

        neighbors: Dict[str, List[Node]] = {}
        # 只查一层深度的直连节点
        for edge in self.storage._mock_edges:
            # outgoing: source → target
            if edge.source_id == node_id:
                target_node = self.storage._mock_nodes.get(edge.target_id)
                if target_node:
                    neighbors.setdefault(edge.relation_type, []).append(target_node)
            # incoming: target ← source (undirected)
            if edge.target_id == node_id:
                source_node = self.storage._mock_nodes.get(edge.source_id)
                if source_node:
                    neighbors.setdefault(edge.relation_type, []).append(source_node)
        return neighbors

    def find_path(self, source_id: str, target_id: str, max_length: int = 5) -> List[List[Dict[str, str]]]:
        """查找两点之间的所有路径

        Args:
            source_id: 源节点 ID
            target_id: 目标节点 ID
            max_length: 最大路径长度

        Returns:
            路径列表，每条路径是一个节点和边的序列
        """
        if not self.storage.driver:
            return self._mock_find_path(source_id, target_id)

        try:
            with self.storage.driver.session() as session:
                query = f"""
                MATCH path = (source)-[*1..{max_length}]-(target)
                WHERE id(source) = $source_id AND id(target) = $target_id
                RETURN path
                """
                result = session.run(query, source_id=int(source_id), target_id=int(target_id))

                paths = []
                for record in result:
                    path_nodes = []
                    for node in record["path"].nodes:
                        path_nodes.append(
                            {
                                "id": str(node.id),
                                "label": node.labels.pop() if node.labels else "Unknown",
                                "properties": dict(node),
                            }
                        )
                    paths.append(path_nodes)

                logger.info(f"查找路径完成: {len(paths)} 条路径")
                return paths

        except Exception as e:
            logger.error(f"查找路径失败: {str(e)}")
            return []

    def _mock_find_path(self, source_id: str, target_id: str) -> List[List[Dict[str, str]]]:
        """模拟查找路径"""
        return []

    def find_shortest_path(self, source_id: str, target_id: str) -> Optional[List[Dict[str, str]]]:
        """查找两点之间的最短路径

        Args:
            source_id: 源节点 ID
            target_id: 目标节点 ID

        Returns:
            最短路径，如果不存在则返回 None
        """
        if not self.storage.driver:
            return self._mock_find_shortest_path(source_id, target_id)

        try:
            with self.storage.driver.session() as session:
                query = """
                MATCH path = shortestPath((source)-[*]-(target))
                WHERE id(source) = $source_id AND id(target) = $target_id
                RETURN path
                """
                result = session.run(query, source_id=int(source_id), target_id=int(target_id))
                record = result.single()

                if record:
                    path_nodes = []
                    for node in record["path"].nodes:
                        path_nodes.append(
                            {
                                "id": str(node.id),
                                "label": node.labels.pop() if node.labels else "Unknown",
                                "properties": dict(node),
                            }
                        )
                    return path_nodes

                return None

        except Exception as e:
            logger.error(f"查找最短路径失败: {str(e)}")
            return None

    def _mock_find_shortest_path(self, source_id: str, target_id: str) -> Optional[List[Dict[str, str]]]:
        """模拟查找最短路径"""
        return None

    def find_subgraph_by_entities(self, entity_ids: List[str], depth: int = 1) -> Dict[str, List[Node]]:
        """根据实体 ID 查找子图

        Args:
            entity_ids: 实体 ID 列表
            depth: 扩展深度

        Returns:
            子图数据，包含节点和边
        """
        if not entity_ids or not self.storage.driver:
            return self._mock_find_subgraph_by_entities(entity_ids, depth)

        try:
            with self.storage.driver.session() as session:
                node_ids = [int(id) for id in entity_ids]
                query = f"""
                MATCH (n)
                WHERE id(n) IN $node_ids
                CALL {{
                    WITH n
                    MATCH path = (n)-[*1..{depth}]-(related)
                    RETURN related
                }}
                RETURN DISTINCT n, related
                """
                result = session.run(query, node_ids=node_ids)

                nodes = {}
                for record in result:
                    for node in [record["n"], record["related"]]:
                        node_id = str(node.id)
                        if node_id not in nodes:
                            nodes[node_id] = Node(
                                id=node_id,
                                label=node.labels.pop() if node.labels else "Unknown",
                                properties=dict(node),
                            )

                logger.info(f"子图查询完成: {len(nodes)} 个节点")
                return {"nodes": list(nodes.values()), "edges": []}

        except Exception as e:
            logger.error(f"子图查询失败: {str(e)}")
            return {}

    def _mock_find_subgraph_by_entities(self, entity_ids: List[str], depth: int) -> Dict[str, List[Node]]:
        """模拟子图查询"""
        return {}

    def find_common_neighbors(self, node_id_1: str, node_id_2: str) -> List[Node]:
        """查找两个节点的公共邻居

        Args:
            node_id_1: 第一个节点 ID
            node_id_2: 第二个节点 ID

        Returns:
            公共邻居节点列表
        """
        if not self.storage.driver:
            return self._mock_find_common_neighbors(node_id_1, node_id_2)

        try:
            with self.storage.driver.session() as session:
                query = """
                MATCH (n1)-[r1]->(common)<-[r2]-(n2)
                WHERE id(n1) = $node_id_1 AND id(n2) = $node_id_2
                RETURN DISTINCT common
                """
                result = session.run(query, node_id_1=int(node_id_1), node_id_2=int(node_id_2))

                neighbors = []
                for record in result:
                    node = record["common"]
                    neighbors.append(
                        Node(
                            id=str(node.id),
                            label=node.labels.pop() if node.labels else "Unknown",
                            properties=dict(node),
                        )
                    )

                logger.info(f"公共邻居查询完成: {len(neighbors)} 个节点")
                return neighbors

        except Exception as e:
            logger.error(f"公共邻居查询失败: {str(e)}")
            return []

    def _mock_find_common_neighbors(self, node_id_1: str, node_id_2: str) -> List[Node]:
        """模拟公共邻居查询"""
        return []

    def search_by_text(self, keyword: str, label: Optional[str] = None, limit: int = 10) -> List[Node]:
        """根据文本搜索节点

        Args:
            keyword: 搜索关键词
            label: 节点标签过滤
            limit: 返回数量限制

        Returns:
            匹配的节点列表
        """
        if not keyword:
            return []

        if not self.storage.driver:
            # 内存存储搜索
            results: List[Node] = []
            keyword_lower = keyword.lower()
            for node in self.storage._mock_nodes.values():
                if label and node.label != label:
                    continue
                # 搜索节点属性值
                match = False
                for val in node.properties.values():
                    if keyword_lower in val.lower():
                        match = True
                        break
                if match:
                    results.append(node)
                    if len(results) >= limit:
                        break
            return results

        try:
            with self.storage.driver.session() as session:
                if label:
                    query = f"""
                    MATCH (n:{label})
                    WHERE any(prop in keys(n) WHERE toString(n[prop]) CONTAINS $keyword)
                    RETURN id(n) as node_id, labels(n) as labels, properties(n) as props
                    LIMIT $limit
                    """
                    result = session.run(query, keyword=keyword, limit=limit)
                else:
                    query = """
                    MATCH (n)
                    WHERE any(prop in keys(n) WHERE toString(n[prop]) CONTAINS $keyword)
                    RETURN id(n) as node_id, labels(n) as labels, properties(n) as props
                    LIMIT $limit
                    """
                    result = session.run(query, keyword=keyword, limit=limit)

                nodes = []
                for record in result:
                    nodes.append(
                        Node(
                            id=str(record["node_id"]),
                            label=record["labels"][0] if record["labels"] else "Unknown",
                            properties=record["props"],
                        )
                    )

                logger.info(f"文本搜索完成: {len(nodes)} 个节点")
                return nodes

        except Exception as e:
            logger.error(f"文本搜索失败: {str(e)}")
            return []

    def enhanced_retrieval(
        self, query: str, entity_ids: Optional[List[str]] = None, max_results: int = 10
    ) -> Dict[str, any]:
        """图谱增强检索

        结合图谱结构进行增强检索，返回相关的实体和路径信息

        Args:
            query: 检索查询
            entity_ids: 相关实体 ID 列表（可选）
            max_results: 最大返回结果数

        Returns:
            检索结果字典
        """
        results = {
            "query": query,
            "entities": [],
            "paths": [],
            "context": [],
            "total": 0,
        }

        try:
            if entity_ids:
                for entity_id in entity_ids:
                    neighbors = self.find_neighbors(entity_id, depth=2)
                    for rel_type, nodes in neighbors.items():
                        results["entities"].extend(nodes)
                        results["context"].append({"from": entity_id, "relation": rel_type, "count": len(nodes)})

            if len(results["entities"]) > max_results:
                results["entities"] = results["entities"][:max_results]

            results["total"] = len(results["entities"])
            logger.info(f"增强检索完成: {results['total']} 个实体")

        except Exception as e:
            logger.error(f"增强检索失败: {str(e)}")

        return results

    def get_node_degree(self, node_id: str) -> Dict[str, int]:
        """获取节点的度数

        Args:
            node_id: 节点 ID

        Returns:
            度数统计字典
        """
        if not self.storage.driver:
            return self._mock_get_node_degree(node_id)

        try:
            with self.storage.driver.session() as session:
                in_degree_query = "MATCH ()-[r]->(n) WHERE id(n) = $node_id RETURN count(r) as count"
                in_result = session.run(in_degree_query, node_id=int(node_id))
                in_degree = in_result.single()["count"]

                out_degree_query = "MATCH (n)-[r]->() WHERE id(n) = $node_id RETURN count(r) as count"
                out_result = session.run(out_degree_query, node_id=int(node_id))
                out_degree = out_result.single()["count"]

                return {"in_degree": in_degree, "out_degree": out_degree, "total_degree": in_degree + out_degree}

        except Exception as e:
            logger.error(f"获取节点度数失败: {str(e)}")
            return {"in_degree": 0, "out_degree": 0, "total_degree": 0}

    def _mock_get_node_degree(self, node_id: str) -> Dict[str, int]:
        """模拟获取节点度数"""
        return {"in_degree": 0, "out_degree": 0, "total_degree": 0}

    def find_triangles(self) -> List[Set[str]]:
        """查找图中的三角形（三个互相关联的节点）

        Returns:
            三角形列表，每个三角形是一个节点 ID 集合
        """
        if not self.storage.driver:
            return []

        try:
            with self.storage.driver.session() as session:
                query = """
                MATCH (a)-[]->(b)-[]->(c)-[]->(a)
                RETURN DISTINCT collect(DISTINCT id(a)) + collect(DISTINCT id(b)) + collect(DISTINCT id(c)) as triangle
                """
                result = session.run(query)

                triangles = []
                for record in result:
                    triangle_ids = set(str(node_id) for node_id in record["triangle"])
                    triangles.append(triangle_ids)

                logger.info(f"三角形查询完成: {len(triangles)} 个三角形")
                return triangles

        except Exception as e:
            logger.error(f"三角形查询失败: {str(e)}")
            return []

    def analyze_connectivity(self, component_type: str = "weak") -> Dict[str, any]:
        """分析图的连通性

        Args:
            component_type: 连通分量类型（weak 或 strong）

        Returns:
            连通性分析结果
        """
        if not self.storage.driver:
            return self._mock_analyze_connectivity(component_type)

        try:
            with self.storage.driver.session() as session:
                if component_type == "weak":
                    query = """
                    CALL gds.graph.project('temp', '*', '*')
                    YIELD graphName
                    CALL gds.wcc.stats('temp')
                    YIELD componentCount, componentDistribution
                    CALL gds.graph.drop('temp')
                    RETURN componentCount
                    """
                else:
                    query = """
                    CALL gds.graph.project('temp', '*', '*')
                    YIELD graphName
                    CALL gds.scc.stats('temp')
                    YIELD componentCount, componentDistribution
                    CALL gds.graph.drop('temp')
                    RETURN componentCount
                    """

                result = session.run(query)
                record = result.single()

                return {
                    "component_type": component_type,
                    "component_count": record["componentCount"] if record else 0,
                    "is_connected": record["componentCount"] == 1 if record else True,
                }

        except Exception as e:
            logger.error(f"连通性分析失败: {str(e)}")
            return {}

    def _mock_analyze_connectivity(self, component_type: str) -> Dict[str, any]:
        """模拟连通性分析"""
        return {"component_type": component_type, "component_count": 0, "is_connected": True}
