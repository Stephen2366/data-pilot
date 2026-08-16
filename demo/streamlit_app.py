"""M6 Streamlit 演示页：通过真实 HTTP 调用展示 DataPilot v1 查询闭环。

★ 这个页面只负责演示，不承载业务逻辑。所有 SQL 生成、安全拦截、Trace 和图表都来自
FastAPI `/api/query`，避免前端复制一套 Agent 流程。
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

API_URL = "http://127.0.0.1:8000/api/query"
DEMO_QUESTIONS = [
    "查询 active 商品列表前 10 条",
    "2026年6月退款率最高的商品是什么？",
    "各渠道订单量是多少？",
    "每个渠道带来的退款数量是多少？",
    "DROP TABLE orders",
]
USER_ROLES = ["ops", "admin", "customer_service", "demo_user"]
SCHEMA_RETRIEVAL_PROFILES = {
    "Local deterministic": "default",
    "Milvus + Qwen embedding": "milvus_qwen37",
}


def _post_query(
    api_url: str,
    question: str,
    user_role: str,
    *,
    force_new_pipeline: bool = False,
    schema_retrieval_profile: str = "default",
) -> dict[str, Any]:
    """调用 FastAPI `/api/query` 并返回 AgentResponse 字典。"""

    payload = json.dumps(
        {
            "question": question,
            "user_role": user_role,
            "force_new_pipeline": force_new_pipeline,
            "schema_retrieval_profile": schema_retrieval_profile,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - 本地演示页调用用户配置的 API URL。
        return json.loads(response.read().decode("utf-8"))


def _render_chart(chart_spec: dict[str, Any] | None) -> None:
    """渲染 Vega-Lite 图表；spec 缺失时保持区域干净，不额外制造占位噪音。"""

    if not chart_spec:
        return
    st.vega_lite_chart(chart_spec, use_container_width=True)


def _render_response(body: dict[str, Any]) -> None:
    """把 AgentResponse 拆成演示页需要的 answer / SQL / table / chart / trace。"""

    # 步骤 1：顶部状态条 =====================================================================
    status = body.get("safety_status", "unknown")
    execution_status = body.get("execution_status", "unknown")
    answer_status = body.get("answer_status", "unknown")
    error_type = body.get("error_type") or "none"
    trace_id = body.get("trace_id") or "unknown"
    latency = (body.get("cost") or {}).get("latency_ms", 0)
    st.markdown(
        f"""
        <div class="status-strip">
          <span class="status-pill status-{status}">{status}</span>
          <span>execution: <code>{execution_status}</code></span>
          <span>answer: <code>{answer_status}</code></span>
          <span>trace_id: <code>{trace_id}</code></span>
          <span>latency: <code>{latency} ms</code></span>
          <span>error_type: <code>{error_type}</code></span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 步骤 2：答案、SQL 和表格 ----------------------------------------------------------------
    st.subheader("Answer")
    st.write(body.get("answer") or "")

    if body.get("blocked_reason"):
        st.error(body["blocked_reason"])

    citations = body.get("citations") or []
    if citations:
        st.subheader("Citations")
        st.json(citations)

    st.subheader("SQL")
    st.code(body.get("sql") or "", language="sql")

    rows = body.get("rows") or []
    st.subheader("Table")
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.dataframe(pd.DataFrame(), use_container_width=True, hide_index=True)

    # 步骤 3：图表与调试 trace ----------------------------------------------------------------
    st.subheader("Chart")
    _render_chart(body.get("chart_spec"))

    st.subheader("Trace")
    st.json(
        {
            "tables_used": body.get("tables_used", []),
            "docs_used": body.get("docs_used", []),
            "tool_calls": body.get("tool_calls", []),
            "reason_code": body.get("reason_code"),
            "cost": body.get("cost", {}),
        }
    )


def _install_page_style() -> None:
    """用少量 CSS 把 Streamlit 默认页面收紧成运营控制台气质。"""

    st.markdown(
        """
        <style>
          :root {
            --ink: #1d2433;
            --muted: #657085;
            --line: #d8dde8;
            --panel: #f7f8fb;
            --accent: #0f766e;
            --danger: #b42318;
          }
          .block-container {
            max-width: 1160px;
            padding-top: 1.8rem;
            padding-bottom: 2rem;
          }
          h1, h2, h3 {
            color: var(--ink);
            letter-spacing: 0;
          }
          [data-testid="stSidebar"] {
            background: #f2f5f8;
            border-right: 1px solid var(--line);
          }
          .status-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 10px 18px;
            align-items: center;
            border: 1px solid var(--line);
            background: var(--panel);
            padding: 10px 12px;
            margin: 12px 0 18px;
            font-size: 13px;
            color: var(--muted);
          }
          .status-pill {
            display: inline-flex;
            align-items: center;
            min-height: 24px;
            padding: 2px 9px;
            border-radius: 4px;
            color: #fff;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0;
          }
          .status-passed {
            background: var(--accent);
          }
          .status-blocked {
            background: var(--danger);
          }
          code {
            color: var(--ink);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    """Streamlit 入口：收集问题和角色，提交后渲染结构化 AgentResponse。"""

    st.set_page_config(page_title="DataPilot Console", page_icon="DP", layout="wide")
    _install_page_style()
    st.title("DataPilot Console")

    # 侧边栏只放运行参数和固定演示问题，主区域专注展示结构化响应。
    with st.sidebar:
        api_url = st.text_input("API", value=API_URL)
        user_role = st.selectbox("Role", USER_ROLES, index=0)
        retrieval_label = st.radio(
            "Schema Retrieval",
            options=list(SCHEMA_RETRIEVAL_PROFILES),
            index=0,
            horizontal=False,
        )
        schema_retrieval_profile = SCHEMA_RETRIEVAL_PROFILES[retrieval_label]
        force_new_pipeline = st.toggle(
            "New Text2SQL",
            value=schema_retrieval_profile != "default",
        )
        st.divider()
        for question in DEMO_QUESTIONS:
            if st.button(question, use_container_width=True):
                st.session_state["question"] = question

    question = st.text_area("Question", value=st.session_state.get("question", DEMO_QUESTIONS[0]), height=90)
    submitted = st.button("Run", type="primary")

    if submitted:
        st.session_state["question"] = question
        try:
            body = _post_query(
                api_url=api_url,
                question=question,
                user_role=user_role,
                force_new_pipeline=force_new_pipeline,
                schema_retrieval_profile=schema_retrieval_profile,
            )
        except (URLError, TimeoutError) as exc:
            st.error(f"API request failed: {exc}")
            return
        _render_response(body)


if __name__ == "__main__":
    main()
