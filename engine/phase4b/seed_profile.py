"""M42-B：独立 Phase 4B seed/oracle profile。

默认 seed 仍是 legacy。只有调用者显式选择 ``phase4b``，这个深模块才在同一 14 表 schema
中追加 7/8 月行级事实，并返回绑定 recipe/content/config/oracle 的身份。这样历史 Eval 不会
因为一个仍叫 ``sqlite_deterministic_seed`` 的标签而被误判为可比。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Channel, Order, OrderItem, OrderWide, Product, Refund, User
from engine.phase4b.identity import canonical_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "seed_profile.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "seed_profile.manifest.json"
LEGACY_SEED_PROFILE = "legacy"
PHASE4B_SEED_PROFILE = "phase4b"


class SeedProfileError(ValueError):
    """profile 未知、内容漂移或业务边际不闭合时的稳定失败。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class SeedProfile:
    """已经校验的 recipe 与身份；``payload`` 只读消费，不在运行中修补。"""

    alias: str
    family: str
    version: str
    content_identity: str
    profile_identity: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RefundFactRow:
    """三组边际分布相交后的单条行级净退款事实。"""

    month: str
    reason: str
    channel_name: str
    sku: str
    amount: Decimal


def _load_json(path: Path) -> dict[str, Any]:
    """读取 profile JSON，并把 IO/编码/解析问题收敛成稳定错误。"""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SeedProfileError("seed_profile_unavailable", str(exc)) from exc
    if not isinstance(value, dict):
        raise SeedProfileError("seed_profile_invalid", "profile 顶层必须是 object")
    return value


