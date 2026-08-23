"""Phase 4B 共享的 canonical content identity 小模块。

★ identity 描述内容，不描述文件放在哪里或何时写入。这样移动项目外 artifact 不会改变
语义身份，而正文、配置或 recipe 的任意变化都会改变哈希。
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


def canonical_json(payload: Any) -> str:
    """把 JSON 兼容对象规范化成稳定文本；集合必须由调用者先转成有序列表。"""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(payload: Any) -> str:
    """返回规范 JSON 的 SHA-256，用于 recipe/catalog/artifact 的内容身份。"""

    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """流式计算文件哈希；不把大 artifact 一次读入内存。"""

    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
