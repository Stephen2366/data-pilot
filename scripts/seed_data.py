"""种子数据脚本：向 datapilot_dev 库填充确定性的演示数据。

★ 每次重跑生成相同数据（确定性种子），供开发、测试和 demo 使用。
命令行：python -m scripts.seed_data --reset
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.models import Channel, KnowledgeDoc, Order, Product, Refund, Ticket, User

EXPECTED_SEED_COUNTS = {
    "users": 50,
    "products": 30,
    "channels": 6,
    "orders": 500,
    "refunds": 80,
    "tickets": 120,
    "knowledge_docs": 8,
}
# ★ 这 4 个角色来自 Phase 2 的 RBAC 设计，M4 会继续用它们做权限矩阵。
REQUIRED_ROLES = {"admin", "ops", "customer_service", "demo_user"}


# 固定事实说明 ================================================================
# ★ 这些事实是后续 SQL 评测的“标准答案锚点”，seed 每次重跑都保持稳定：
# 1. 2026-06 退款率最高商品：Aurora Noise Cancelling Headphones。
# 2. 2026-06 GMV 最高渠道：Mobile App。
# 3. 全量退款 Top 原因：quality_issue。
# 4. 待处理高优先级工单数量：12。


def seed_database(session: Session, reset_existing: bool = False) -> dict[str, Any]:
    """向已迁移完成的数据库中填充确定性的演示数据。

    参数说明：
    - session：外部传入事务会话，方便 API、测试和命令行复用同一套逻辑。
    - reset_existing：为 True 时先清空 7 张业务表；生产环境不要对真实库使用。
    """

    # 步骤 1：按需清空旧数据 =================================================
    # reset 模式用于本地反复验收。真实生产库不应直接清空业务表。
    if reset_existing:
        _delete_existing_rows(session)

    # 步骤 2：先创建“父表 / 维表” ============================================
    # 订单、退款、工单都有外键，必须先让用户、商品、渠道、文档拥有主键 id。
    users = _build_users()
    products = _build_products()
    channels = _build_channels()
    docs = _build_knowledge_docs()

    session.add_all([*users, *products, *channels, *docs])
    # flush 会把对象写入数据库事务并拿到自增 id，但暂时不 commit。
    # 这样后续 orders 可以直接通过 user/product/channel 关系建立外键。
    session.flush()

    # 步骤 3：再创建“子表 / 事实表” ==========================================
    # orders 依赖用户、商品、渠道；refunds 和 tickets 又依赖 orders。
    orders = _build_orders(users=users, products=products, channels=channels)
    session.add_all(orders)
    session.flush()

    refunds = _build_refunds(orders)
    tickets = _build_tickets(users=users, orders=orders)
    session.add_all([*refunds, *tickets])
    # 所有表一起提交，保证 seed 要么完整成功，要么完整回滚。
    session.commit()

    # 步骤 4：返回摘要，给命令行输出、测试断言和后续排查使用。====================
    counts = _count_seed_tables(session)
    return {
        "counts": counts,
        "roles": sorted({user.role for user in users}),
        "facts": verify_business_facts(session),
    }


def verify_business_facts(session: Session) -> dict[str, Any]:
    """对种子数据中内嵌的业务事实执行稳定的 SQL 校验。

    ★ 这里不是为了业务功能服务，而是为了”验收可复现”。后续 Agent 生成 SQL 后，
    可以拿这些事实当标准答案，判断它查出来的关键结果是否正确。
    """

    # 统一定义 2026-06 的左闭右开时间窗口：[2026-06-01, 2026-07-01)。
    # 这样不需要处理“6 月最后一秒”的边界问题。
    june_start = datetime(2026, 6, 1)
    july_start = datetime(2026, 7, 1)

    # 事实 1：按商品统计 2026-06 退款率，退款率 = 退款订单数 / 订单数。
    refund_rate_stmt = (
        select(
            Product.product_name,
            (func.count(func.distinct(Refund.id)) * 1.0 / func.count(func.distinct(Order.id))).label("refund_rate"),
        )
        .join(Order, Order.product_id == Product.id)
        .outerjoin(Refund, Refund.order_id == Order.id)
        .where(Order.paid_at >= june_start, Order.paid_at < july_start)
        .group_by(Product.id, Product.product_name)
        .order_by(
            (func.count(func.distinct(Refund.id)) * 1.0 / func.count(func.distinct(Order.id))).desc(),
            Product.product_name.asc(),
        )
        .limit(1)
    )
    highest_refund_rate_product = session.execute(refund_rate_stmt).scalar_one()

    # 事实 2：按渠道统计 2026-06 GMV，排除已取消订单。
    gmv_stmt = (
        select(Channel.channel_name, func.sum(Order.order_amount).label("gmv"))
        .join(Order, Order.channel_id == Channel.id)
        .where(
            Order.paid_at >= june_start,
            Order.paid_at < july_start,
            Order.order_status != "cancelled",
        )
        .group_by(Channel.id, Channel.channel_name)
        .order_by(func.sum(Order.order_amount).desc(), Channel.channel_name.asc())
        .limit(1)
    )
    top_gmv_channel = session.execute(gmv_stmt).scalar_one()

    # 事实 3：全量退款原因 Top 1。
    reason_stmt = (
        select(Refund.refund_reason, func.count(Refund.id).label("refund_count"))
        .group_by(Refund.refund_reason)
        .order_by(func.count(Refund.id).desc(), Refund.refund_reason.asc())
        .limit(1)
    )
    top_refund_reason = session.execute(reason_stmt).scalar_one()

    # 事实 4：待处理高优先级工单数量。
    pending_ticket_stmt = select(func.count(Ticket.id)).where(Ticket.status == "pending", Ticket.priority == "high")
    pending_high_priority_tickets = session.execute(pending_ticket_stmt).scalar_one()

    return {
        "highest_refund_rate_product_june_2026": highest_refund_rate_product,
        "top_gmv_channel_june_2026": top_gmv_channel,
        "top_refund_reason": top_refund_reason,
        "pending_high_priority_tickets": pending_high_priority_tickets,
    }


def _delete_existing_rows(session: Session) -> None:
    """按外键依赖顺序清空 7 张业务表，避免 MySQL 外键约束阻止删除。"""
    # 按外键依赖从子表到父表删除，避免 MySQL 外键约束阻止清空。
    for model in (Ticket, Refund, Order, KnowledgeDoc, Product, Channel, User):
        session.execute(delete(model))
    session.flush()


# 50 个真实感中文姓名，适合演示和面试截图。
_REALISTIC_NAMES: list[str] = [
    "陈米娅", "王逸凡", "张雨薇", "李思源", "刘若晴",
    "黄子轩", "赵晓萌", "吴俊杰", "杨雨桐", "周明哲",
    "徐悦然", "孙博文", "马晓琳", "郭浩然", "林芷若",
    "何志远", "高语嫣", "唐瑞霖", "程一诺", "罗嘉懿",
    "彭婉清", "潘奕辰", "邓梓涵", "肖景行", "冯书瑶",
    "石承宇", "任雅静", "万子骞", "杜若溪", "傅正阳",
    "谢安然", "段思齐", "姜语桐", "韩铭远", "秦乐瑶",
    "廖凯文", "熊芷萱", "崔敬轩", "毕雨晴", "瞿天佑",
    "孔令仪", "阮启航", "侯静怡", "左逸凡", "童雅琪",
    "顾砚书", "邵灵犀", "裴宇轩", "连以安", "聂朗清",
]

# 姓名的拼音映射，用于生成邮箱地址（first.last@datapilot.example）。
_REALISTIC_NAME_PINYIN: list[str] = [
    "miya.chen", "yifan.wang", "yuwei.zhang", "siyuan.li", "ruoqing.liu",
    "zixuan.huang", "xiaomeng.zhao", "junjie.wu", "yutong.yang", "mingzhe.zhou",
    "yueran.xu", "bowen.sun", "xiaolin.ma", "haoran.guo", "zhiruo.lin",
    "zhiyuan.he", "yuyan.gao", "ruilin.tang", "yinuo.cheng", "jiayi.luo",
    "wanqing.peng", "yichen.pan", "zihan.deng", "jingxing.xiao", "shuyao.feng",
    "chengyu.shi", "yajing.ren", "ziqian.wan", "ruoxi.du", "zhengyang.fu",
    "anran.xie", "siqi.duan", "yutong.jiang", "mingyuan.han", "leyao.qin",
    "kaiwen.liao", "zhixuan.xiong", "jingxuan.cui", "yuqing.bi", "tianyou.qu",
    "lingyi.kong", "qihang.ruan", "jingyi.hou", "yifan.zuo", "yaqi.tong",
    "yanshu.gu", "lingxi.shao", "yuxuan.peui", "yian.lian", "langqing.nie",
]


def _build_users() -> list[User]:
    """构建 50 个用户，覆盖所有 RBAC 角色。"""

    users: list[User] = []
    roles = ["admin", "ops", "customer_service", "demo_user"]

    for index in range(EXPECTED_SEED_COUNTS["users"]):
        # 用取模轮转角色，保证 4 类角色都出现，并且数量大致均匀。
        role = roles[index % len(roles)]
        users.append(
            User(
                user_name=_REALISTIC_NAMES[index],
                role=role,
                email=f"{_REALISTIC_NAME_PINYIN[index]}@datapilot.example",
                phone=f"1380000{index + 1:04d}",
                status="active" if index < 46 else "disabled",
            )
        )

    return users


# 29 个真实感商品/SaaS 套餐名（中文），按类目分组，适合演示和面试截图。
# 索引 0 为锚点商品 Aurora Noise Cancelling Headphones 预留。
_REALISTIC_PRODUCTS: list[dict[str, Any]] = [
    {"sku": "SKU-WL-EB-002", "name": "真无线降噪耳机 Pro",         "category": "数码电子", "price": Decimal("399.00")},
    {"sku": "SKU-SD-LP-003", "name": "智能护眼台灯",               "category": "家居生活",        "price": Decimal("249.00")},
    {"sku": "SKU-MK-K2-004", "name": "机械键盘 K2 红轴",           "category": "数码电子", "price": Decimal("549.00")},
    {"sku": "SKU-MS-PL-005", "name": "记忆棉护颈枕",               "category": "家居生活",        "price": Decimal("179.00")},
    {"sku": "SKU-VC-SR-006", "name": "VC 焕白精华液 30ml",         "category": "个护美妆",      "price": Decimal("128.00")},
    {"sku": "SKU-CRM-ST-007","name": "CRM 入门版（月付）",          "category": "SaaS 软件",        "price": Decimal("299.00")},
    {"sku": "SKU-HB-45-008", "name": "户外登山包 45L",              "category": "户外运动",     "price": Decimal("459.00")},
    {"sku": "SKU-4K-WC-009", "name": "4K 高清摄像头",               "category": "数码电子", "price": Decimal("679.00")},
    {"sku": "SKU-BM-SH-010", "name": "楠竹置物架三层",             "category": "家居生活",        "price": Decimal("189.00")},
    {"sku": "SKU-HA-TN-011", "name": "玻尿酸保湿爽肤水",           "category": "个护美妆",      "price": Decimal("98.00")},
    {"sku": "SKU-AN-PR-012", "name": "Analytics Pro（月付）",      "category": "SaaS 软件",        "price": Decimal("599.00")},
    {"sku": "SKU-CT-2P-013", "name": "双人露营帐篷 防暴雨",        "category": "户外运动",     "price": Decimal("899.00")},
    {"sku": "SKU-UG-CG-014", "name": "氮化镓快充头 65W",           "category": "数码电子", "price": Decimal("149.00")},
    {"sku": "SKU-AR-DR-015", "name": "超声波香薰机 Mini",          "category": "家居生活",        "price": Decimal("139.00")},
    {"sku": "SKU-SP-FD-016", "name": "清爽防晒日霜 SPF50",         "category": "个护美妆",      "price": Decimal("158.00")},
    {"sku": "SKU-MK-ST-017", "name": "全渠道营销套件入门版",       "category": "SaaS 软件",        "price": Decimal("899.00")},
    {"sku": "SKU-UL-TT-018", "name": "超轻徒步帐篷 单人",          "category": "户外运动",     "price": Decimal("1299.00")},
    {"sku": "SKU-BT-SK-019", "name": "便携蓝牙音箱 Mini",          "category": "数码电子", "price": Decimal("219.00")},
    {"sku": "SKU-SL-PL-020", "name": "真丝枕套套装 一对装",        "category": "家居生活",        "price": Decimal("99.00")},
    {"sku": "SKU-RT-MK-021", "name": "视黄醇抗皱面霜",             "category": "个护美妆",      "price": Decimal("189.00")},
    {"sku": "SKU-CS-PT-022", "name": "智能客服 Pro（月付）",       "category": "SaaS 软件",        "price": Decimal("399.00")},
    {"sku": "SKU-PC-JK-023", "name": "便携轻薄羽绒服",             "category": "户外运动",     "price": Decimal("549.00")},
    {"sku": "SKU-TB-PS-024", "name": "铝合金平板支架",             "category": "数码电子", "price": Decimal("79.00")},
    {"sku": "SKU-CX-FM-025", "name": "纯棉针织盖毯",               "category": "家居生活",        "price": Decimal("159.00")},
    {"sku": "SKU-CC-CM-026", "name": "校色遮瑕膏 三色盘",          "category": "个护美妆",      "price": Decimal("109.00")},
    {"sku": "SKU-WH-PL-027", "name": "仓储管理 Pro（月付）",       "category": "SaaS 软件",        "price": Decimal("699.00")},
    {"sku": "SKU-FS-RD-028", "name": "碳素台钓竿 2.4m",            "category": "户外运动",     "price": Decimal("329.00")},
    {"sku": "SKU-KS-SC-029", "name": "儿童智能手表",               "category": "数码电子", "price": Decimal("259.00")},
    {"sku": "SKU-RC-CK-030", "name": "迷你电饭煲 3 杯量",          "category": "家居生活",        "price": Decimal("119.00")},
]


def _build_products() -> list[Product]:
    """构建商品数据，包含一个用于退款率评测的锚点商品。"""

    # 第 1 个商品是固定事实锚点：后续 refunds 会集中指向它，
    # 确保它成为 2026-06 退款率最高商品。
    products = [
        Product(
            sku="SKU-HIGH-REFUND-01",
            product_name="Aurora Noise Cancelling Headphones",
            category="数码电子",
            status="active",
            price=Decimal("899.00"),
            launched_at=datetime(2026, 1, 10),
        )
    ]

    for index, prod in enumerate(_REALISTIC_PRODUCTS):
        products.append(
            Product(
                sku=prod["sku"],
                product_name=prod["name"],
                category=prod["category"],
                status="active" if (index + 1) % 11 else "paused",
                price=prod["price"],
                launched_at=datetime(2026, 1, 1) + timedelta(days=(index + 1) * 3),
            )
        )

    return products


def _build_channels() -> list[Channel]:
    """构建 6 个渠道，覆盖自有、平台、付费和合作伙伴流量来源。"""

    return [
        Channel(channel_code="mobile_app", channel_name="Mobile App", channel_type="owned"),
        Channel(channel_code="web_store", channel_name="Web Store", channel_type="owned"),
        Channel(channel_code="tmall", channel_name="Tmall", channel_type="marketplace"),
        Channel(channel_code="jd", channel_name="JD", channel_type="marketplace"),
        Channel(channel_code="douyin", channel_name="Douyin", channel_type="paid"),
        Channel(channel_code="partner", channel_name="Partner", channel_type="partner"),
    ]


def _build_orders(users: list[User], products: list[Product], channels: list[Channel]) -> list[Order]:
    """构建确定性订单数据，模拟 6 月/5 月的时间分布和渠道锚点。"""

    orders: list[Order] = []
    june_start = datetime(2026, 6, 1, 9, 0, 0)
    may_start = datetime(2026, 5, 1, 9, 0, 0)
    # 加权分布模拟真实电商：大部分已送达，少量取消。delivered 200 + shipped 150 + paid 100 + cancelled 50 = 500。
    statuses = ["delivered"] * 200 + ["shipped"] * 150 + ["paid"] * 100 + ["cancelled"] * 50

    for index in range(EXPECTED_SEED_COUNTS["orders"]):
        # 前 40 单集中给锚点商品，配合退款数据制造“退款率最高商品”。
        if index < 40:
            product = products[0]
        else:
            product = products[(index % (len(products) - 1)) + 1]

        # 前 170 单集中给 Mobile App 且金额较高，制造“6 月 GMV 最高渠道”。
        if index < 170:
            channel = channels[0]
            amount = Decimal("899.00") + Decimal(index % 5) * Decimal("50.00")
        else:
            channel = channels[(index % (len(channels) - 1)) + 1]
            amount = Decimal("109.00") + Decimal(index % 17) * Decimal("23.00")

        # 前 320 单落在 6 月，剩余订单落在 5 月，方便后续测试时间筛选。
        paid_at = (june_start if index < 320 else may_start) + timedelta(days=index % 28, hours=index % 7)
        status = statuses[index]

        orders.append(
            Order(
                order_no=f"ORD-2026-{index + 1:05d}",
                user=users[index % len(users)],
                product=product,
                channel=channel,
                order_status=status,
                order_amount=amount,
                quantity=1 + (index % 3),
                paid_at=paid_at,
            )
        )

    return orders


def _build_refunds(orders: list[Order]) -> list[Refund]:
    """构建退款数据，包含稳定的原因分布和商品退款率锚点。"""

    refunds: list[Refund] = []
    # quality_issue 出现 42 次，确保它稳定成为 Top 退款原因。
    reasons = ["quality_issue"] * 42 + ["late_delivery"] * 15 + ["wrong_item"] * 12 + ["changed_mind"] * 11
    statuses = ["approved", "completed", "requested", "rejected"]

    # 先集中给锚点商品生成 18 条退款，确保它在 2026-06 的退款率最高。
    refund_order_indexes = list(range(18))
    refund_order_indexes.extend(range(60, 60 + EXPECTED_SEED_COUNTS["refunds"] - 18))

    for index, order_index in enumerate(refund_order_indexes):
        order = orders[order_index]
        requested_at = order.paid_at + timedelta(days=2 + index % 5)
        processed_at = requested_at + timedelta(days=1) if index % 4 != 2 else None
        refunds.append(
            Refund(
                refund_no=f"REF-2026-{index + 1:05d}",
                order=order,
                user=order.user,
                product=order.product,
                refund_status=statuses[index % len(statuses)],
                refund_reason=reasons[index],
                refund_amount=(order.order_amount * Decimal("0.90")).quantize(Decimal("0.01")),
                requested_at=requested_at,
                processed_at=processed_at,
            )
        )

    return refunds


# 工单标题词库：按 ticket_type 分组，生成真实客服场景的 subject。
_TICKET_SUBJECTS: dict[str, list[str]] = {
    "refund": [
        "申请 Aurora 耳机质量问题退款",
        "收到的商品外包装破损，要求退货",
        "护肤品过敏反应，申请退款退货",
        "订单重复扣款，申请退回多付金额",
        "商品与页面描述不符，要求退款",
        "7 天无理由退货申请",
        "赠品缺失，申请部分退款",
        "活动期间买贵了，申请退差价",
        "退货后物流显示签收但未退款",
    ],
    "shipping": [
        "物流信息 72 小时未更新，查询包裹状态",
        "发货地址填写错误，请求修改",
        "物流延迟超过预计到货时间 5 天",
        "包裹显示已签收但本人未收到",
        "跨境物流清关中，咨询预计放行时间",
        "加急订单未按承诺时效发货",
        "收货地址变更，请转寄到新地址",
        "部分商品漏发，请求补发",
    ],
    "invoice": [
        "电子发票抬头修改为公司名称",
        "发票金额与实付金额不符",
        "需要补开增值税专用发票",
        "发票税号填写错误，申请重开",
        "订单完成后发票未自动推送",
        "批量采购需要合并开票",
    ],
    "account": [
        "账号绑定手机号已停用，申请换绑",
        "多次登录失败，账号疑似被锁定",
        "会员等级未正确升级，积分异常",
        "无法修改默认收货地址",
        "账号注销申请被驳回，查询原因",
        "实名认证审核超过 3 个工作日",
    ],
    "product_quality": [
        "耳机降噪功能与宣传效果差距大",
        "商品缺少中文使用说明书",
        "SaaS 套餐功能权限与购买页面不一致",
        "查询商品是否支持固件升级",
        "电饭煲内胆涂层出现脱落",
        "商品保质期剩余不足 3 个月",
    ],
}


def _build_tickets(users: list[User], orders: list[Order]) -> list[Ticket]:
    """构建客服工单，固定包含 12 个待处理高优先级工单。"""

    tickets: list[Ticket] = []
    # 加权分布让工单类型不那么均匀，退款和物流比发票和账号更常见。
    ticket_types = ["refund"] * 30 + ["shipping"] * 28 + ["invoice"] * 22 + ["account"] * 20 + ["product_quality"] * 20
    service_users = [user for user in users if user.role == "customer_service"]

    for index in range(EXPECTED_SEED_COUNTS["tickets"]):
        ttype = ticket_types[index]
        # 前 12 条固定为 pending + high，作为后续客服工单评测锚点。
        is_anchor_ticket = index < 12
        priority = "high" if is_anchor_ticket else ["low", "medium", "urgent"][index % 3]
        status = "pending" if is_anchor_ticket else ["processing", "resolved", "closed"][index % 3]
        created_at = datetime(2026, 6, 1, 10, 0, 0) + timedelta(hours=index * 3)
        resolved_at = None if status in {"pending", "processing"} else created_at + timedelta(days=2)

        # 从对应类型的词库中轮转选取标题，保证每次 seed 结果确定。
        subjects_pool = _TICKET_SUBJECTS[ttype]
        subject = subjects_pool[index % len(subjects_pool)]

        tickets.append(
            Ticket(
                ticket_no=f"TCK-2026-{index + 1:05d}",
                user=users[index % len(users)],
                order=orders[index % len(orders)] if index % 5 != 0 else None,
                assigned_user=service_users[index % len(service_users)],
                ticket_type=ttype,
                priority=priority,
                status=status,
                subject=subject,
                description=f"用户 {users[index % len(users)].user_name} 提交工单：{subject}。请客服团队尽快处理。",
                resolved_at=resolved_at,
                created_at=created_at,
            )
        )

    return tickets


# 知识库文档正文库：每个 doc_key 对应一份真实感政策文档（2-5 段），供 RAG 检索使用。
_KB_CONTENTS: dict[str, str] = {
    "refund_policy_basic": (
        "本平台支持以下退款类型：7 天无理由退货、质量问题退款、物流损坏退款以及价保补差。"
        "7 天无理由退货需确保商品完好、配件齐全且不影响二次销售；用户需在签收后 168 小时内提交申请，"
        "审核通过后 3 个工作日内原路退款。"
        "质量问题退款不受 7 天限制，用户在质保期内凭有效凭证（订单号 + 商品照片）发起申请，"
        "客服将在 24 小时内响应并安排上门取件，退货运费由平台承担。"
        "物流损坏退款需用户在签收时当面验货并拍照留存；若快递员已离开，需在签收后 4 小时内提交"
        "损坏照片和开箱视频，超时将按普通质量问题流程处理。"
        "价保补差适用于标有「价保」标签的商品，用户在购买后 15 天内发现同 SKU 降价，可申请退还差价，"
        "每单限申请一次。"
    ),
    "refund_policy_quality": (
        "质量问题指商品存在影响正常使用的缺陷，包括但不限于：功能故障（如电子产品无法开机）、"
        "外观严重瑕疵（如服装大面积染色、鞋类开胶）、保质期内变质（如护肤品油水分离、食品发霉）"
        "以及配件缺失导致无法使用。"
        "用户提交质量问题退款时需提供以下材料：① 清晰展示缺陷部位的照片至少 3 张；"
        "② 开箱视频（如为签收时即发现）；③ 商品外包装的快递单号照片。材料不全将退回补充，"
        "累计退回 2 次仍未补全的将自动转为线下人工审核。"
        "平台在收到退货商品后 48 小时内完成质检。确认为质量问题的，全额退款并补偿 50 元优惠券；"
        "确认为用户使用不当的，将原路寄回并由用户承担来回运费。"
    ),
    "shipping_delay_rule": (
        "订单发货时效以商品详情页标注的「预计发货时间」为准：现货商品支付后 48 小时内出库，"
        "预售商品以页面标注的「最晚发货日」为承诺截止时间。"
        "物流延迟定义为「超过承诺发货时间 72 小时仍未出库」或「出库后物流信息超过 120 小时无更新」。"
        "发生延迟时，用户可申请延迟补偿：每延迟 1 天补偿 10 元无门槛优惠券，单笔订单补偿上限 100 元。"
        "因不可抗力（自然灾害、疫情封控、海关抽检等）导致的延迟不适用补偿规则，但平台将主动推送"
        "延迟通知并在物流恢复正常后优先发货。"
        "加急订单（标记为「加急配送」）未在承诺时效内送达的，除延迟补偿外额外退还加急费用的 50%。"
    ),
    "invoice_rule": (
        "平台支持开具电子普通发票和增值税专用发票。电子普通发票在订单完成后自动推送至用户邮箱，"
        "也可在「我的订单 → 申请发票」中手动触发；增值税专用发票需先完成企业认证并填写完整的"
        "开票信息（公司名称、税号、地址、电话、开户行及账号）。"
        "发票抬头默认为收货人姓名，用户可在下单时修改为个人或企业名称。订单支付后 30 天内可修改"
        "抬头，超过 30 天需联系客服人工处理。已开具的发票若信息有误，可在开票后 7 天内申请红冲重开。"
        "发票金额以订单实付金额为准（已扣除优惠券、积分抵扣等），不含运费和保险费。合并开票需在"
        "所有关联订单均完成后的 15 天内提交申请，跨月订单不支持合并开票。"
    ),
    "vip_service_rule": (
        "高价值客户（定义：近 12 个月累计消费金额 ≥ 20,000 元或月均消费 ≥ 2,000 元）自动进入"
        "VIP 服务通道，享受专属客服、优先处理和柔性退款政策。"
        "VIP 客户提交工单后，系统自动分配高级客服（Level 3 及以上），首次响应时间承诺 ≤ 2 小时。"
        "退款方面，VIP 客户享受扩大的无理由退货窗口（15 天而非标准 7 天），且年度内 3 次以内"
        "无理由退货免收退回运费。"
        "每季度平台会重新评估 VIP 资格，降级客户将收到通知并保留 30 天缓冲期，缓冲期内仍享受"
        "VIP 权益。"
    ),
    "sensitive_data_policy": (
        "敏感字段包括但不限于：用户真实姓名、手机号、邮箱、身份证号、银行卡号、收货地址的精确门牌号、"
        "IP 地址以及用户行为轨迹数据。以上字段在数据库中以加密存储（AES-256-GCM），应用层按角色"
        "脱敏展示。"
        "各角色访问权限如下：admin 可查看所有字段明文，但每次访问均记录审计日志；ops 可查看脱敏后"
        "的手机号（138****0001）和邮箱前缀（miy***）；customer_service 仅可在处理工单时临时查看"
        "关联用户的手机号和地址，工单关闭后 24 小时权限自动回收；demo_user 角色仅能访问匿名化的"
        "演示数据，严禁接触任何真实 PII。"
        "数据导出操作需双人审批：申请人提交导出原因和范围，由 admin 角色两人依次审批后方可执行，"
        "导出文件自动加水印并设置 72 小时后失效。所有敏感数据访问日志保留不少于 180 天。"
    ),
    "demo_user_scope": (
        "演示账号（demo_user 角色）用于产品演示和新员工培训，所有可访问数据均为系统生成的模拟数据，"
        "不包含任何真实用户个人信息或业务记录。演示账号的数据范围限定在：seed 脚本生成的订单、退款、"
        "工单和知识库文档，且所有金额、姓名、地址均为虚构。"
        "演示账号默认关闭以下能力：数据导出、批量删除、API Key 创建以及外部系统集成。若培训需要"
        "开放部分能力，需由 admin 在演示沙箱环境中单独配置，培训结束后立即回收。"
        "每个演示账号的有效期为创建后 90 天，到期自动禁用。需继续使用的，由 admin 手动续期，"
        "每次续期最长 90 天。"
    ),
    "gmv_metric_note": (
        "GMV（Gross Merchandise Volume，成交总额）是平台核心业务指标之一，统计口径需在跨部门"
        "协作中保持一致以避免数据分歧。"
        "本平台 GMV 口径定义为：在统计周期内，已支付且未被取消的订单金额总和。具体规则如下："
        "① 仅统计 order_status 为 'paid'、'shipped' 或 'delivered' 的订单，排除 'cancelled'；"
        "② 金额取 order_amount 字段，单位为人民币元；③ 统计时间以 paid_at（支付时间）为基准，"
        "而非下单时间或发货时间。"
        "退款订单不影响 GMV 计算——即使订单后续发生了退款，只要未取消，其金额仍计入 GMV。"
        "如需分析「实收口径」的收入，应使用 NAR（Net Revenue After Refund）= 支付金额 − 实际退款金额。"
        "月度 GMV 报表在次月第 3 个工作日前由系统自动生成，如遇节假日顺延。"
    ),
}


def _build_knowledge_docs() -> list[KnowledgeDoc]:
    """构建政策与指标文档，供后续 RAG 模块使用。"""

    docs = [
        ("refund_policy_basic", "基础退款政策", "refund_policy", "customer_service"),
        ("refund_policy_quality", "质量问题退款规则", "refund_policy", "customer_service"),
        ("shipping_delay_rule", "物流延迟处理规则", "support_rule", "customer_service"),
        ("invoice_rule", "发票开具规则", "support_rule", "customer_service"),
        ("vip_service_rule", "高价值客户服务规则", "support_rule", "ops"),
        ("sensitive_data_policy", "敏感字段访问规范", "security_policy", "admin"),
        ("demo_user_scope", "演示账号数据范围", "security_policy", "demo_user"),
        ("gmv_metric_note", "GMV 指标口径说明", "metric_definition", "ops"),
    ]
    return [
        KnowledgeDoc(
            doc_key=doc_key,
            title=title,
            doc_type=doc_type,
            audience_role=audience_role,
            status="active",
            content=_KB_CONTENTS[doc_key],
        )
        for doc_key, title, doc_type, audience_role in docs
    ]


def _count_seed_tables(session: Session) -> dict[str, int]:
    """逐表统计种子数据行数，供命令行输出和测试使用。"""

    models = {
        "users": User,
        "products": Product,
        "channels": Channel,
        "orders": Order,
        "refunds": Refund,
        "tickets": Ticket,
        "knowledge_docs": KnowledgeDoc,
    }
    return {table_name: session.execute(select(func.count(model.id))).scalar_one() for table_name, model in models.items()}


def main() -> None:
    """命令行入口：连接数据库 → 填充种子数据 → 校验业务事实 → 打印统计。"""
    # 命令行入口 ==============================================================
    # 设计成 python -m scripts.seed_data --reset，方便 README 和 dev-log 复用。
    parser = argparse.ArgumentParser(description="Seed DataPilot M1 demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing M1 business rows before seeding.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)

    # 命令行脚本只负责写数据，不调用 create_all；建表主路径必须走 Alembic。
    with SessionLocal() as session:
        summary = seed_database(session, reset_existing=args.reset)

    print("Seed completed.")
    print(summary)


if __name__ == "__main__":
    main()
