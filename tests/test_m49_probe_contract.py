"""M49-P1 Probe 只核对业务语义，不绑定 fake/real SQL 的列投影差异。"""

from scripts.probe_m49_t1_t2 import _comparison_rows_match


def test_comparison_probe_accepts_real_repair_projection() -> None:
    """Probe 核对业务语义，接受真实 month/metric/delta/rate 投影。"""

    assert _comparison_rows_match([
        {"month": "2026-07-01", "net_refund_amount": 120000.0},
        {
            "month": "2026-08-01",
            "net_refund_amount": 180000.0,
            "delta": 60000.0,
            "rate": 0.5,
        },
    ])


def test_comparison_probe_accepts_frozen_oracle_projection_but_rejects_wrong_value() -> None:
    """兼容 frozen oracle 的列名，但不能因此放过错误业务数值。"""

    assert _comparison_rows_match([
        {"period": "2026-07", "value": 120000},
        {"period": "2026-08", "value": 180000, "diff": 60000, "change_rate": 0.5},
    ])
    assert not _comparison_rows_match([
        {"period": "2026-07", "value": 120000},
        {"period": "2026-08", "value": 170000, "diff": 50000, "change_rate": 0.4},
    ])
