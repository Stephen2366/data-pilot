from typing import Any


class NullCache:
    """M2 cache wrapper skeleton.

    Redis is intentionally not connected in M2. Business code can depend on this
    tiny interface later, and the implementation can be swapped without changing
    API route code.
    """

    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        return None


cache = NullCache()
