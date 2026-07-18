from datetime import datetime
from typing import TypeVar

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.base import Order, Product, Refund, Ticket
from app.db.session import get_db
from app.schemas.common import PageResponse
from app.schemas.resources import OrderRead, ProductRead, RefundRead, TicketRead


router = APIRouter(prefix="/api", tags=["resources"])
ModelT = TypeVar("ModelT")


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "unknown")


def _paginate(
    *,
    db: Session,
    stmt: Select[tuple[ModelT]],
    page: int,
    page_size: int,
    request: Request,
) -> PageResponse[ModelT]:
    """Execute a filtered SELECT and wrap it in the shared page response."""

    # 步骤 1：先统计过滤后的总数，前端需要它计算总页数。
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    # 步骤 2：再取当前页。offset = (页码 - 1) * 每页条数，是最常见分页公式。
    items = (
        db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
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
    stmt = select(Product).order_by(Product.id.asc())
    if category:
        stmt = stmt.where(Product.category == category)
    if status:
        stmt = stmt.where(Product.status == status)

    return _paginate(
        db=db, stmt=stmt, page=page, page_size=page_size, request=request
    )


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
    stmt = select(Order).order_by(Order.id.asc())
    if paid_from:
        stmt = stmt.where(Order.paid_at >= paid_from)
    if paid_to:
        stmt = stmt.where(Order.paid_at < paid_to)
    if channel_id:
        stmt = stmt.where(Order.channel_id == channel_id)
    if order_status:
        stmt = stmt.where(Order.order_status == order_status)

    return _paginate(
        db=db, stmt=stmt, page=page, page_size=page_size, request=request
    )


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
    stmt = select(Refund).order_by(Refund.id.asc())
    if requested_from:
        stmt = stmt.where(Refund.requested_at >= requested_from)
    if requested_to:
        stmt = stmt.where(Refund.requested_at < requested_to)
    if refund_status:
        stmt = stmt.where(Refund.refund_status == refund_status)
    if refund_reason:
        stmt = stmt.where(Refund.refund_reason == refund_reason)

    return _paginate(
        db=db, stmt=stmt, page=page, page_size=page_size, request=request
    )


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
    stmt = select(Ticket).order_by(Ticket.id.asc())
    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if ticket_type:
        stmt = stmt.where(Ticket.ticket_type == ticket_type)

    return _paginate(
        db=db, stmt=stmt, page=page, page_size=page_size, request=request
    )
