"""Phase 4 文档知识能力。

这里只保留 M30 catalog 的稳定短入口。M31 governance、Evidence 和 release 相互有明确依赖
方向，调用方应从对应子模块导入，避免一个聚合 ``__init__`` 重新制造循环依赖和万能接口。
"""

from engine.rag.catalog import (
    CatalogBuildError,
    CatalogBuildRecipe,
    CatalogEntry,
    StagedCatalog,
    build_staged_catalog,
)

__all__ = [
    "CatalogBuildError",
    "CatalogBuildRecipe",
    "CatalogEntry",
    "StagedCatalog",
    "build_staged_catalog",
]
