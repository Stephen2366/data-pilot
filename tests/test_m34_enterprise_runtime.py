"""M34 external profile 真实通过 Knowledge Tool、Evidence 和 AnswerFlow 的合同测试。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from engine.governance import test_caller as make_test_caller
from engine.governance import unverified_request_caller
from engine.rag.answer_flow import RAGAnswerRequest
from engine.rag.enterprise_dataset import (
    DatasetAudit,
    DatasetExpectations,
    DatasetRecipe,
    SourceInstance,
)
from engine.rag.enterprise_profile import build_candidate_external_profile
from engine.rag.enterprise_runtime import load_enterprise_profile_runtime
from engine.rag.enterprise_units import UnitRecipe
from engine.rag.evidence import DocumentEvidencePayload
from engine.rag.knowledge_tool import KnowledgeRequest


def _build_runtime(tmp_path: Path, *, allow_cross_thread: bool = False):
    content = (
        "Alpha Approval Policy\n\n"
        "Alpha policy says every production approval requires manager review.\n\n"
        "The reviewer records the decision in the audit log."
    ).encode()
    filename = "dsid_00000000000000000000000000000001__approval.txt"
    relative_path = f"confluence/confluence/{filename}"
    path = tmp_path / "dataset" / "extracted" / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    source = SourceInstance(
        source_type="confluence",
        relative_path=relative_path,
        logical_document_id="dsid_00000000000000000000000000000001",
        semantic_name="approval",
        byte_size=len(content),
        content_sha256=sha256(content).hexdigest(),
        physical_identity="physical-approval-1",
    )
    recipe = DatasetRecipe(
        recipe_version="dataset-runtime-test-v1",
        release_tag="v-test",
        source_types=("confluence",),
        question_filter="source_types_nonempty_subset_of_selected_sources",
        required_assets=(),
        expected=DatasetExpectations(1, 0, 0, 0, 0, {"confluence": 1}),
    )
    audit = DatasetAudit(
        recipe=recipe,
        dataset_root=tmp_path / "dataset",
        source_instances=(source,),
        selected_questions=(),
        conflicting_logical_document_ids=(),
        missing_gold_document_ids=(),
        corpus_identity="corpus-runtime-test",
        question_set_identity="questions-runtime-test",
        dataset_identity="dataset-runtime-test",
    )
    root = tmp_path / "profiles"
    manifest = build_candidate_external_profile(
        root=root,
        audit=audit,
        unit_recipe=UnitRecipe("unit-runtime-test-v1", "paragraph_pack", max_characters=240),
    )
    return load_enterprise_profile_runtime(
        root=root,
        profile_identity=manifest.profile_identity,
        allow_cross_thread=allow_cross_thread,
    )


def test_external_candidate_retrieves_materialized_evidence_with_coordinates(
    tmp_path: Path,
) -> None:
    with _build_runtime(tmp_path) as runtime:
        outcome = runtime.knowledge_tool().retrieve(
            KnowledgeRequest(
                question="What does the Alpha production approval require?",
                caller=make_test_caller(caller_id="m34-test", roles=("admin",)),
                purpose="answer_evidence",
                run_id="m34-runtime-retrieval",
            )
        )

        assert outcome.reason_code == "evidence_retrieved"
        assert len(outcome.selected_evidence) == 1
        evidence = outcome.selected_evidence[0]
        assert isinstance(evidence.payload, DocumentEvidencePayload)
        assert "manager review" in evidence.payload.content
        coordinates = evidence.payload.context_coordinates
        assert coordinates is not None
        assert coordinates.logical_document_id.endswith("00000000000000000000000000000001")
        assert coordinates.physical_source_identity == "physical-approval-1"
        assert coordinates.normalized_end > coordinates.normalized_start
        assert runtime.selection.lifecycle_status == "candidate"


def test_unverified_caller_cannot_make_external_content_visible(tmp_path: Path) -> None:
    with _build_runtime(tmp_path) as runtime:
        outcome = runtime.knowledge_tool().retrieve(
            KnowledgeRequest(
                question="What does the Alpha production approval require?",
                caller=unverified_request_caller(
                    caller_id="request-user", claimed_roles=("admin",)
                ),
                purpose="answer_evidence",
                run_id="m34-runtime-unverified",
            )
        )

        assert outcome.reason_code == "no_authorized_evidence"
        assert outcome.selected_evidence == ()
        assert outcome.diagnostics.adapter_calls == 1


def test_external_evidence_reaches_answer_and_validated_citation(tmp_path: Path) -> None:
    with _build_runtime(tmp_path) as runtime:
        result = runtime.answer_flow().run(
            RAGAnswerRequest(
                question="What does the Alpha production approval require?",
                caller=make_test_caller(caller_id="m34-answer", roles=("demo_user",)),
                run_id="m34-runtime-answer",
            )
        )

        assert result.answer_status == "complete"
        assert result.safety_status == "passed"
        assert result.reason_code == "answer_completed"
        assert result.answer is not None and "manager review" in result.answer
        assert len(result.citations) == 1
        assert result.citations[0].authority_ref.startswith("enterprise-rag-bench/")
        evidence = result.gate_decision.context.evidence[0]  # type: ignore[union-attr]
        assert isinstance(evidence.payload, DocumentEvidencePayload)
        assert evidence.payload.context_coordinates is not None
        assert result.ledger.stage_of(evidence.ref.evidence_id) == "cited"


def test_m44a_shared_read_only_runtime_serializes_concurrent_sqlite_access(tmp_path: Path) -> None:
    """lifespan 共享一条只读 connection 时，多请求仍应各自得到完整 Evidence。"""

    with _build_runtime(tmp_path, allow_cross_thread=True) as runtime:
        tool = runtime.knowledge_tool()

        def retrieve(index: int):
            return tool.retrieve(
                KnowledgeRequest(
                    question="What does the Alpha production approval require?",
                    caller=make_test_caller(caller_id=f"m44a-thread-{index}", roles=("demo_user",)),
                    purpose="answer_evidence",
                    run_id=f"m44a-concurrent-{index}",
                )
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(retrieve, range(8)))

    assert all(item.reason_code == "evidence_retrieved" for item in outcomes)
    assert all(len(item.selected_evidence) == 1 for item in outcomes)
