"""M4 Schema Loader：把 domain_pack 里的业务知识加载成 prompt / policy 可用结构。

★ `engine/` 不应该硬编码“电商有哪些表、哪些字段敏感”。这里像 SpringBoot 里读取
配置中心一样，把 `domain_pack/` 变成 NL2SQL 引擎可消费的领域模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DESC_DIR = PROJECT_ROOT / "domain_pack" / "schema_desc"
METRICS_PATH = PROJECT_ROOT / "domain_pack" / "metrics.yaml"
SQL_EXAMPLES_PATH = PROJECT_ROOT / "domain_pack" / "sql_examples" / "basic.yaml"

# ★ `schema_desc/*.md` 是自然语言 SQL 的 queryable universe，不是 SQLAlchemy metadata
# 的机械全集。物理表可以因兼容或迁移继续存在，但只有这里有描述的分析表才会进入
# planner、Schema Retrieval 和 prompt。SQL Guard 也复用这份默认集合。
DEFAULT_QUERYABLE_TABLE_NAMES = frozenset(
    path.stem for path in SCHEMA_DESC_DIR.glob("*.md") if path.name != ".gitkeep"
)


@dataclass(frozen=True)
class FieldDescription:
    """字段描述：保存 prompt 和安全策略共同关心的元数据。"""

    name: str
    meaning: str
    semantic_role: str
    sensitivity: str


@dataclass(frozen=True)
class TableDescription:
    """表描述：一个表的业务含义、字段清单和关联关系。"""

    name: str
    business_meaning: str
    fields: dict[str, FieldDescription] = field(default_factory=dict)
    relations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MetricDescription:
    """KPI 口径描述：让 LLM 生成 SQL 时知道 GMV、退款率等词的真实计算方式。"""

    key: str
    name: str
    formula: str
    description: str
    filter: str | None = None
    default_time_field: str | None = None


@dataclass(frozen=True)
class SQLExample:
    """few-shot 示例：来自 M3 已验证模板 SQL，供 M4 prompt 复用。"""

    example_id: str
    question: str
    route: str
    expected_tables: list[str]
    sql: str


@dataclass(frozen=True)
class DomainSchema:
    """DataPilot 领域 Schema 快照。

    `sensitive_fields` 使用 `table.column` 全限定名，方便 policy 不依赖自然语言描述再解析。
    """

    tables: dict[str, TableDescription]
    metrics: dict[str, MetricDescription]
    examples: list[SQLExample]
    sensitive_fields: set[str]


def _extract_section(markdown: str, heading: str) -> str:
    """提取二级标题下的正文，供业务含义和关联关系解析使用。"""

    marker = f"## {heading}"
    start = markdown.find(marker)
    if start == -1:
        return ""
    body_start = markdown.find("\n", start)
    next_heading = markdown.find("\n## ", body_start + 1)
    if next_heading == -1:
        next_heading = len(markdown)
    return markdown[body_start:next_heading].strip()


def _parse_fields(markdown: str, table_name: str) -> dict[str, FieldDescription]:
    """从 markdown 表格读取字段说明。

    ★ 这里不用散乱正则去猜自然语言，只解析 M1 固定下来的字段表格列：
    字段 / 含义 / 语义角色 / 敏感级别。
    """

    fields: dict[str, FieldDescription] = {}
    in_field_table = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("| 字段 |"):
            in_field_table = True
            continue
        if in_field_table and line.startswith("## "):
            break
        if in_field_table and (not line.startswith("|") or line.startswith("|---")):
            continue
        if in_field_table and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 4:
                continue
            name, meaning, semantic_role, sensitivity = cells[:4]
            fields[name] = FieldDescription(
                name=name,
                meaning=meaning,
                semantic_role=semantic_role,
                sensitivity=sensitivity,
            )
            continue
    if not fields:
        raise ValueError(f"{table_name} 没有解析到字段说明。")
    return fields


def _parse_relations(markdown: str) -> list[str]:
    """读取关联关系小节中的 `orders.user_id -> users.id` 这类说明。"""

    section = _extract_section(markdown, "关联关系")
    return [line.removeprefix("- ").strip() for line in section.splitlines() if line.strip().startswith("- ")]


def _load_table(path: Path) -> TableDescription:
    """加载单个 schema_desc markdown 文件。"""

    markdown = path.read_text(encoding="utf-8")
    table_name = path.stem
    return TableDescription(
        name=table_name,
        business_meaning=_extract_section(markdown, "业务含义"),
        fields=_parse_fields(markdown, table_name),
        relations=_parse_relations(markdown),
    )


def _load_metrics(path: Path) -> dict[str, MetricDescription]:
    """加载 `metrics.yaml` 中的 KPI 口径。"""

    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    metrics: dict[str, MetricDescription] = {}
    for key, item in (payload.get("metrics") or {}).items():
        metrics[key] = MetricDescription(
            key=key,
            name=str(item.get("name", key)),
            formula=str(item.get("formula", "")),
            description=str(item.get("description", "")),
            filter=item.get("filter"),
            default_time_field=item.get("default_time_field"),
        )
    return metrics


def _load_examples(path: Path) -> list[SQLExample]:
    """加载 M3 已跑通模板 SQL，作为 M4 few-shot 示例。"""

    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    examples: list[SQLExample] = []
    for item in payload.get("examples") or []:
        examples.append(
            SQLExample(
                example_id=str(item.get("id", "")),
                question=str(item.get("question", "")),
                route=str(item.get("route", "sql")),
                expected_tables=list(item.get("expected_tables") or []),
                sql=str(item.get("sql", "")).strip(),
            )
        )
    return examples


def load_domain_schema(
    *,
    schema_desc_dir: Path = SCHEMA_DESC_DIR,
    metrics_path: Path = METRICS_PATH,
    sql_examples_path: Path = SQL_EXAMPLES_PATH,
) -> DomainSchema:
    """★ 读取 DataPilot 领域配置并返回一次完整 Schema 快照。"""

    # 步骤 1：读取所有表结构描述 ----------------------------------------------------------
    tables = {path.stem: _load_table(path) for path in sorted(schema_desc_dir.glob("*.md")) if path.name != ".gitkeep"}

    # 步骤 2：把敏感字段预计算成 `table.column` 集合，policy 层可以 O(1) 判断。---------------
    sensitive_fields = {
        f"{table.name}.{field_desc.name}" for table in tables.values() for field_desc in table.fields.values() if field_desc.sensitivity == "sensitive"
    }

    # 步骤 3：汇总 schema、KPI、few-shot，形成 prompt / policy 共享的领域快照。--------------
    return DomainSchema(
        tables=tables,
        metrics=_load_metrics(metrics_path),
        examples=_load_examples(sql_examples_path),
        sensitive_fields=sensitive_fields,
    )
