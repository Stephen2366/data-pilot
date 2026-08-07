"""种子数据脚本：生成 Phase 2.7 的 14 表确定性业务数据。

★ 这个文件是 DataPilot 数据底座的“数据工厂”，不是静态 SQL dump。所有 1 万级订单、
订单明细、优惠券、行为日志和固定事实都由稳定规则生成，重跑可复现，也不依赖自增 ID
从 1 开始。命令行：`python -m scripts.seed_data --reset`。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from sqlalchemy import case, create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base  # noqa: F401  # 先注册 metadata，避免 app.models 聚合包循环导入。
from app.models import (
    Channel,
    Coupon,
    KnowledgeDoc,
    Order,
    OrderCoupon,
    OrderItem,
    OrderWide,
    Product,
    ProductCategory,
    ProductPriceHistory,
    Refund,
    Ticket,
    User,
    UserBehaviorLog,
)

EXPECTED_SEED_COUNTS = {
    "users": 200,
    "product_categories": 15,
    "products": 50,
    "channels": 6,
    "orders": 10_000,
    "order_items": 18_000,
    "refunds": 1_000,
    "tickets": 300,
    "knowledge_docs": 10,
    "coupons": 10,
    "order_coupons": 3_000,
    "user_behavior_log": 10_000,
    "product_price_history": 150,
    "orders_wide": 10_000,
}

# ★ 这 4 个角色来自 Phase 2 的 RBAC 设计，M4 会继续用它们做权限矩阵。
REQUIRED_ROLES = {"admin", "ops", "customer_service", "demo_user"}
SEED_SUMMARY_PATH = Path(".agent_work/temp/database-upgrade-seed-summary.md")
MONEY = Decimal("0.01")


def _money(value: Decimal | int | str) -> Decimal:
    """统一金额四舍五入，避免 Decimal 口径散在各个构造函数里。"""

    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def seed_database(session: Session, reset_existing: bool = False) -> dict[str, Any]:
    """向已迁移完成的数据库中填充确定性模拟业务数据。

    参数说明：
    - session：外部传入事务会话，测试、eval 和命令行共用同一入口。
    - reset_existing：为 True 时按外键依赖顺序清空 14 张物理表；不重置自增 ID。
    """

    if reset_existing:
        _delete_existing_rows(session)

    categories = _build_product_categories()
    users = _build_users()
    channels = _build_channels()
    products = _build_products(categories)
    docs = _build_knowledge_docs()
    coupons = _build_coupons()
    price_history = _build_product_price_history(products)

    session.add_all([*categories, *users, *channels, *products, *docs, *coupons, *price_history])
    session.flush()

    orders, order_items = _build_orders_and_items(users=users, products=products, channels=channels)
    session.add_all([*orders, *order_items])
    session.flush()

    order_coupons = _build_order_coupons(orders=orders, coupons=coupons)
    session.add_all(order_coupons)
    session.flush()

    refunds = _build_refunds(orders)
    tickets = _build_tickets(users=users, orders=orders)
    behavior_logs = _build_user_behavior_logs(users=users, products=products, channels=channels)
    session.add_all([*refunds, *tickets, *behavior_logs])
    session.flush()

    orders_wide = _build_orders_wide(orders)
    session.add_all(orders_wide)
    session.commit()

    summary = {
        "counts": _count_seed_tables(session),
        "roles": sorted({user.role for user in users}),
        "facts": verify_business_facts(session),
    }
    _write_seed_summary(summary)
    return summary


def verify_business_facts(session: Session) -> dict[str, Any]:
    """查询 Phase 2.7 的固定业务事实，供测试、smoke 和后续 eval 复用。

    ★ 固定事实不用自增 ID 定位，只用商品名、SKU、coupon_code、channel_code 等稳定业务键。
    """

    june_start = datetime(2026, 6, 1)
    july_start = datetime(2026, 7, 1)
    valid_order_filter = (
        Order.paid_at >= june_start,
        Order.paid_at < july_start,
        Order.order_status.notin_(["cancelled", "canceled"]),
    )

    gmv = session.execute(
        select(func.round(func.sum(Order.order_amount), 2)).where(*valid_order_filter)
    ).scalar_one()

    # ★ 商品退款率不能走 orders.product_id：一单多商品时会把退款归给“主商品”。
    # 明细退款按 order_item 归因；整单退款没有明细时，只能使用退款表保存的 product_id 回退。
    eligible_order_items = (
        select(OrderItem.order_id, OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(*valid_order_filter)
        .cte("eligible_order_items")
    )
    refunds_by_product = (
        select(
            func.coalesce(OrderItem.product_id, Refund.product_id).label("product_id"),
            func.count(func.distinct(Refund.order_id)).label("refunded_order_count"),
        )
        .join(Order, Order.id == Refund.order_id)
        .outerjoin(OrderItem, OrderItem.id == Refund.order_item_id)
        .where(
            *valid_order_filter,
            Refund.refund_status == "completed",
            func.coalesce(OrderItem.product_id, Refund.product_id).is_not(None),
        )
        .group_by(func.coalesce(OrderItem.product_id, Refund.product_id))
        .cte("refunds_by_product")
    )
    refund_rate_stmt = (
        select(
            Product.product_name,
            (
                func.coalesce(refunds_by_product.c.refunded_order_count, 0) * 1.0
                / func.count(func.distinct(eligible_order_items.c.order_id))
            ).label("refund_rate"),
        )
        .join(eligible_order_items, eligible_order_items.c.product_id == Product.id)
        .outerjoin(refunds_by_product, refunds_by_product.c.product_id == Product.id)
        .group_by(Product.id, Product.product_name, refunds_by_product.c.refunded_order_count)
        .order_by(
            (
                func.coalesce(refunds_by_product.c.refunded_order_count, 0) * 1.0
                / func.count(func.distinct(eligible_order_items.c.order_id))
            ).desc(),
            Product.product_name.asc(),
        )
        .limit(1)
    )
    highest_refund_rate_product = session.execute(refund_rate_stmt).scalar_one()

    top_channel_stmt = (
        select(Channel.channel_name, func.sum(Order.order_amount).label("gmv"))
        .join(Order, Order.channel_id == Channel.id)
        .where(*valid_order_filter)
        .group_by(Channel.id, Channel.channel_name)
        .order_by(func.sum(Order.order_amount).desc(), Channel.channel_name.asc())
        .limit(1)
    )
    top_gmv_channel = session.execute(top_channel_stmt).scalar_one()

    reason_stmt = (
        select(Refund.refund_reason, func.count(Refund.id).label("refund_count"))
        .group_by(Refund.refund_reason)
        .order_by(func.count(Refund.id).desc(), Refund.refund_reason.asc())
        .limit(1)
    )
    top_refund_reason = session.execute(reason_stmt).scalar_one()

    pending_ticket_stmt = select(func.count(Ticket.id)).where(Ticket.status == "pending", Ticket.priority == "high")
    pending_high_priority_tickets = session.execute(pending_ticket_stmt).scalar_one()

    coupon_channel_stmt = (
        select(Channel.channel_name, func.count(func.distinct(Order.id)).label("usage_count"))
        .join(Order, Order.channel_id == Channel.id)
        .join(OrderCoupon, OrderCoupon.order_id == Order.id)
        .join(Coupon, Coupon.id == OrderCoupon.coupon_id)
        .where(Coupon.coupon_code == "JUNE_FIXED_50")
        .group_by(Channel.id, Channel.channel_name)
        .order_by(func.count(func.distinct(Order.id)).desc(), Channel.channel_name.asc())
        .limit(1)
    )
    june_fixed_coupon_top_channel = session.execute(coupon_channel_stmt).scalar_one()

    category_stmt = (
        select(Product.category, func.sum(OrderItem.line_amount).label("category_gmv"))
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(*valid_order_filter)
        .group_by(Product.category)
        .order_by(func.sum(OrderItem.line_amount).desc(), Product.category.asc())
        .limit(1)
    )
    top_root_category = session.execute(category_stmt).scalar_one()

    aurora_price_stmt = (
        select(func.round(func.avg(ProductPriceHistory.price), 2))
        .join(Product, Product.id == ProductPriceHistory.product_id)
        .where(
            Product.sku == "SKU-HIGH-REFUND-01",
            ProductPriceHistory.valid_from < july_start,
            (ProductPriceHistory.valid_to.is_(None)) | (ProductPriceHistory.valid_to > june_start),
        )
    )
    aurora_avg_price = session.execute(aurora_price_stmt).scalar_one()

    conversion_stmt = (
        select(
            UserBehaviorLog.device_type,
            (
                func.sum(case((UserBehaviorLog.event_type == "payment_success", 1), else_=0))
                * 1.0
                / func.sum(case((UserBehaviorLog.event_type == "add_to_cart", 1), else_=0))
            ).label("conversion_rate"),
        )
        .group_by(UserBehaviorLog.device_type)
        .order_by(
            (
                func.sum(case((UserBehaviorLog.event_type == "payment_success", 1), else_=0))
                * 1.0
                / func.sum(case((UserBehaviorLog.event_type == "add_to_cart", 1), else_=0))
            ).desc(),
            UserBehaviorLog.device_type.asc(),
        )
        .limit(1)
    )
    top_conversion_device = session.execute(conversion_stmt).scalar_one()

    star_gmv = session.execute(
        select(Channel.channel_code, func.round(func.sum(Order.order_amount), 2))
        .join(Order, Order.channel_id == Channel.id)
        .where(*valid_order_filter)
        .group_by(Channel.channel_code)
        .order_by(Channel.channel_code.asc())
    ).all()
    wide_gmv = session.execute(
        select(OrderWide.channel_code, func.round(func.sum(OrderWide.order_amount), 2))
        .where(
            OrderWide.paid_at >= june_start,
            OrderWide.paid_at < july_start,
            OrderWide.order_status.notin_(["cancelled", "canceled"]),
        )
        .group_by(OrderWide.channel_code)
        .order_by(OrderWide.channel_code.asc())
    ).all()

    mismatch_count = session.execute(
        select(func.count())
        .select_from(
            select(Order.id)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .group_by(Order.id, Order.order_amount)
            .having(func.round(func.sum(OrderItem.line_amount) - Order.order_amount, 2) != 0)
            .subquery()
        )
    ).scalar_one()

    return {
        "gmv_june_2026": gmv,
        "highest_refund_rate_product_june_2026": highest_refund_rate_product,
        "top_gmv_channel_june_2026": top_gmv_channel,
        "top_refund_reason": top_refund_reason,
        "pending_high_priority_tickets": pending_high_priority_tickets,
        "june_fixed_50_top_usage_channel": june_fixed_coupon_top_channel,
        "top_root_category_by_gmv_june_2026": top_root_category,
        "aurora_avg_price_june_2026": aurora_avg_price,
        "top_add_to_pay_device_type": top_conversion_device,
        "orders_wide_matches_star_gmv_by_channel": star_gmv == wide_gmv,
        "amount_mismatch_order_count": mismatch_count,
    }


def _delete_existing_rows(session: Session) -> None:
    """按外键依赖顺序清空 14 张物理表，不依赖自增 ID 回到 1。"""

    # ★ product_categories 是自引用类目树。MySQL 会在同表父子外键下拦截整表 DELETE，
    # 所以 reset 时先断开 parent_id，再按父表删除顺序清空。
    session.query(ProductCategory).update({ProductCategory.parent_id: None}, synchronize_session=False)
    session.flush()
    for model in (
        OrderWide,
        UserBehaviorLog,
        Ticket,
        Refund,
        OrderCoupon,
        OrderItem,
        ProductPriceHistory,
        Order,
        Coupon,
        KnowledgeDoc,
        Product,
        ProductCategory,
        Channel,
        User,
    ):
        session.execute(delete(model))
    session.flush()


_USER_NAMES = [
    "陈米娅", "王逸凡", "张雨薇", "李思源", "刘若晴", "黄子轩", "赵晓萌", "吴俊杰", "杨雨桐", "周明哲",
    "徐悦然", "孙博文", "马晓琳", "郭浩然", "林芷若", "何志远", "高语嫣", "唐瑞霖", "程一诺", "罗嘉懿",
    "彭婉清", "潘奕辰", "邓梓涵", "肖景行", "冯书瑶", "石承宇", "任雅静", "万子骞", "杜若溪", "傅正阳",
    "谢安然", "段思齐", "姜语桐", "韩铭远", "秦乐瑶", "廖凯文", "熊芷萱", "崔敬轩", "毕雨晴", "瞿天佑",
    "孔令仪", "阮启航", "侯静怡", "左逸凡", "童雅琪", "顾砚书", "邵灵犀", "裴宇轩", "连以安", "聂朗清",
    "陈澈", "王遥", "张弛", "李想", "刘畅", "黄骁", "赵宁", "吴越", "杨帆", "周砚",
    "徐朗", "孙晴", "马骁", "郭宁", "林溪", "何川", "高岚", "唐栩", "程墨", "罗晗",
    "彭越", "潘澈", "邓楠", "肖遥", "冯澜", "石岩", "任舟", "万宁", "杜衡", "傅野",
    "谢舟", "段然", "姜澈", "韩越", "秦川", "廖宁", "熊辰", "崔遥", "毕然", "瞿墨",
    "孔晴", "阮川", "侯澈", "左言", "童宁", "顾南", "邵岚", "裴然", "连舟", "聂远",
    "苏晚晴", "许知夏", "梁嘉树", "宋若溪", "郑清欢", "蒋明远", "沈亦辰", "韩知意", "曹沐阳", "袁嘉宁",
    "邱景和", "方予安", "孟星河", "丁若初", "邵云起", "陆嘉禾", "白舒然", "贺南星", "夏以沫", "顾星辞",
    "叶清越", "乔安然", "江予白", "尹疏桐", "薛明朗", "戴雨辰", "钟子墨", "汪若琳", "汤嘉懿", "谭亦舟",
    "魏初夏", "邹景行", "丁芷晴", "卢一诺", "姚星辰", "郝思齐", "毛语晨", "钱若楠", "康逸晨", "赖书宁",
    "严清扬", "莫子涵", "章雨眠", "龙嘉泽", "雷沐辰", "辛念初", "伍若宁", "常明熙", "申以安", "葛云舒",
    "林小北", "周小满", "陈一一", "李木子", "王可心", "赵知行", "张之遥", "刘嘉木", "杨若白", "吴念慈",
    "徐简", "孙棠", "马越", "郭一帆", "何以宁", "高予夏", "唐一鸣", "程知远", "罗曼", "彭小雅",
    "Alex Chen", "Emma Wang", "Kevin Liu", "Olivia Zhang", "Jason Li", "Mia Huang", "Leo Zhao", "Grace Wu", "Daniel Yang", "Sophia Zhou",
    "Aaron Xu", "Nina Sun", "Eric Ma", "Ivy Guo", "Ryan Lin", "Chloe He", "Victor Gao", "Luna Tang", "Ethan Cheng", "Ruby Luo",
    "沈清和", "陆明轩", "许安乔", "梁若安", "宋知微", "郑子衿", "蒋云深", "曹嘉许", "袁可为", "邱雨棠",
]


def _build_users() -> list[User]:
    """构建 200 个用户，包含少量 disabled 用户但仍保留历史订单。"""

    roles = ["admin", "ops", "customer_service", "demo_user"]
    users: list[User] = []
    for index in range(EXPECTED_SEED_COUNTS["users"]):
        # ★ 用户名直接来自 200 个固定姓名池，混合二字名、三字名和少量英文名，兼顾真实感与可复现。
        user_name = _USER_NAMES[index]
        users.append(
            User(
                user_name=user_name,
                role=roles[index % len(roles)],
                email=f"user{index + 1:03d}@datapilot.example",
                phone=f"138{index + 1:08d}",
                status="disabled" if index in {11, 47, 113, 179} else "active",
            )
        )
    return users


def _build_product_categories() -> list[ProductCategory]:
    """构建 15 个类目节点，形成 3 层树。"""

    roots = {
        "数码电子": ProductCategory(name="数码电子", level=1, sort_order=10),
        "家居生活": ProductCategory(name="家居生活", level=1, sort_order=20),
        "个护美妆": ProductCategory(name="个护美妆", level=1, sort_order=30),
        "户外运动": ProductCategory(name="户外运动", level=1, sort_order=40),
        "SaaS 软件": ProductCategory(name="SaaS 软件", level=1, sort_order=50),
    }
    children = [
        ProductCategory(name="手机通讯", parent=roots["数码电子"], level=2, sort_order=11),
        ProductCategory(name="电脑办公", parent=roots["数码电子"], level=2, sort_order=12),
        ProductCategory(name="智能穿戴", parent=roots["数码电子"], level=2, sort_order=13),
        ProductCategory(name="家纺", parent=roots["家居生活"], level=2, sort_order=21),
        ProductCategory(name="厨具", parent=roots["家居生活"], level=2, sort_order=22),
        ProductCategory(name="护肤", parent=roots["个护美妆"], level=2, sort_order=31),
        ProductCategory(name="彩妆", parent=roots["个护美妆"], level=2, sort_order=32),
        ProductCategory(name="露营装备", parent=roots["户外运动"], level=2, sort_order=41),
    ]
    grandchildren = [
        ProductCategory(name="笔记本", parent=children[1], level=3, sort_order=121),
        ProductCategory(name="台式机", parent=children[1], level=3, sort_order=122),
    ]
    return [*roots.values(), *children, *grandchildren]


_PRODUCT_SPECS: list[tuple[str, str, str, Decimal]] = [
    ("SKU-HIGH-REFUND-01", "Aurora Noise Cancelling Headphones", "智能穿戴", Decimal("899.00")),
    ("SKU-WL-EB-002", "真无线降噪耳机 Pro", "智能穿戴", Decimal("399.00")),
    ("SKU-SD-LP-003", "智能护眼台灯", "家纺", Decimal("249.00")),
    ("SKU-MK-K2-004", "机械键盘 K2 红轴", "电脑办公", Decimal("549.00")),
    ("SKU-MS-PL-005", "记忆棉护颈枕", "家纺", Decimal("179.00")),
    ("SKU-VC-SR-006", "VC 焕白精华液 30ml", "护肤", Decimal("128.00")),
    ("SKU-CRM-ST-007", "CRM 入门版（月付）", "SaaS 软件", Decimal("299.00")),
    ("SKU-HB-45-008", "户外登山包 45L", "露营装备", Decimal("459.00")),
    ("SKU-4K-WC-009", "4K 高清摄像头", "电脑办公", Decimal("679.00")),
    ("SKU-BM-SH-010", "楠竹置物架三层", "家纺", Decimal("189.00")),
    ("SKU-HA-TN-011", "玻尿酸保湿爽肤水", "护肤", Decimal("98.00")),
    ("SKU-AN-PR-012", "Analytics Pro（月付）", "SaaS 软件", Decimal("599.00")),
    ("SKU-CT-2P-013", "双人露营帐篷 防暴雨", "露营装备", Decimal("899.00")),
    ("SKU-UG-CG-014", "氮化镓快充头 65W", "手机通讯", Decimal("149.00")),
    ("SKU-AR-DR-015", "超声波香薰机 Mini", "家纺", Decimal("139.00")),
    ("SKU-SP-FD-016", "清爽防晒日霜 SPF50", "护肤", Decimal("158.00")),
    ("SKU-MK-ST-017", "全渠道营销套件入门版", "SaaS 软件", Decimal("899.00")),
    ("SKU-UL-TT-018", "超轻徒步帐篷 单人", "露营装备", Decimal("1299.00")),
    ("SKU-BT-SK-019", "便携蓝牙音箱 Mini", "智能穿戴", Decimal("219.00")),
    ("SKU-SL-PL-020", "真丝枕套套装 一对装", "家纺", Decimal("99.00")),
    ("SKU-RT-MK-021", "视黄醇抗皱面霜", "护肤", Decimal("189.00")),
    ("SKU-CS-PT-022", "智能客服 Pro（月付）", "SaaS 软件", Decimal("399.00")),
    ("SKU-PC-JK-023", "便携轻薄羽绒服", "露营装备", Decimal("549.00")),
    ("SKU-TB-PS-024", "铝合金平板支架", "电脑办公", Decimal("79.00")),
    ("SKU-CX-FM-025", "纯棉针织盖毯", "家纺", Decimal("159.00")),
    ("SKU-CC-CM-026", "校色遮瑕膏 三色盘", "彩妆", Decimal("109.00")),
    ("SKU-WH-PL-027", "仓储管理 Pro（月付）", "SaaS 软件", Decimal("699.00")),
    ("SKU-FS-RD-028", "碳素台钓竿 2.4m", "露营装备", Decimal("329.00")),
    ("SKU-KS-SC-029", "儿童智能手表", "智能穿戴", Decimal("259.00")),
    ("SKU-RC-CK-030", "迷你电饭煲 3 杯量", "厨具", Decimal("119.00")),
    ("SKU-NB-AIR-031", "轻薄商务笔记本 14 寸", "笔记本", Decimal("4699.00")),
    ("SKU-DT-MINI-032", "迷你主机 i5 办公版", "台式机", Decimal("2999.00")),
    ("SKU-MB-5G-033", "5G 商务手机 SE", "手机通讯", Decimal("2199.00")),
    ("SKU-WT-HR-034", "心率监测运动手环", "智能穿戴", Decimal("299.00")),
    ("SKU-KT-POT-035", "不粘锅三件套", "厨具", Decimal("329.00")),
    ("SKU-BD-QT-036", "四季纯棉被套", "家纺", Decimal("229.00")),
    ("SKU-SK-MA-037", "修护面膜 20 片装", "护肤", Decimal("169.00")),
    ("SKU-MU-LP-038", "丝绒哑光口红套装", "彩妆", Decimal("199.00")),
    ("SKU-CM-CH-039", "折叠露营椅", "露营装备", Decimal("269.00")),
    ("SKU-SA-BI-040", "BI 报表企业版（月付）", "SaaS 软件", Decimal("1299.00")),
    ("SKU-SA-ETL-041", "数据同步基础版（月付）", "SaaS 软件", Decimal("499.00")),
    ("SKU-DS-MON-042", "27 寸 4K 显示器", "电脑办公", Decimal("1799.00")),
    ("SKU-DS-MOU-043", "静音无线鼠标", "电脑办公", Decimal("129.00")),
    ("SKU-PH-CASE-044", "抗摔手机壳", "手机通讯", Decimal("69.00")),
    ("SKU-PH-PWR-045", "磁吸充电宝 10000mAh", "手机通讯", Decimal("199.00")),
    ("SKU-KT-RICE-046", "低糖电饭煲 4L", "厨具", Decimal("499.00")),
    ("SKU-BD-PIL-047", "乳胶枕经典款", "家纺", Decimal("299.00")),
    ("SKU-SK-ESS-048", "烟酰胺精华组合", "护肤", Decimal("259.00")),
    ("SKU-MU-FDN-049", "持妆粉底液", "彩妆", Decimal("189.00")),
    ("SKU-CM-LAMP-050", "营地充电照明灯", "露营装备", Decimal("239.00")),
]


def _root_category_name(category: ProductCategory) -> str:
    """从任意层级类目向上找到一级类目名称，用于保留 products.category 冗余字段。"""

    current = category
    while current.parent is not None:
        current = current.parent
    return current.name


def _build_products(categories: list[ProductCategory]) -> list[Product]:
    """构建 50 个商品，category_id 指向规范化类目，category 保留一级类目冗余。"""

    category_by_name = {category.name: category for category in categories}
    products: list[Product] = []
    for index, (sku, name, category_name, price) in enumerate(_PRODUCT_SPECS):
        category = category_by_name[category_name]
        products.append(
            Product(
                sku=sku,
                product_name=name,
                category_ref=category,
                category=_root_category_name(category),
                status="paused" if index in {17, 35, 48} else "active",
                price=price,
                launched_at=datetime(2026, 1, 1) + timedelta(days=index * 2),
            )
        )
    return products


def _build_channels() -> list[Channel]:
    """构建 6 个渠道，沿用 Phase 2 的业务键和展示名。"""

    return [
        Channel(channel_code="mobile_app", channel_name="Mobile App", channel_type="owned"),
        Channel(channel_code="web_store", channel_name="Web Store", channel_type="owned"),
        Channel(channel_code="tmall", channel_name="Tmall", channel_type="marketplace"),
        Channel(channel_code="jd", channel_name="JD", channel_type="marketplace"),
        Channel(channel_code="douyin", channel_name="Douyin", channel_type="paid"),
        Channel(channel_code="partner", channel_name="Partner", channel_type="partner"),
    ]


def _build_coupons() -> list[Coupon]:
    """构建 10 张优惠券，其中 JUNE_FIXED_50 是固定事实锚点。"""

    valid_from = datetime(2026, 5, 20)
    valid_to = datetime(2026, 7, 5)
    specs = [
        ("JUNE_FIXED_50", "六月满 300 减 50", "fixed_amount", Decimal("50.00"), Decimal("300.00")),
        ("FREESHIP_JUNE", "六月免运费券", "free_shipping", Decimal("18.00"), Decimal("99.00")),
        ("VIP_100_OFF", "VIP 满 800 减 100", "fixed_amount", Decimal("100.00"), Decimal("800.00")),
        ("APP_ONLY_30", "App 专享减 30", "fixed_amount", Decimal("30.00"), Decimal("199.00")),
        ("BEAUTY_20", "美妆护理减 20", "fixed_amount", Decimal("20.00"), Decimal("99.00")),
        ("SAAS_TRIAL_80", "SaaS 新客减 80", "fixed_amount", Decimal("80.00"), Decimal("399.00")),
        ("OUTDOOR_60", "户外装备减 60", "fixed_amount", Decimal("60.00"), Decimal("499.00")),
        ("HOME_25", "家居生活减 25", "fixed_amount", Decimal("25.00"), Decimal("159.00")),
        ("DIGITAL_5PCT", "数码 95 折券", "percentage", Decimal("5.00"), Decimal("499.00")),
        ("RETENTION_40", "沉默用户唤醒减 40", "fixed_amount", Decimal("40.00"), Decimal("199.00")),
    ]
    return [
        Coupon(
            coupon_code=code,
            coupon_name=name,
            coupon_type=coupon_type,
            discount_value=value,
            min_order_amount=min_amount,
            status="active",
            valid_from=valid_from,
            valid_to=valid_to,
        )
        for code, name, coupon_type, value, min_amount in specs
    ]


def _build_orders_and_items(
    *, users: list[User], products: list[Product], channels: list[Channel]
) -> tuple[list[Order], list[OrderItem]]:
    """构建 1 万订单头和 1.8 万订单明细。"""

    products_by_sku = {product.sku: product for product in products}
    aurora = products_by_sku["SKU-HIGH-REFUND-01"]
    digital_products = [product for product in products if product.category == "数码电子"]
    non_anchor_products = [product for product in products if product is not aurora]
    june_start = datetime(2026, 6, 1, 9, 0, 0)
    may_start = datetime(2026, 5, 1, 9, 0, 0)
    orders: list[Order] = []
    order_items: list[OrderItem] = []

    for index in range(EXPECTED_SEED_COUNTS["orders"]):
        paid_at = None if index < 20 else (june_start if index < 7_000 else may_start) + timedelta(
            days=index % 28,
            hours=index % 9,
            minutes=index % 37,
        )
        if paid_at is None:
            status = "pending_payment"
        elif index < 300:
            status = "delivered"
        elif 300 <= index < 308:
            status = "canceled"
        elif index % 23 == 0:
            status = "cancelled"
        else:
            status = ["paid", "shipped", "delivered"][index % 3]

        channel = channels[0] if index < 4_500 else channels[(index % (len(channels) - 1)) + 1]
        primary_product = aurora if index < 300 else (
            digital_products[index % len(digital_products)] if index % 5 in {0, 1, 2} else non_anchor_products[index % len(non_anchor_products)]
        )
        item_count = 1 if index % 10 < 4 else 2 if index % 10 < 8 else 3
        selected_products = [primary_product]
        for offset in range(1, item_count):
            selected_products.append(non_anchor_products[(index + offset * 7) % len(non_anchor_products)])

        line_amount_total = Decimal("0.00")
        quantity_total = 0
        order = Order(
            order_no=f"ORD-2026-{index + 1:05d}",
            source_order_no=f"SRC-2026-{(index // 2) + 1:05d}" if 100 <= index < 120 else f"SRC-2026-{index + 1:05d}",
            external_order_no=f"EXT-MKT-{(index // 2) + 1:05d}" if 100 <= index < 120 else f"EXT-MKT-{index + 1:05d}",
            user=users[index % len(users)],
            product=primary_product,
            channel=channel,
            order_status=status,
            order_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00") if index % 7 == 0 else Decimal("12.00") + Decimal(index % 4) * Decimal("3.00"),
            discount_amount=Decimal("0.00"),
            actual_amount=Decimal("0.00"),
            quantity=0,
            paid_at=paid_at,
        )

        for line_no, product in enumerate(selected_products, start=1):
            quantity = 1 + ((index + line_no) % 3 == 0)
            unit_price = _money(product.price + Decimal(index % 4) * Decimal("3.00"))
            line_amount = _money(unit_price * Decimal(quantity))
            line_amount_total += line_amount
            quantity_total += quantity
            order_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    line_no=line_no,
                    quantity=quantity,
                    unit_price=unit_price,
                    line_amount=line_amount,
                    item_discount_amount=Decimal("0.00"),
                    item_actual_amount=line_amount,
                    sku_snapshot=product.sku,
                    product_name_snapshot=product.product_name,
                    created_at=paid_at or datetime(2026, 6, 1, 8, 0, 0),
                )
            )

        # DQ-04：末尾 5 单故意制造订单头金额和明细汇总不一致，不影响核心 6 月锚点。
        order.order_amount = _money(line_amount_total + (Decimal("10.00") if index >= 9_995 else Decimal("0.00")))
        order.quantity = quantity_total
        order.actual_amount = _money(order.order_amount + order.shipping_amount - order.discount_amount)
        orders.append(order)

    return orders, order_items


def _build_order_coupons(*, orders: list[Order], coupons: list[Coupon]) -> list[OrderCoupon]:
    """构建 3000 条订单优惠券关系，并回写订单折扣与实付金额。"""

    coupons_by_code = {coupon.coupon_code: coupon for coupon in coupons}
    result: list[OrderCoupon] = []
    used_order_coupon_pairs: set[tuple[int, str]] = set()

    def attach(order: Order, coupon_code: str, amount: Decimal) -> None:
        pair = (id(order), coupon_code)
        if pair in used_order_coupon_pairs:
            return
        used_order_coupon_pairs.add(pair)
        coupon = coupons_by_code[coupon_code]
        discount = min(_money(amount), _money(order.order_amount + order.shipping_amount))
        order.discount_amount = _money(order.discount_amount + discount)
        order.actual_amount = _money(order.order_amount + order.shipping_amount - order.discount_amount)
        result.append(
            OrderCoupon(
                order=order,
                coupon=coupon,
                discount_amount=discount,
                applied_at=order.paid_at or datetime(2026, 6, 1, 8, 0, 0),
            )
        )

    for index, order in enumerate(orders):
        if len(result) >= EXPECTED_SEED_COUNTS["order_coupons"]:
            break
        if index < 650 and order.channel.channel_code == "mobile_app":
            attach(order, "JUNE_FIXED_50", Decimal("50.00"))
        elif index % 4 == 0:
            attach(order, "FREESHIP_JUNE", min(order.shipping_amount, Decimal("18.00")))
        elif index % 5 == 0:
            attach(order, "APP_ONLY_30", Decimal("30.00"))
        elif index % 7 == 0:
            attach(order, "DIGITAL_5PCT", _money(order.order_amount * Decimal("0.05")))
        elif index % 9 == 0:
            attach(order, "RETENTION_40", Decimal("40.00"))

    # 不足 3000 时继续补稳定优惠券，保证行数精确。
    cursor = 0
    fill_codes = ["HOME_25", "BEAUTY_20", "SAAS_TRIAL_80", "OUTDOOR_60", "VIP_100_OFF"]
    while len(result) < EXPECTED_SEED_COUNTS["order_coupons"]:
        order = orders[cursor % len(orders)]
        attach(order, fill_codes[cursor % len(fill_codes)], Decimal("20.00") + Decimal(cursor % 5) * Decimal("5.00"))
        cursor += 1
    return result


def _build_refunds(orders: list[Order]) -> list[Refund]:
    """构建 1000 条退款，优先指向订单明细，同时保留少量整单退款。"""

    refunds: list[Refund] = []
    statuses = ["approved", "completed", "requested", "rejected"]
    reasons = ["quality_issue"] * 420 + ["late_delivery"] * 210 + ["wrong_item"] * 160 + ["changed_mind"] * 130 + ["price_protection"] * 80
    refund_orders = [order for order in orders[:260] if order.paid_at is not None]
    refund_orders.extend(order for order in orders[500:500 + EXPECTED_SEED_COUNTS["refunds"] - len(refund_orders)])

    for index, order in enumerate(refund_orders[: EXPECTED_SEED_COUNTS["refunds"]]):
        order_item = order.order_items[0] if index % 10 != 0 else None
        amount = _money((order_item.item_actual_amount if order_item else order.actual_amount) * Decimal("0.80"))
        if index >= EXPECTED_SEED_COUNTS["refunds"] - 3:
            amount = Decimal("-20.00")
        refunds.append(
            Refund(
                refund_no=f"REF-2026-{index + 1:05d}",
                source_order_no=f"SRC-MISSING-{index + 1:03d}" if index < 5 else order.source_order_no,
                order=order,
                order_item=order_item,
                user=order.user,
                product=(order_item.product if order_item else order.product),
                refund_status=statuses[index % len(statuses)],
                refund_reason=reasons[index],
                refund_amount=amount,
                requested_at=(order.paid_at or datetime(2026, 6, 1)) + timedelta(days=2 + index % 5),
                processed_at=((order.paid_at or datetime(2026, 6, 1)) + timedelta(days=4 + index % 5)) if index % 4 != 2 else None,
            )
        )
    return refunds


_TICKET_SUBJECTS: dict[str, list[str]] = {
    "refund": ["质量问题申请退款", "退货后未收到退款", "价保补差申请", "退款审核进度咨询"],
    "shipping": ["物流 72 小时未更新", "收货地址需要修改", "包裹签收异常", "部分商品漏发"],
    "invoice": ["电子发票抬头修改", "专票资质审核", "发票金额与实付不符", "合并开票申请"],
    "account": ["手机号换绑申请", "账号登录失败", "会员积分异常", "默认地址无法修改"],
    "product_quality": ["商品缺少说明书", "耳机降噪效果异常", "SaaS 权限不一致", "电饭煲内胆涂层问题"],
}


def _build_tickets(*, users: list[User], orders: list[Order]) -> list[Ticket]:
    """构建 300 条客服工单，保留 12 个 pending high 锚点。"""

    service_users = [user for user in users if user.role == "customer_service"]
    ticket_types = ["refund"] * 80 + ["shipping"] * 75 + ["invoice"] * 55 + ["account"] * 45 + ["product_quality"] * 45
    tickets: list[Ticket] = []
    for index in range(EXPECTED_SEED_COUNTS["tickets"]):
        ticket_type = ticket_types[index]
        is_anchor = index < 12
        status = "pending" if is_anchor else ["processing", "resolved", "closed"][index % 3]
        priority = "high" if is_anchor else ["low", "medium", "urgent"][index % 3]
        created_at = datetime(2026, 6, 1, 10, 0, 0) + timedelta(hours=index * 2)
        subject = _TICKET_SUBJECTS[ticket_type][index % len(_TICKET_SUBJECTS[ticket_type])]
        tickets.append(
            Ticket(
                ticket_no=f"TCK-2026-{index + 1:05d}",
                user=users[index % len(users)],
                order=orders[(index * 13) % len(orders)] if index % 5 != 0 else None,
                assigned_user=service_users[index % len(service_users)],
                ticket_type=ticket_type,
                priority=priority,
                status=status,
                subject=subject,
                description=f"用户 {users[index % len(users)].user_name} 提交工单：{subject}。请客服团队根据 SLA 优先级处理。",
                resolved_at=None if status in {"pending", "processing"} else created_at + timedelta(days=2),
                created_at=created_at,
            )
        )
    return tickets


def _build_user_behavior_logs(*, users: list[User], products: list[Product], channels: list[Channel]) -> list[UserBehaviorLog]:
    """构建 1 万条行为日志，mobile_app 设备加购到支付转化率最高。"""

    device_events = {
        "mobile_app": (1200, 800, 560, 440),
        "desktop_web": (1300, 650, 260, 290),
        "mobile_web": (1250, 600, 210, 240),
        "mini_program": (1150, 550, 190, 310),
    }
    event_names = ["view_product", "add_to_cart", "payment_success", "search"]
    logs: list[UserBehaviorLog] = []
    event_time = datetime(2026, 6, 1, 8, 0, 0)
    for device, counts in device_events.items():
        for event_name, count in zip(event_names, counts, strict=True):
            for offset in range(count):
                index = len(logs)
                logs.append(
                    UserBehaviorLog(
                        user=users[index % len(users)],
                        product=products[index % len(products)] if event_name != "search" else None,
                        channel=channels[0] if device == "mobile_app" else channels[(index % (len(channels) - 1)) + 1],
                        session_id=f"SES-{device}-{offset % 1800:05d}",
                        event_type=event_name,
                        device_type=device,
                        page_url=f"/products/{products[index % len(products)].sku}" if event_name != "search" else "/search",
                        referrer=["organic", "paid_search", "push", "email"][index % 4],
                        duration_ms=None if index % 10 == 0 else 300 + (index % 200) * 17,
                        event_time=event_time + timedelta(minutes=index % 43, seconds=index % 59),
                    )
                )
    return logs


def _build_product_price_history(products: list[Product]) -> list[ProductPriceHistory]:
    """为每个商品构建 3 段价格历史，总计 150 行。"""

    rows: list[ProductPriceHistory] = []
    for index, product in enumerate(products):
        base_price = _money(product.price)
        historical = [
            (
                datetime(2026, 1, 1),
                datetime(2026, 4, 1),
                _money(base_price * Decimal("0.92")),
                "new_year_clearance",
            ),
            (datetime(2026, 4, 1), datetime(2026, 7, 1), _money(base_price), "spring_price_restore"),
            (
                datetime(2026, 7, 1),
                None,
                _money(base_price + (Decimal("12.00") if index in {3, 9} else Decimal("0.00"))),
                "summer_price_refresh" if index in {3, 9} else "current_price",
            ),
        ]
        for valid_from, valid_to, price, change_reason in historical:
            rows.append(
                ProductPriceHistory(
                    product=product,
                    price=price,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    is_current=valid_to is None,
                    price_source="seed",
                    change_reason=change_reason,
                )
            )
    return rows


_KB_CONTENTS: dict[str, tuple[str, str, str, str]] = {
    "refund_policy_basic": ("基础退款政策", "refund_policy", "customer_service", "支持 7 天无理由、质量问题、物流损坏和价保补差。质量问题退款需提供照片、订单号和必要视频，审核通过后原路退款。"),
    "refund_policy_quality": ("质量问题退款规则", "refund_policy", "customer_service", "质量问题包括功能故障、外观严重瑕疵、保质期异常和配件缺失。平台质检确认后全额退款并补偿优惠券。"),
    "shipping_delay_rule": ("物流延迟处理规则", "support_rule", "customer_service", "现货 48 小时内出库，物流超过 120 小时无更新视为延迟。延迟补偿按天发放优惠券。"),
    "invoice_rule": ("发票开具规则", "support_rule", "customer_service", "支持电子普通发票和增值税专用发票，发票金额以订单实付金额为准，红冲重开需在 7 天内申请。"),
    "vip_service_rule": ("高价值客户服务规则", "support_rule", "ops", "近 12 个月累计消费超过 20000 元的客户进入 VIP 通道，享受专属客服和更长退货窗口。"),
    "sensitive_data_policy": ("敏感字段访问规范", "security_policy", "admin", "邮箱、手机号、精确地址和行为轨迹属于敏感数据。非 admin 角色默认只看脱敏或匿名化结果。"),
    "demo_user_scope": ("演示账号数据范围", "security_policy", "demo_user", "demo_user 只能访问 seed 生成的模拟数据，默认关闭导出、删除和外部系统集成能力。"),
    "gmv_metric_note": ("GMV 指标口径说明", "metric_definition", "ops", "GMV 统计已支付且未取消订单的 order_amount，不含运费，不扣优惠，退款不回冲 GMV。"),
    "coupon_rule": ("优惠券核销规则", "metric_definition", "ops", "优惠券分析以 order_coupons 为准。一单多券时统计订单量必须 COUNT(DISTINCT orders.id)。"),
    "behavior_funnel_rule": ("行为漏斗口径说明", "metric_definition", "ops", "加购到支付转化率以 user_behavior_log 中 payment_success / add_to_cart 计算，duration_ms 为空不影响事件数。"),
}


def _build_knowledge_docs() -> list[KnowledgeDoc]:
    """构建 10 篇知识库文档，补入优惠券和行为漏斗口径。"""

    return [
        KnowledgeDoc(
            doc_key=doc_key,
            title=title,
            doc_type=doc_type,
            audience_role=audience_role,
            status="active",
            content=content,
        )
        for doc_key, (title, doc_type, audience_role, content) in _KB_CONTENTS.items()
    ]


def _build_orders_wide(orders: list[Order]) -> list[OrderWide]:
    """把订单头常用维度冗余成宽表快照，行数与 orders 一一对应。"""

    snapshot_at = datetime(2026, 7, 1, 3, 0, 0)
    rows: list[OrderWide] = []
    for order in orders:
        # ★ 宽表保留“快照可直接聚合”的指标，但不替代明细表做强一致诊断。
        refund_count = len(order.refunds)
        total_refund = _money(sum((refund.refund_amount for refund in order.refunds), Decimal("0.00")))
        rows.append(
            OrderWide(
                order_id=order.id,
                order_no=order.order_no,
                source_order_no=order.source_order_no,
                external_order_no=order.external_order_no,
                user_id=order.user.id,
                user_name=order.user.user_name,
                user_status=order.user.status,
                user_role=order.user.role,
                product_id=order.product.id,
                sku=order.product.sku,
                product_name=order.product.product_name,
                primary_product_price=order.product.price,
                category_id=order.product.category_id,
                category=order.product.category,
                channel_id=order.channel.id,
                channel_code=order.channel.channel_code,
                channel_name=order.channel.channel_name,
                channel_type=order.channel.channel_type,
                order_status=order.order_status,
                order_amount=order.order_amount,
                shipping_amount=order.shipping_amount,
                discount_amount=order.discount_amount,
                actual_amount=order.actual_amount,
                quantity=order.quantity,
                item_count=len(order.order_items),
                refund_count=refund_count,
                total_refund=total_refund,
                has_refund=refund_count > 0,
                paid_at=order.paid_at,
                source_updated_at=order.updated_at or snapshot_at,
                snapshot_at=snapshot_at,
                batch_id="orders_wide_20260701_0300",
            )
        )
    return rows


def _count_seed_tables(session: Session) -> dict[str, int]:
    """逐表统计种子数据行数，供命令行输出和测试使用。"""

    models = {
        "users": User,
        "product_categories": ProductCategory,
        "products": Product,
        "channels": Channel,
        "orders": Order,
        "order_items": OrderItem,
        "refunds": Refund,
        "tickets": Ticket,
        "knowledge_docs": KnowledgeDoc,
        "coupons": Coupon,
        "order_coupons": OrderCoupon,
        "user_behavior_log": UserBehaviorLog,
        "product_price_history": ProductPriceHistory,
        "orders_wide": OrderWide,
    }
    return {table_name: session.execute(select(func.count(model.id))).scalar_one() for table_name, model in models.items()}


def _write_seed_summary(summary: dict[str, Any]) -> None:
    """把 seed 行数和固定事实写成 Markdown，方便人工检查和 AI_CONTEXT 引用。"""

    SEED_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 2.7 Seed Summary",
        "",
        "## Counts",
        "",
    ]
    for table_name, count in summary["counts"].items():
        lines.append(f"- {table_name}: {count}")
    lines.extend(["", "## Facts", ""])
    for fact_key, fact_value in summary["facts"].items():
        lines.append(f"- {fact_key}: {fact_value}")
    SEED_SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """命令行入口：连接数据库 → seed → 固定事实查询 → 打印摘要。"""

    parser = argparse.ArgumentParser(description="Seed DataPilot Phase 2.7 demo data.")
    parser.add_argument("--reset", action="store_true", help="Delete existing business rows before seeding.")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        summary = seed_database(session, reset_existing=args.reset)

    print("Seed completed.")
    print(summary)
    print(f"seed_summary={SEED_SUMMARY_PATH}")


if __name__ == "__main__":
    main()
