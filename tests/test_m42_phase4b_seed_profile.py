"""M42-B 独立 seed/profile identity 与真实 SQL oracle。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Order, Refund
from engine.phase4b.seed_profile import SeedProfileError, load_phase4b_seed_profile, resolve_seed_profile
from scripts.seed_data import EXPECTED_SEED_COUNTS, seed_database


def _build(alias: str) -> dict:
    """在独立内存数据库中按指定 profile 重建一次完整 seed。"""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        return seed_database(session, reset_existing=True, profile_alias=alias)


def test_phase4b_profile_rebuild_is_deterministic_and_oracles_reconcile() -> None:
    """两次真实建库必须得到相同 profile/oracle，且三种分解都命中 exact facts。"""

    first = _build("phase4b")
    second = _build("phase4b")
    assert first["seed_profile"] == second["seed_profile"]
    assert first["phase4b_facts"]["oracle_identity"] == second["phase4b_facts"]["oracle_identity"]

    facts = first["phase4b_facts"]
    assert facts["months"]["2026-07"]["net_refund_amount"] == Decimal("120000.00")
    assert facts["months"]["2026-08"]["net_refund_amount"] == Decimal("180000.00")
    assert facts["months"]["2026-07"]["reasons"]["quality_issue"] == Decimal("48000.00")
    assert facts["months"]["2026-08"]["reasons"]["quality_issue"] == Decimal("96000.00")
    assert facts["months"]["2026-08"]["channels"]["Mobile App"] == Decimal("78000.00")
    assert facts["months"]["2026-08"]["products"]["SKU-HIGH-REFUND-01"] == Decimal("54000.00")
    assert facts["wide_matches_star_total"] is True
    assert facts["negative_correction_count"] == 2


def test_legacy_default_stays_unchanged_and_unknown_profile_fails_before_write() -> None:
    """默认调用仍是历史 seed；未知 alias 不得删除或写入任何行。"""

    legacy = _build("legacy")
    assert legacy["counts"] == EXPECTED_SEED_COUNTS
    assert legacy["seed_profile"] == {
        "alias": "legacy", "profile_identity": "sqlite_deterministic_seed",
        "content_identity": None, "extension_counts": {},
    }

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)
        before = session.execute(select(func.count(Order.id))).scalar_one()
        with pytest.raises(SeedProfileError, match="unknown"):
            seed_database(session, reset_existing=True, profile_alias="typo")
        assert session.execute(select(func.count(Order.id))).scalar_one() == before


def test_profile_manifest_tamper_is_rejected(tmp_path: Path) -> None:
    """recipe 内容变化但 manifest 未升级时，消费者不能进入数据库构建。"""

    source = Path("domain_pack/phase4b/seed_profile.json").read_text(encoding="utf-8")
    manifest = Path("domain_pack/phase4b/seed_profile.manifest.json").read_text(encoding="utf-8")
    profile_path = tmp_path / "profile.json"
    manifest_path = tmp_path / "manifest.json"
    profile_path.write_text(source.replace("120000.00", "120001.00", 1), encoding="utf-8")
    manifest_path.write_text(manifest, encoding="utf-8")
    with pytest.raises(SeedProfileError, match="identity"):
        load_phase4b_seed_profile(profile_path, manifest_path)

    assert resolve_seed_profile("legacy") is None
