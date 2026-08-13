"""Phase 4 文档知识能力。

M30 只在这里建立可信原件到 ``staged catalog`` 的边界；检索、Knowledge Tool、
Evidence/citation 和 active 发布仍属于后续模块。
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
