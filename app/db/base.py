from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base shared by every ORM model.

    ★ 新手理解：Alembic 迁移工具会读取 Base.metadata，它像一张“总目录”，
    只有把所有模型都导入进来，迁移工具才知道项目里有哪些表。
    """


# 导入模型是为了把表注册进 Base.metadata；这些导入不要删除。
from app.models.channels import Channel  # noqa: E402,F401
from app.models.coupons import Coupon  # noqa: E402,F401
from app.models.knowledge_docs import KnowledgeDoc  # noqa: E402,F401
from app.models.order_coupons import OrderCoupon  # noqa: E402,F401
from app.models.order_items import OrderItem  # noqa: E402,F401
from app.models.orders import Order  # noqa: E402,F401
from app.models.orders_wide import OrderWide  # noqa: E402,F401
from app.models.product_categories import ProductCategory  # noqa: E402,F401
from app.models.product_price_history import ProductPriceHistory  # noqa: E402,F401
from app.models.products import Product  # noqa: E402,F401
from app.models.refunds import Refund  # noqa: E402,F401
from app.models.tickets import Ticket  # noqa: E402,F401
from app.models.user_behavior_log import UserBehaviorLog  # noqa: E402,F401
from app.models.users import User  # noqa: E402,F401
