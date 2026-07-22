from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

"""资源 Read Schema：定义商品/订单/退款/工单的 API 返回字段。

★ 每个 Read Schema 对应一张业务表的"对外展示视图"，
敏感字段不暴露，字段类型适配 JSON 序列化（如 Decimal 保持财务精度）。
"""

class ProductRead(BaseModel):
    """商品的 API 出参模型（Read = 只读展示，不用于写入）。

    ★ `from_attributes=True` 让 Pydantic 直接从 ORM 对象读取属性完成转换（类比 Java 里
    把 Entity 映射成 DTO / VO），路由函数返回 ORM 对象即可自动序列化成 JSON。
    Read 模型只暴露业务需要的字段，用户邮箱 / 手机号等敏感字段不出现在这批模型里。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    product_name: str
    category_id: int | None
    category: str
    status: str
    price: Decimal
    launched_at: datetime | None


class OrderRead(BaseModel):
    """订单的 API 出参模型：字段与 orders 表对应，金额用 Decimal 保证财务精度。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    source_order_no: str | None
    external_order_no: str | None
    user_id: int
    product_id: int
    channel_id: int
    order_status: str
    order_amount: Decimal
    shipping_amount: Decimal
    discount_amount: Decimal
    actual_amount: Decimal
    quantity: int
    paid_at: datetime | None


class RefundRead(BaseModel):
    """退款的 API 出参模型：processed_at 可能为 None（退款尚未处理完成）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    refund_no: str
    source_order_no: str | None
    order_id: int
    order_item_id: int | None
    user_id: int
    product_id: int
    refund_status: str
    refund_reason: str
    refund_amount: Decimal
    requested_at: datetime
    processed_at: datetime | None


class TicketRead(BaseModel):
    """工单的 API 出参模型：order_id / assigned_user_id 允许为 None（未关联订单 / 未指派）。"""

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
