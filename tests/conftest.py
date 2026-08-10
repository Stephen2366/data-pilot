"""全仓测试的 hermetic 边界：未显式注入 fake 时禁止真实 Text2SQL provider。"""

from __future__ import annotations

import pytest


class RealProviderAccessForbidden(BaseException):
    """故意不继承 Exception，避免产品容错把测试配置错误包装成普通 pipeline 失败。"""


class _ForbiddenLLMClient:
    provider = "forbidden-in-tests"
    model = "forbidden-in-tests"
    max_retries = 0

    def complete(self, **_: object) -> str:
        raise RealProviderAccessForbidden(
            "pytest 禁止未 mock 的真实 LLM provider；请显式注入 fake client，"
            "或为 legacy 合同传 force_new_pipeline=False。"
        )


@pytest.fixture(autouse=True)
def forbid_unmocked_text2sql_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认替换新 pipeline 的 client factory；需要模型行为的测试可在用例内覆盖。"""

    from engine.nl2sql import pipeline

    monkeypatch.setattr(pipeline, "get_default_llm_client", lambda: _ForbiddenLLMClient())
