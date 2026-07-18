from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    product_name: str
    category: str
    status: str
    price: Decimal
    launched_at: datetime | None


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    user_id: int
    product_id: int
    channel_id: int
    order_status: str
    order_amount: Decimal
    quantity: int
    paid_at: datetime


class RefundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    refund_no: str
    order_id: int
    user_id: int
    product_id: int
    refund_status: str
    refund_reason: str
    refund_amount: Decimal
    requested_at: datetime
    processed_at: datetime | None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_no: str
    user_id: int
    order_id: int | None
    assigned_user_id: int | None
    ticket_type: str
    priority: str
    status: str
    subject: str
    resolved_at: datetime | None
