"""把 Schema hit 组织成当前问题的轻量 SchemaGraph / JoinPath。"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Any

from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.document_builder import DEFAULT_RELATIONS_PATH, load_relations
from engine.schema_retrieval.objects import JoinEdge, JoinPath, SchemaGraph, SchemaHit

TABLE_REF_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.")


def _tables_from_relation(relation: dict[str, Any]) -> list[str]:
    """取出一条 relation 涉及的所有物理表，桥表也算入 JoinPath。"""

    tables = [relation.get("from_table"), relation.get("through_table"), relation.get("to_table")]
    return [str(table) for table in tables if table]


def _edge_from_relation(relation: dict[str, Any]) -> JoinEdge:
    """把 relation YAML 转成 JoinEdge，桥表条件保留在 through_table 中。"""

    return JoinEdge(
        relation_id=str(relation["id"]),
        left_table=str(relation.get("from_table")),
        left_column=str(relation.get("from_column")),
        right_table=str(relation.get("to_table")),
        right_column=str(relation.get("to_column")),
        join_type=str(relation.get("join_type", "inner")),
        through_table=relation.get("through_table"),
        warning=relation.get("aggregation_warning"),
    )


def _metric_tables(metric_key: str, domain_schema: DomainSchema) -> set[str]:
    """从指标公式、过滤条件和默认时间字段里抽取表名。"""

    metric = domain_schema.metrics.get(metric_key)
    if metric is None:
        return set()
    text = " ".join([metric.formula, metric.filter or "", metric.default_time_field or "", metric.description])
    return {table for table in TABLE_REF_RE.findall(text) if table in domain_schema.tables}


def _build_adjacency(relations: list[dict[str, Any]]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """把 relation 列表转成无向邻接表，便于找最短 JoinPath。"""

    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for relation in relations:
        tables = _tables_from_relation(relation)
        for left in tables:
            for right in tables:
                if left != right:
                    adjacency.setdefault(left, []).append((right, relation))
    return adjacency


def _find_path(start: str, target: str, adjacency: dict[str, list[tuple[str, dict[str, Any]]]]) -> list[dict[str, Any]]:
    """在 relations 图里找 start 到 target 的最短关系链。"""

    queue: deque[tuple[str, list[dict[str, Any]]]] = deque([(start, [])])
    visited = {start}
    while queue:
        current, path = queue.popleft()
        if current == target:
            return path
        for next_table, relation in adjacency.get(current, []):
            if next_table in visited:
                continue
            visited.add(next_table)
            queue.append((next_table, [*path, relation]))
    return []


def _relation_key_columns(relation: dict[str, Any]) -> dict[str, set[str]]:
    """收集 Join 条件里的 key 字段，确保局部 Schema 不缺 join key。"""

    columns: dict[str, set[str]] = {}
    from_table = relation.get("from_table")
    to_table = relation.get("to_table")
    through_table = relation.get("through_table")
    if from_table and relation.get("from_column"):
        columns.setdefault(str(from_table), set()).add(str(relation["from_column"]))
    if to_table and relation.get("to_column"):
        columns.setdefault(str(to_table), set()).add(str(relation["to_column"]))
    if through_table:
        for column_name in ["through_from_column", "through_to_column"]:
            if relation.get(column_name):
                columns.setdefault(str(through_table), set()).add(str(relation[column_name]))
    return columns


def build_schema_graph(
    hits: list[SchemaHit],
    *,
    domain_schema: DomainSchema,
    relations_path: Path = DEFAULT_RELATIONS_PATH,
) -> SchemaGraph:
    """★ 根据命中文档生成当前问题的局部 SchemaGraph。"""

    relations = load_relations(relations_path)
    selected_tables: set[str] = set()
    selected_metrics: set[str] = set()
    selected_relations: dict[str, dict[str, Any]] = {}

    # 步骤 1：从命中文档收集直接相关的表、指标和关系。-------------------------------
    for hit in hits:
        document = hit.document
        if document.table:
            selected_tables.add(document.table)
        if document.metric_key:
            selected_metrics.add(document.metric_key)
            selected_tables.update(_metric_tables(document.metric_key, domain_schema))
        if document.relation:
            selected_relations[str(document.relation["id"])] = document.relation
            selected_tables.update(_tables_from_relation(document.relation))

    # 步骤 2：用最短路径补齐多表之间的关系，不允许凭空编 join。----------------------
    adjacency = _build_adjacency(relations)
    ordered_tables = sorted(table for table in selected_tables if table in domain_schema.tables)
    relation_path_edges: dict[str, dict[str, Any]] = dict(selected_relations)
    join_paths: list[JoinPath] = []
    if len(ordered_tables) > 1:
        anchor = ordered_tables[0]
        for table in ordered_tables[1:]:
            path_relations = _find_path(anchor, table, adjacency)
            if not path_relations:
                continue
            for relation in path_relations:
                relation_path_edges[str(relation["id"])] = relation
                selected_tables.update(_tables_from_relation(relation))
            edges = [_edge_from_relation(relation) for relation in path_relations]
            path_tables = {
                anchor,
                table,
                *[relation_table for relation in path_relations for relation_table in _tables_from_relation(relation)],
            }
            join_paths.append(JoinPath(tables=sorted(path_tables), edges=edges))

    # 步骤 3：字段按表补齐。M9 先保证 recall，M11 再做更严格的局部 prompt 精简。---------
    fields: dict[str, set[str]] = {
        table: set(domain_schema.tables[table].fields)
        for table in selected_tables
        if table in domain_schema.tables
    }
    for relation in relation_path_edges.values():
        for table, columns in _relation_key_columns(relation).items():
            if table in domain_schema.tables:
                fields.setdefault(table, set()).update(columns)

    return SchemaGraph(
        tables=sorted(table for table in selected_tables if table in domain_schema.tables),
        fields={table: sorted(columns) for table, columns in sorted(fields.items())},
        metrics=sorted(selected_metrics),
        relations=[relation_path_edges[key] for key in sorted(relation_path_edges)],
        join_paths=join_paths,
    )
