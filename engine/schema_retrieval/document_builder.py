"""把 domain_pack 构造成 Schema Retrieval 文档。

M9 不直接读取数据库 DDL，而是复用已经人工维护过的 `schema_desc/*.md`、`metrics.yaml` 和
`relations.yaml`。这类似把 SpringBoot 配置文件整理成搜索索引：运行时检索的是结构化知识，
不是让 LLM 临时猜业务含义。
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.objects import SchemaDocument

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELATIONS_PATH = PROJECT_ROOT / "domain_pack" / "schema_desc" / "relations.yaml"


def load_relations(relations_path: Path = DEFAULT_RELATIONS_PATH) -> list[dict[str, Any]]:
    """读取集中关系定义文件，作为 JoinPath 的唯一结构化来源。"""

    payload = yaml.safe_load(relations_path.read_text(encoding="utf-8")) or {}
    return [dict(item) for item in payload.get("relations") or []]


def _metric_aliases(metric_key: str, metric_name: str) -> list[str]:
    """为常见业务问法补充可检索短语。

    ★ 这些别名不另开文件，是为了避免制造第二份领域知识源；它们只围绕 metrics.yaml 已有
    指标名和描述做轻量扩写，让“渠道 GMV / 商品销售额 / 退款商品”这类中文问法能被召回。
    """

    aliases = {
        "gmv": ["渠道 GMV", "渠道销售额", "成交额", "销售额"],
        "item_gmv": ["商品销售额", "商品 GMV", "商品维度 GMV", "类目销售额"],
        "refund_rate": ["退款商品", "商品退款率", "渠道退款率", "退款率排名"],
        "net_revenue": ["实收金额", "实付金额", "净收入"],
        "add_to_pay_conversion_rate": ["加购到支付转化率", "支付转化率", "转化率最高"],
        "coupon_usage_rate": ["优惠券使用率", "用券订单数", "优惠券使用最多"],
        "avg_selling_price": ["历史售价", "平均售价", "当时价格"],
    }
    return [metric_name, *aliases.get(metric_key, [])]


def _table_aliases(table_name: str) -> list[str]:
    """把英文物理表名扩成常见中文表名，用于关键词召回。"""

    aliases = {
        "orders": ["订单表", "订单", "已支付订单"],
        "order_items": ["订单明细表", "订单明细", "商品明细"],
        "products": ["商品表", "商品", "退款商品"],
        "product_categories": ["类目表", "商品类目", "一级类目", "子类目"],
        "channels": ["渠道表", "渠道"],
        "coupons": ["优惠券表", "优惠券", "券码"],
        "order_coupons": ["订单优惠券桥接表", "用券订单", "优惠券使用"],
        "refunds": ["退款表", "退款", "退款商品"],
        "user_behavior_log": ["行为日志表", "设备类型", "加购", "支付事件"],
        "product_price_history": ["价格历史表", "历史售价", "平均售价"],
        "orders_wide": ["订单宽表", "看板口径", "渠道 GMV 看板"],
        "users": ["用户表", "用户"],
        "tickets": ["工单表", "工单"],
    }
    return aliases.get(table_name, [f"{table_name}表"])


def _relation_text(relation: dict[str, Any]) -> str:
    """把一条 relation YAML 转成关键词和向量都能消费的文本。"""

    parts = [
        str(relation.get("id", "")),
        str(relation.get("relation_type", "")),
        str(relation.get("from_table", "")),
        str(relation.get("from_column", "")),
        str(relation.get("through_table", "")),
        str(relation.get("to_table", "")),
        str(relation.get("to_column", "")),
        str(relation.get("when_to_use", "")),
        str(relation.get("avoid_when", "")),
        str(relation.get("aggregation_warning", "")),
        str(relation.get("temporal_condition", "")),
    ]
    return " ".join(part for part in parts if part and part != "None")


def build_schema_documents(
    domain_schema: DomainSchema,
    *,
    relations_path: Path = DEFAULT_RELATIONS_PATH,
) -> list[SchemaDocument]:
    """★ 构建 field / metric / relation 三类 Schema 文档。"""

    documents: list[SchemaDocument] = []

    # 步骤 1：字段文档 ---------------------------------------------------------------
    for table in domain_schema.tables.values():
        table_alias = f"{table.business_meaning} {table.name} {' '.join(_table_aliases(table.name))}"
        for field_desc in table.fields.values():
            keyword_text = " ".join(
                [
                    table.name,
                    table_alias,
                    field_desc.name,
                    field_desc.meaning,
                    field_desc.semantic_role,
                    field_desc.sensitivity,
                ]
            )
            documents.append(
                SchemaDocument(
                    doc_id=f"field:{table.name}.{field_desc.name}",
                    doc_type="field_doc",
                    table=table.name,
                    column=field_desc.name,
                    metric_key=None,
                    relation=None,
                    keyword_text=keyword_text,
                    vector_text=f"{keyword_text}。{table.business_meaning}",
                    metadata={
                        "doc_type": "field_doc",
                        "table_name": table.name,
                        "column_name": field_desc.name,
                        "semantic_role": field_desc.semantic_role,
                        "sensitivity": field_desc.sensitivity,
                    },
                )
            )

    # 步骤 2：指标文档 ---------------------------------------------------------------
    for metric in domain_schema.metrics.values():
        aliases = _metric_aliases(metric.key, metric.name)
        keyword_text = " ".join(
            [
                metric.key,
                metric.name,
                *aliases,
                metric.formula,
                metric.description,
                metric.filter or "",
                metric.default_time_field or "",
            ]
        )
        documents.append(
            SchemaDocument(
                doc_id=f"metric:{metric.key}",
                doc_type="metric_doc",
                table=None,
                column=None,
                metric_key=metric.key,
                relation=None,
                keyword_text=keyword_text,
                vector_text=keyword_text,
                metadata={
                    "doc_type": "metric_doc",
                    "table_name": None,
                    "metric_key": metric.key,
                    "formula": metric.formula,
                    "default_time_field": metric.default_time_field,
                },
            )
        )

    # 步骤 3：关系文档 ---------------------------------------------------------------
    for relation in load_relations(relations_path):
        text = _relation_text(relation)
        documents.append(
            SchemaDocument(
                doc_id=f"relation:{relation['id']}",
                doc_type="relation_doc",
                table=relation.get("from_table"),
                column=relation.get("from_column"),
                metric_key=None,
                relation=relation,
                keyword_text=text,
                vector_text=text,
                metadata={
                    "doc_type": "relation_doc",
                    "table_name": relation.get("from_table"),
                    "relation_id": relation["id"],
                    "from_table": relation.get("from_table"),
                    "to_table": relation.get("to_table"),
                    "through_table": relation.get("through_table"),
                },
            )
        )

    return documents


def schema_documents_hash(documents: list[SchemaDocument]) -> str:
    """计算 Schema 文档内容指纹，供 Milvus 实验记录索引版本。

    ★ M20 关注的是“这次向量索引里到底灌了哪一版 schema docs”。这里只使用
    `doc_id + keyword_text + vector_text`，避免 metadata 里字段顺序或无关展示信息导致 hash
    抖动。后续如果 schema doc 粒度升级，hash 会自然变化，实验报告也能追溯。
    """

    payload = [
        {
            "doc_id": document.doc_id,
            "keyword_text": document.keyword_text,
            "vector_text": document.vector_text,
        }
        for document in sorted(documents, key=lambda item: item.doc_id)
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