def load_phase4b_seed_profile(
    path: Path = DEFAULT_PROFILE_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> SeedProfile:
    """验证 source/manifest 和四组金额边际，返回内容绑定身份。"""

    payload = _load_json(path)
    manifest = _load_json(manifest_path)
    expected_root = {
        "profile_family", "profile_version", "profile_alias", "recipe_identity", "snapshot_at",
        "batch_id", "config_identity", "months", "negative_correction",
    }
    if set(payload) != expected_root:
        raise SeedProfileError("seed_profile_invalid", "profile 字段不闭合")
    content_identity = canonical_hash(payload)
    if manifest != {"profile_family": payload["profile_family"], "content_identity": content_identity}:
        raise SeedProfileError("seed_profile_identity_mismatch", "profile source 与 manifest 不一致")
    if payload["profile_alias"] != PHASE4B_SEED_PROFILE or set(payload["months"]) != {"2026-07", "2026-08"}:
        raise SeedProfileError("seed_profile_invalid", "alias 或月份不符合 Phase 4B v1")
    for month, facts in payload["months"].items():
        if set(facts) != {"net_refund_amount", "reasons", "channels", "products"}:
            raise SeedProfileError("seed_profile_invalid", f"{month} 事实字段不闭合")
        total = Decimal(facts["net_refund_amount"])
        for dimension in ("reasons", "channels", "products"):
            values = [Decimal(value) for value in facts[dimension].values()]
            if any(value <= 0 for value in values) or sum(values, Decimal("0")) != total:
                raise SeedProfileError("seed_profile_margin_mismatch", f"{month}.{dimension} 不守恒")
    profile_identity = canonical_hash(
        {
            "family": payload["profile_family"],
            "version": payload["profile_version"],
            "recipe": payload["recipe_identity"],
            "content_identity": content_identity,
            "config_identity": payload["config_identity"],
        }
    )
    return SeedProfile(
        alias=payload["profile_alias"], family=payload["profile_family"], version=payload["profile_version"],
        content_identity=content_identity, profile_identity=profile_identity, payload=payload,
    )


def resolve_seed_profile(alias: str) -> SeedProfile | None:
    """解析 closed-world profile；legacy 返回 None，未知值不得静默回退。"""

    normalized = alias.strip().lower()
    if normalized == LEGACY_SEED_PROFILE:
        return None
    if normalized == PHASE4B_SEED_PROFILE:
        return load_phase4b_seed_profile()
    raise SeedProfileError("seed_profile_unknown", alias)


def _category_at(offset: Decimal, margins: Mapping[str, str]) -> str:
    """在累计金额轴上定位维度值；三个维度共享同一轴即可同时满足全部边际。"""

    cursor = Decimal("0")
    for key, raw in margins.items():
        cursor += Decimal(raw)
        if offset < cursor:
            return key
    raise SeedProfileError("seed_profile_margin_mismatch", "累计边际没有覆盖总金额")


def build_refund_fact_rows(profile: SeedProfile) -> tuple[RefundFactRow, ...]:
    """用累计区间交集构造三维 contingency rows，并显式保留一条负数冲销。"""

    rows: list[RefundFactRow] = []
    correction = abs(Decimal(profile.payload["negative_correction"]))
    for month, facts in profile.payload["months"].items():
        boundaries = {Decimal("0"), Decimal(facts["net_refund_amount"])}
        for dimension in ("reasons", "channels", "products"):
            cursor = Decimal("0")
            for value in facts[dimension].values():
                cursor += Decimal(value)
                boundaries.add(cursor)
        ordered = sorted(boundaries)
        month_rows: list[RefundFactRow] = []
        for start, end in zip(ordered, ordered[1:]):
            if end == start:
                continue
            month_rows.append(
                RefundFactRow(
                    month=month,
                    reason=_category_at(start, facts["reasons"]),
                    channel_name=_category_at(start, facts["channels"]),
                    sku=_category_at(start, facts["products"]),
                    amount=end - start,
                )
            )
        # ★ 正负两行使用相同三维坐标：净值和三个边际都不变，但 SQL 必须保留 signed amount。
        first = month_rows[0]
        month_rows[0] = RefundFactRow(first.month, first.reason, first.channel_name, first.sku, first.amount + correction)
        month_rows.insert(1, RefundFactRow(first.month, first.reason, first.channel_name, first.sku, -correction))
        rows.extend(month_rows)
    return tuple(rows)


def append_phase4b_rows(
    session: Session,
    *,
    profile: SeedProfile,
    users: Sequence[User],
    products: Sequence[Product],
    channels: Sequence[Channel],
) -> dict[str, int]:
    """把 profile 行级事实追加到已构建 legacy seed，且只写既有 14 表。"""

    # 步骤 1：隔离 legacy 时间尾巴 ====================================================
    # legacy 订单在 6 月末支付后会按 +4~8 天生成 processed_at，少量自然滑入 7 月。
    # Phase 4B 是独立世界，若不先封住这条尾巴，“追加 12 万”后的真实 SQL 会变成
    # 139,920。这里仅修改显式 phase4b profile 内的 legacy 副本；默认 legacy seed 不变。
    legacy_cutoff = datetime(2026, 7, 1)
    spillovers = session.scalars(
        select(Refund).where(
            Refund.refund_no.like("REF-2026-%"),
            Refund.processed_at >= legacy_cutoff,
        )
    ).all()
    for refund in spillovers:
        refund.processed_at = datetime(2026, 6, 30, 23, 59, 0)
    session.flush()

    # 步骤 2：追加 Phase 4B 行级事实 ================================================
    products_by_sku = {item.sku: item for item in products}
    channels_by_name = {item.channel_name: item for item in channels}
    rows = build_refund_fact_rows(profile)
    orders: list[Order] = []
    items: list[OrderItem] = []
    refunds: list[Refund] = []
    for index, fact in enumerate(rows):
        product = products_by_sku[fact.sku]
        channel = channels_by_name[fact.channel_name]
        month_start = datetime.strptime(f"{fact.month}-01", "%Y-%m-%d")
        processed_at = month_start + timedelta(days=10 + index % 12, hours=index % 6)
        paid_at = processed_at - timedelta(days=4)
        order_amount = abs(fact.amount) + Decimal("100.00")
        order = Order(
            order_no=f"ORD-P4B-{index + 1:04d}", source_order_no=f"SRC-P4B-{index + 1:04d}",
            external_order_no=f"EXT-P4B-{index + 1:04d}", user=users[index % len(users)], product=product,
            channel=channel, order_status="delivered", order_amount=order_amount, shipping_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"), actual_amount=order_amount, quantity=1, paid_at=paid_at,
        )
        item = OrderItem(
            order=order, product=product, line_no=1, quantity=1, unit_price=order_amount,
            line_amount=order_amount, item_discount_amount=Decimal("0.00"), item_actual_amount=order_amount,
            sku_snapshot=product.sku, product_name_snapshot=product.product_name, created_at=paid_at,
        )
        refund = Refund(
            refund_no=f"REF-P4B-{index + 1:04d}", source_order_no=order.source_order_no, order=order,
            order_item=item, user=order.user, product=product, refund_status="completed",
            refund_reason=fact.reason, refund_amount=fact.amount, requested_at=processed_at - timedelta(days=2),
            processed_at=processed_at,
        )
        orders.append(order)
        items.append(item)
        refunds.append(refund)
    session.add_all([*orders, *items, *refunds])
    session.flush()

    snapshot_at = datetime.fromisoformat(str(profile.payload["snapshot_at"]))
    wide_rows: list[OrderWide] = []
    for order in orders:
        refund = order.refunds[0]
        wide_rows.append(
            OrderWide(
                order_id=order.id, order_no=order.order_no, source_order_no=order.source_order_no,
                external_order_no=order.external_order_no, user_id=order.user.id, user_name=order.user.user_name,
                user_status=order.user.status, user_role=order.user.role, product_id=order.product.id,
                sku=order.product.sku, product_name=order.product.product_name,
                primary_product_price=order.product.price, category_id=order.product.category_id,
                category=order.product.category, channel_id=order.channel.id, channel_code=order.channel.channel_code,
                channel_name=order.channel.channel_name, channel_type=order.channel.channel_type,
                order_status=order.order_status, order_amount=order.order_amount, shipping_amount=order.shipping_amount,
                discount_amount=order.discount_amount, actual_amount=order.actual_amount, quantity=order.quantity,
                item_count=1, refund_count=1, total_refund=refund.refund_amount, has_refund=True,
                paid_at=order.paid_at, source_updated_at=order.updated_at or snapshot_at,
                snapshot_at=snapshot_at, batch_id=str(profile.payload["batch_id"]),
            )
        )
    session.add_all(wide_rows)
    session.flush()
    return {
        "orders": len(orders), "order_items": len(items), "refunds": len(refunds),
        "orders_wide": len(wide_rows), "legacy_spillovers_retimed": len(spillovers),
    }


def verify_phase4b_business_facts(session: Session, *, profile: SeedProfile) -> dict[str, Any]:
    """用真实 SQL 计算 Phase 4B oracle；不从 recipe 原样回显期望值。"""

    result: dict[str, Any] = {"months": {}}
    for month in ("2026-07", "2026-08"):
        start = datetime.strptime(f"{month}-01", "%Y-%m-%d")
        end = datetime(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
        base = (Refund.refund_status == "completed", Refund.processed_at >= start, Refund.processed_at < end)
        total = session.execute(select(func.sum(Refund.refund_amount)).where(*base)).scalar_one()
        reasons = dict(session.execute(select(Refund.refund_reason, func.sum(Refund.refund_amount)).where(*base).group_by(Refund.refund_reason)).all())
        channels = dict(session.execute(select(Channel.channel_name, func.sum(Refund.refund_amount)).join(Order, Order.channel_id == Channel.id).join(Refund, Refund.order_id == Order.id).where(*base).group_by(Channel.channel_name)).all())
        products = dict(session.execute(select(Product.sku, func.sum(Refund.refund_amount)).join(Refund, Refund.product_id == Product.id).where(*base).group_by(Product.sku)).all())
        result["months"][month] = {"net_refund_amount": total, "reasons": reasons, "channels": channels, "products": products}
    batch_id = str(profile.payload["batch_id"])
    wide_total = session.execute(select(func.sum(OrderWide.total_refund)).where(OrderWide.batch_id == batch_id)).scalar_one()
    star_total = sum((item["net_refund_amount"] for item in result["months"].values()), Decimal("0"))
    negative_count = session.execute(select(func.count(Refund.id)).where(Refund.refund_no.like("REF-P4B-%"), Refund.refund_amount < 0)).scalar_one()
    result.update({"wide_matches_star_total": wide_total == star_total, "negative_correction_count": negative_count})
    result["oracle_identity"] = canonical_hash(
        {
            "profile_identity": profile.profile_identity,
            "facts": {
                month: {
                    "net_refund_amount": str(values["net_refund_amount"]),
                    "reasons": {key: str(value) for key, value in sorted(values["reasons"].items())},
                    "channels": {key: str(value) for key, value in sorted(values["channels"].items())},
                    "products": {key: str(value) for key, value in sorted(values["products"].items())},
                }
                for month, values in result["months"].items()
            },
            "wide_matches_star_total": result["wide_matches_star_total"],
            "negative_correction_count": result["negative_correction_count"],
        }
    )
    return result
