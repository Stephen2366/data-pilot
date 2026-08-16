"""M35 顶层单轮 Harness。

这个 package 的 public interface 只有 ``run_harness`` 与几份跨节点合同。SQL 和 RAG 的复杂
流程仍留在各自深 module；Harness 只负责一次路由、一次受控调用与统一终止。
"""

from engine.harness.graph import HarnessRuntime, build_harness, run_harness

__all__ = ["HarnessRuntime", "build_harness", "run_harness"]
