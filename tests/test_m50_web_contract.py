"""M50 跨语言 fixture 与 demo prepare 的 Python authority 回归。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.schemas.agent import AgentResponse
from scripts.export_m50_web_contract_fixtures import CONTRACT_DIR, FIXTURE_DIR, FORMAT, _json_bytes
from scripts.prepare_m50_demo import TARGET_DATABASE, resolve_demo_url


def test_m50_response_fixtures_remain_valid_pydantic_responses() -> None:
    """每个给前端的 fixture 都必须先通过当前 Python AgentResponse。"""

    fixtures = sorted(FIXTURE_DIR.glob("*.json"))
    assert len(fixtures) >= 5
    for path in fixtures:
        AgentResponse.model_validate_json(path.read_text(encoding="utf-8"))


def test_m50_contract_manifest_binds_every_generated_file() -> None:
    """fixture/schema 内容变化必须重签 identity，避免 TS 测试悄悄吃旧样本。"""

    manifest = json.loads((CONTRACT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == FORMAT and manifest["authority"] == "app.schemas.agent"
    for relative, expected in manifest["files"].items():
        content = (CONTRACT_DIR.parent / relative).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected
    expected_identity = hashlib.sha256(
        _json_bytes({"format": FORMAT, "files": manifest["files"]})
    ).hexdigest()
    assert manifest["identity"] == expected_identity


def test_m50_demo_target_guard_only_accepts_exact_isolated_database() -> None:
    """危险操作的白名单在建连接前关闭，任何相近名字都不能“猜对”。"""

    configured = "mysql+pymysql://user:password@127.0.0.1:3306/datapilot_dev?charset=utf8mb4"
    resolved = resolve_demo_url(configured, TARGET_DATABASE)
    assert resolved.database == "datapilot_demo"
    for forbidden in ("datapilot_dev", "datapilot_m48_test", "datapilot_demo_test", "prod", ""):
        try:
            resolve_demo_url(configured, forbidden)
        except ValueError as error:
            assert str(error) == "m50_demo_confirmation_mismatch"
        else:
            raise AssertionError(f"forbidden target accepted: {forbidden}")
