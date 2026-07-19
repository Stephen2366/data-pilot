from datetime import datetime
from typing import TypeVar

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.base import Order, Product, Refund, Ticket
from app.db.session import get_db
from app.schemas.common import PageResponse
from app.schemas.resources import OrderRead, ProductRead, RefundRead, TicketRead

"""资源列表 API：商品/订单/退款/工单 4 个列表接口 + 通用分页执行器。

★ 4 个接口共用同一个 _paginate 执行器，各自只负责拼筛选条件；
分页、计数、响应组装全部收口在一处，避免重复代码。
"""

# 4 个资源列表接口共用一个 router，统一挂 /api 前缀（类比 SpringBoot 的类级 @RequestMapping）。
router = APIRouter(prefix="/api", tags=["resources"])
# ModelT 是泛型占位符：让 _paginate 对 4 种 ORM 模型复用同一套分页逻辑。
ModelT = TypeVar("ModelT")


def _trace_id(request: Request) -> str:
    """从请求上下文读取 trace_id，塞进分页响应，方便把某次响应和服务端日志对上。"""
    return getattr(request.state, "trace_id", "unknown")


def _paginate(
    *,
    db: Session,
    stmt: Select[tuple[ModelT]],
    page: int,
    page_size: int,
    request: Request,
) -> PageResponse[ModelT]:
    """通用分页执行器：执行过滤后的 SELECT，并包装成统一的 PageResponse。

    ★ 4 个列表接口只负责拼各自的筛选条件；计数、取页、响应组装全部收口在这里，
    避免同一套分页逻辑复制 4 份。
    """

    # 步骤 1：先统计过滤后的总数，前端需要它计算总页数。
    # order_by(None) 去掉计数子查询里的排序：算总数不需要排序，留着只会浪费性能。
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()

    # 步骤 2：再取当前页。offset = (页码 - 1) * 每页条数，是最常见分页公式。
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return PageResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        trace_id=_trace_id(request),
    )


@router.get("/products", response_model=PageResponse[ProductRead])
def list_products(
    request: Request,
    category: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PageResponse[ProductRead]:
    """商品列表：支持类目 / 状态筛选 + 分页。

    ★ page / page_size 的合法范围由 Query(ge=1, le=100) 声明式校验，非法值由 FastAPI
    直接拒绝，并经全局异常处理器统一包装成 422 ErrorResponse，路由里不用手写 if 判断。
    """

    # 分页必须配稳定排序（按 id 升序），否则数据库不保证两页之间的数据不重不漏。
    stmt = select(Product).order_by(Product.id.asc())
    if category:
        stmt = stmt.where(Product.category == category)
    if status:
        stmt = stmt.where(Product.status == status)

    return _paginate(db=db, stmt=stmt, page=page, page_size=page_size, request=request)


@router.get("/orders", response_model=PageResponse[OrderRead])
def list_orders(
    request: Request,
    paid_from: datetime | None = None,
    paid_to: datetime | None = None,
    channel_id: int | None = None,
    order_status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PageResponse[OrderRead]:
    """订单列表：支持支付时间范围 / 渠道 / 订单状态筛选 + 分页。

    ★ 时间筛选使用左闭右开区间 [paid_from, paid_to)，避免月度统计时边界数据重复计算。
    渠道和订单状态是 GMV 分析最常用的两个维度，所以单独暴露为可选筛选参数。
    """

    stmt = select(Order).order_by(Order.id.asc())
    if paid_from:
        stmt = stmt.where(Order.paid_at >= paid_from)
    if paid_to:
        # 时间范围用“>= from、< to”的左闭右开写法，月度统计等场景不会把边界时刻算两次。
        stmt = stmt.where(Order.paid_at < paid_to)
    if channel_id:
        stmt = stmt.where(Order.channel_id == channel_id)
    if order_status:
        stmt = stmt.where(Order.order_status == order_status)

    return _paginate(db=db, stmt=stmt, page=page, page_size=page_size, request=request)


@router.get("/refunds", response_model=PageResponse[RefundRead])
def list_refunds(
    request: Request,
    requested_from: datetime | None = None,
    requested_to: datetime | None = None,
    refund_status: str | None = None,
    refund_reason: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PageResponse[RefundRead]:
    """退款列表：支持申请时间范围 / 退款状态 / 退款原因筛选 + 分页。

    ★ 退款状态和退款原因是售后分析的两个核心维度；退款原因（quality_issue 等）
    后续会用于退款率归因分析。
    """

    stmt = select(Refund).order_by(Refund.id.asc())
    if requested_from:
        stmt = stmt.where(Refund.requested_at >= requested_from)
    if requested_to:
        stmt = stmt.where(Refund.requested_at < requested_to)
    if refund_status:
        stmt = stmt.where(Refund.refund_status == refund_status)
    if refund_reason:
        stmt = stmt.where(Refund.refund_reason == refund_reason)

    return _paginate(db=db, stmt=stmt, page=page, page_size=page_size, request=request)


@router.get("/tickets", response_model=PageResponse[TicketRead])
def list_tickets(
    request: Request,
    status: str | None = None,
    priority: str | None = None,
    ticket_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PageResponse[TicketRead]:
    """工单列表：支持状态 / 优先级 / 工单类型筛选 + 分页。

    ★ 客服运营最常见的筛选场景是"待处理 + 高优先级"，所以 status 和 priority
    都建了索引；工单类型用于区分咨询、投诉、技术支持等不同处理流程。
    """

    stmt = select(Ticket).order_by(Ticket.id.asc())
    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if ticket_type:
        stmt = stmt.where(Ticket.ticket_type == ticket_type)

    return _paginate(db=db, stmt=stmt, page=page, page_size=page_size, request=request)
