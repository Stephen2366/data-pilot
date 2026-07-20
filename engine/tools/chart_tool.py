"""M5 Chart Tool：把常见聚合结果转换成 Vega-Lite 兼容 spec。

阶段二不做复杂智能可视化，只实现三类稳定规则：类别 + 数值柱状图、日期 + 数值折线图、
Top N / 排名类横向柱状图。无法判断时返回 None，不影响主答案。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHART_TEMPLATES_PATH = PROJECT_ROOT / "domain_pack" / "chart_templates" / "basic.yaml"


def build_chart_spec(*, columns: list[str], rows: list[dict[str, Any]], question: str) -> dict[str, Any] | None:
    """根据表格形状和问题关键词生成最小 Vega-Lite spec。"""

    if not rows or not columns:
        return None

    templates = _load_chart_templates()
    numeric_columns = [column for column in columns if _is_numeric_column(rows, column)]
    if not numeric_columns:
        return None

    # 步骤 1：单指标兜底 ---------------------------------------------------------------------
    # ★ GMV 这类单行单值结果也有演示价值，用合成 metric_name 生成一根柱，避免前端无图可画。
    if len(columns) == 1 and len(numeric_columns) == 1:
        value_column = numeric_columns[0]
        return _single_metric_bar(
            template=templates["bar"],
            metric_label=value_column,
            value=rows[0].get(value_column),
            question=question,
        )

    dimension = _pick_dimension_column(columns, rows)
    measure = _pick_measure_column(question, numeric_columns)
    if dimension is None:
        return None

    if _looks_like_date_column(dimension):
        return _line_spec(template=templates["line"], rows=rows, x_field=dimension, y_field=measure, question=question)
    if _looks_like_top_question(question):
        return _horizontal_bar_spec(
            template=templates["horizontal_bar"],
            rows=rows,
            y_field=dimension,
            x_field=measure,
            question=question,
        )
    return _bar_spec(template=templates["bar"], rows=rows, x_field=dimension, y_field=measure, question=question)


def _load_chart_templates(path: Path = CHART_TEMPLATES_PATH) -> dict[str, dict[str, Any]]:
    """读取图表模板配置；模板缺失时让异常暴露，提醒配置没有落地。"""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(payload.get("templates") or {})


def _is_numeric_column(rows: list[dict[str, Any]], column: str) -> bool:
    """判断某列是否适合作为 Vega-Lite quantitative 轴。"""

    for row in rows:
        value = row.get(column)
        if value is None:
            continue
        return isinstance(value, int | float)
    return False


def _pick_dimension_column(columns: list[str], rows: list[dict[str, Any]]) -> str | None:
    """选择第一个非数值列作为维度轴。"""

    for column in columns:
        if not _is_numeric_column(rows, column):
            return column
    return None


def _pick_measure_column(question: str, numeric_columns: list[str]) -> str:
    """按问题关键词优先选择指标列。

    ★ 聚合 SQL 常同时返回 count 和 rate。用户问“退款率”时如果拿第一个数值列，会把
    refund_count 画成主指标；这里用轻量规则把业务词和列名对齐。
    """

    normalized = question.lower()
    if ("退款率" in normalized or "rate" in normalized) and "refund_rate" in numeric_columns:
        return "refund_rate"
    if "gmv" in normalized and "gmv" in numeric_columns:
        return "gmv"
    if "订单量" in normalized and "order_count" in numeric_columns:
        return "order_count"
    return numeric_columns[0]


def _looks_like_date_column(column: str) -> bool:
    """按列名判断日期 / 时间维度，避免为了 M5 引入更复杂类型推断。"""

    lowered = column.lower()
    return any(marker in lowered for marker in ("date", "month", "_at", "day"))


def _looks_like_top_question(question: str) -> bool:
    """识别 Top N / 排名类问题，用横向柱状图更适合比较长类目名称。"""

    normalized = question.lower()
    return any(marker in normalized for marker in ("top", "最高", "排名", "最多"))


def _bar_spec(
    *,
    template: dict[str, Any],
    rows: list[dict[str, Any]],
    x_field: str,
    y_field: str,
    question: str,
) -> dict[str, Any]:
    """生成普通柱状图 spec。"""

    return {
        **template,
        "title": question,
        "data": {"values": rows},
        "encoding": {
            "x": {"field": x_field, "type": "nominal"},
            "y": {"field": y_field, "type": "quantitative"},
        },
    }


def _horizontal_bar_spec(
    *,
    template: dict[str, Any],
    rows: list[dict[str, Any]],
    y_field: str,
    x_field: str,
    question: str,
) -> dict[str, Any]:
    """生成横向柱状图 spec。"""

    return {
        **template,
        "title": question,
        "data": {"values": rows},
        "encoding": {
            "y": {"field": y_field, "type": "nominal", "sort": "-x"},
            "x": {"field": x_field, "type": "quantitative"},
        },
    }


def _line_spec(
    *,
    template: dict[str, Any],
    rows: list[dict[str, Any]],
    x_field: str,
    y_field: str,
    question: str,
) -> dict[str, Any]:
    """生成折线图 spec。"""

    return {
        **template,
        "title": question,
        "data": {"values": rows},
        "encoding": {
            "x": {"field": x_field, "type": "temporal"},
            "y": {"field": y_field, "type": "quantitative"},
        },
    }


def _single_metric_bar(*, template: dict[str, Any], metric_label: str, value: Any, question: str) -> dict[str, Any]:
    """把 GMV 这类单指标结果转换成一根柱的 spec。"""

    return {
        **template,
        "title": question,
        "data": {"values": [{"metric_name": metric_label, "value": value}]},
        "encoding": {
            "x": {"field": "metric_name", "type": "nominal"},
            "y": {"field": "value", "type": "quantitative"},
        },
    }
