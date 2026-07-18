from typing import Any


class NullCache:
    """M2 缓存 wrapper 骨架：接口在、实现为空（即“Null Object 模式”）。

    ★ 为什么不直接接 Redis：M2 主线是 API / 日志 / 异常，不让缓存环境问题拖慢主线
    （计划允许的降级边界）。业务代码只依赖 get / set 这个小接口，后续把 NullCache
    换成真实 RedisCache 时，路由和业务代码一行不用改——类似 Spring 里先注入一个
    空实现的 CacheManager 占住扩展点。
    """

    def get(self, key: str) -> Any | None:
        # 空实现：永远视为“缓存未命中”，调用方自然回源数据库查询。
        return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        # 空实现：写入直接丢弃；ttl_seconds 先占位，保持与真实缓存一致的方法签名。
        return None


# 全局共享的缓存入口：业务代码统一 `from app.core.cache import cache`，不自行 new，
# 未来替换实现时只改这一处。
cache = NullCache()
