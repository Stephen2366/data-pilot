"""M27 Evaluator 的内部 seam。

Evaluator 对外只有 ``evaluate(run_spec)``；这些 Protocol 只让实现替换 FastAPI/SQLite 与测试 fake，
不把网络、数据库或文件系统细节泄漏给 CLI/报告调用方。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from eval.contracts import EvalRun, ObservabilityEvidence, ScenarioRun, dataclass_payload, safe_eval_run_payload


class PipelinePort(Protocol):
    """一次候选请求的执行 seam；一个 replicate 只允许调用一次。"""

    def execute(self, *, question: str, user_role: str, pipeline_mode: str, fusion_strategy: str) -> tuple[int, dict[str, Any], tuple[dict[str, Any], ...], ObservabilityEvidence]:
        """返回 HTTP 状态、结构化响应和该请求唯一 trace 的步骤。"""


class OraclePort(Protocol):
    """与 PipelinePort 共用 snapshot 的 reference SQL 执行 seam。"""

    def execute(self, reference_sql: str) -> tuple[dict[str, Any], ...]:
        """执行确定性 reference SQL；异常由 Evaluator 记为 oracle_error。"""


class RunEnvironment(Protocol):
    """一轮 run 的资源所有者；不是 ports 的转发容器。"""

    pipeline: PipelinePort
    oracle: OraclePort
    resolved_runtime_identity: ResolvedRuntimeIdentity

    def close(self) -> None:
        """释放 seed、TestClient、vector index 等整轮资源。"""


class RunEnvironmentFactory(Protocol):
    """根据 run spec 创建单一环境；显式 runtime mismatch 应在此处 fail fast。"""

    def create(self, run_spec: EvalRunSpec) -> RunEnvironment:
        """创建并完成 requested/resolved 对账。"""


class CheckpointStore(Protocol):
    """crash-safe persistence seam；M27A 先保证识别 partial run，不承诺 resume。"""

    def start(self, run: EvalRun) -> None: ...

    def checkpoint(self, scenario_run: ScenarioRun) -> None: ...

    def finalize(self, run: EvalRun) -> None: ...

    def fail(self, run: EvalRun) -> None: ...


class MemoryCheckpointStore:
    """测试用 adapter：保留调用顺序和写入内容，不接触真实文件系统。"""

    def __init__(self) -> None:
        self.started: list[EvalRun] = []
        self.checkpoints: list[ScenarioRun] = []
        self.finalized: list[EvalRun] = []
        self.failed_runs: list[EvalRun] = []

    def start(self, run: EvalRun) -> None:
        """创建不可复用的 running manifest，作为 crash-safe 生命周期起点。"""
        self.started.append(run)

    def checkpoint(self, scenario_run: ScenarioRun) -> None:
        """原子保存一个已完成 ScenarioRun 的短期原始 checkpoint。"""
        self.checkpoints.append(scenario_run)

    def finalize(self, run: EvalRun) -> None:
        """仅为 completed run 落盘脱敏长期 artifact。"""
        self.finalized.append(run)

    def fail(self, run: EvalRun) -> None:
        """把 failed/interrupted lifecycle 写回 manifest，保留 partial evidence。"""
        self.failed_runs.append(run)


class FileCheckpointStore:
    """本地 crash-safe checkpoint adapter。

    manifest/checkpoint 位于 gitignored 临时根目录；只有 completed EvalRun 才会原子写入长期
    artifact 根目录。M27A 不提供 resume，因此任何同 run_id 的再次启动都明确拒绝。
    """

    def __init__(self, *, checkpoint_root: Path, artifact_root: Path) -> None:
        self._checkpoint_root = checkpoint_root
        self._artifact_root = artifact_root

    def start(self, run: EvalRun) -> None:
        run_dir = self._run_dir(run.run_id)
        manifest = run_dir / "manifest.json"
        if manifest.exists():
            raise FileExistsError(f"run_id already exists; resume is not implemented: {run.run_id}")
        run_dir.mkdir(parents=True, exist_ok=False)
        self._write_atomic(manifest, dataclass_payload(run))

    def checkpoint(self, scenario_run: ScenarioRun) -> None:
        run_dir = self._run_dir(scenario_run.evidence.run_id)
        path = run_dir / "checkpoints" / f"{scenario_run.scenario_id}--r{scenario_run.replicate_id}.json"
        if path.exists():
            raise FileExistsError(f"duplicate scenario checkpoint: {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(path, dataclass_payload(scenario_run))

    def finalize(self, run: EvalRun) -> None:
        if run.run_status != "completed":
            raise ValueError("only completed runs may finalize")
        self._write_atomic(self._run_dir(run.run_id) / "manifest.json", dataclass_payload(run))
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        # ★ 长期 artifact 和短期 checkpoint 的保留策略不同：final JSON 必须先经过 allowlist。
        self._write_atomic(self._artifact_root / f"{run.run_id}.json", safe_eval_run_payload(run))

    def fail(self, run: EvalRun) -> None:
        self._write_atomic(self._run_dir(run.run_id) / "manifest.json", dataclass_payload(run))

    def inspect_lifecycle(self, run_id: str) -> str:
        """读取遗留 manifest；running 永不被投影为 completed，resume 前视为 abandoned。"""

        manifest = self._run_dir(run_id) / "manifest.json"
        if not manifest.is_file():
            raise FileNotFoundError(manifest)
        status = str(json.loads(manifest.read_text(encoding="utf-8")).get("run_status", ""))
        return "abandoned" if status == "running" else status

    def _run_dir(self, run_id: str) -> Path:
        """校验 run id 不能逃逸 checkpoint 根目录。"""
        if not run_id or any(part in {"", ".", ".."} for part in Path(run_id).parts) or len(Path(run_id).parts) != 1:
            raise ValueError(f"unsafe run_id: {run_id!r}")
        return self._checkpoint_root / run_id

    @staticmethod
    def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
        """通过同目录临时文件替换，避免半写 JSON 被读取为完成产物。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        os.replace(temporary, path)
