"""Phase 4B 的版本化前置合同。

M42 只把 B0 的 seed、场景、兼容和评测身份冻结成可复用 interface；真正的 Task runtime
从 M43 开始实现。把这些合同放进独立 package，可以避免未来 Agent family 静默改变 M35–M41
legacy runtime 的字段和预算。
"""

from engine.phase4b.contracts import B0ContractBundle, load_b0_contract_bundle
from engine.phase4b.identity import canonical_hash, file_sha256

__all__ = ["B0ContractBundle", "canonical_hash", "file_sha256", "load_b0_contract_bundle"]
