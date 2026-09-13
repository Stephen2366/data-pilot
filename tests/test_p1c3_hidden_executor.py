"""P1-C3 Hidden executor 的零 provider 合同、恢复与最小披露测试。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.evoloop_hidden_executor import (
    BOUNDARY,
    PRIVATE_RESULT_SCHEMA,
    HiddenBeforeProviderError,
    HiddenExecutionError,
    HiddenPrivateStore,
    _digest,
    _envelope,
    _provider_usage_from_scenario_run,
    build_development_offer,
    build_execution_request,
    execute_hidden_baseline,
    validate_development_fixture,
    validate_ordinary_completion,
)
from eval.evoloop_hidden_material import build_public_offer, validate_hidden_material
from eval.run_evoloop_hidden import main as hidden_cli
from eval.export_evoloop_baseline_inputs import main as export_inputs
from tests.evoloop_sample_material import development_sample, formal_sample, write_samples

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "a" * 64


def _material() -> dict:
    return validate_hidden_material(formal_sample())


def _request(material: dict, *, run_id: str = "hidden-fixture") -> dict:
    return build_execution_request(
        run_id=run_id,
        purpose="formal_baseline",
        offer=build_public_offer(material),
        candidate_digest=DIGEST,
        authorization_digest="sha256:" + "b" * 64,
        world={
            "runtime_digest": "sha256:" + "c" * 64,
            "scorer_digest": "sha256:" + "d" * 64,
            "oracle_digest": "sha256:" + "e" * 64,
        },
        budget={"max_logical_works": 4, "max_physical_requests": 8, "max_observed_tokens": 1000, "max_wall_seconds": 30},
        model={"provider": "qwen", "model": "qwen3.7-plus", "temperature": 0, "retry": 0},
    )


def _fake_result(case: dict, _request_payload: dict, attempt_id: str) -> dict:
    return _envelope(PRIVATE_RESULT_SCHEMA, {
        "attempt_id": attempt_id,
        "case_id": case["case_id"],
        "scenario_run": {"assertion_results": [{"status": "passed"}]},
        "runtime": {"values": {"fixture": case["fixture"]["fixture_id"]}},
        "usage": {
            "logical_work_count": 1, "physical_request_count": 1,
            "input_tokens": 1, "output_tokens": 0, "total_tokens": 1,
            "requests": [{
                "stage": "fixture", "provider": "Qwen", "model": "qwen3.7-plus", "request_count": 1,
                "input_tokens": 1, "output_tokens": 0, "total_tokens": 1,
            }],
        },
        "source": {"execution_status": "completed", "physical_attempts": 1, "trace_present": True},
    })


def test_provider_usage_accepts_projected_dict_trace_steps() -> None:
    """真实 API 路径会把 TraceStep 投影成 dict，usage reader 不应只支持 dataclass。"""

    call = {
        "stage": "query_plan", "provider": "Qwen", "model": "qwen3.7-plus",
        "configured_timeout_seconds": 120.0, "max_retries": 0, "attempt_count": 1,
        "prompt_length": 10, "system_prompt_length": 2, "final_outcome": "success",
        "attempts": [{
            "attempt": 1, "latency_ms": 5.0, "outcome": "success", "error_subtype": None,
            "retryable": False, "error_message": None,
        }],
        "usage": {
            "observed": True, "request_count": 1, "prompt_tokens": 7,
            "completion_tokens": 3, "total_tokens": 10,
        },
    }
    scenario_run = SimpleNamespace(evidence=SimpleNamespace(trace_steps=[{"metadata": {"llm_call": call}}]))
    usage = _provider_usage_from_scenario_run(scenario_run)
    assert usage["physical_request_count"] == 1
    assert usage["total_tokens"] == 10


def test_four_fake_works_publish_minimal_completion_and_reopen(tmp_path: Path) -> None:
    material = _material()
    request = _request(material)
    store = HiddenPrivateStore.create(tmp_path / "run", request)
    completion = execute_hidden_baseline(material_value=material, request=request, store=store, executor=_fake_result)
    payload = validate_ordinary_completion(completion, expected_request_digest=request["digest"])
    assert payload["state"] == "completed"
    assert payload["boundary"] == BOUNDARY
    assert payload["aggregate_usage"] == {"physical_request_count": 4, "input_tokens": 4, "output_tokens": 0, "total_tokens": 4}
    assert payload["usage_ledger_digest"].startswith("sha256:")
    assert execute_hidden_baseline(material_value=material, request=request, store=store, executor=_fake_result) == completion
    assert len(store.read().terminal_digests) == 4
    ordinary = json.dumps(completion, ensure_ascii=False).lower()
    for forbidden in ("case_id", "question", "gold", "expected_rows", "verdict", "passed_count", "failed_count"):
        assert forbidden not in ordinary


def test_before_start_terminal_and_started_unknown_fail_closed(tmp_path: Path) -> None:
    material = _material()
    request = _request(material, run_id="failure-matrix")
    store = HiddenPrivateStore.create(tmp_path / "before", request)

    def before(*_args):
        raise HiddenBeforeProviderError("fixture invalid")

    with pytest.raises(HiddenBeforeProviderError):
        execute_hidden_baseline(material_value=material, request=request, store=store, executor=before)
    assert next(iter(store.read().states.values())) == "failed_before_start"
    with pytest.raises(HiddenExecutionError, match="cannot resume"):
        execute_hidden_baseline(material_value=material, request=request, store=store, executor=_fake_result)

    unknown = HiddenPrivateStore.create(tmp_path / "unknown", request)
    first = material["cases"][0]
    unknown.append(attempt_id="ha-unknown", case_id=first["case_id"], state="started")
    with pytest.raises(HiddenExecutionError, match="cannot resume"):
        execute_hidden_baseline(material_value=material, request=request, store=unknown, executor=_fake_result)


def test_identity_drift_old_attempt_overwrite_and_completion_tamper_are_rejected(tmp_path: Path) -> None:
    material = _material()
    request = _request(material, run_id="identity-matrix")
    store = HiddenPrivateStore.create(tmp_path / "run", request)
    drifted = copy.deepcopy(request)
    drifted["payload"]["candidate_digest"] = "sha256:" + "f" * 64
    drifted["digest"] = _digest(drifted["payload"])
    with pytest.raises(HiddenExecutionError, match="stored request"):
        execute_hidden_baseline(material_value=material, request=drifted, store=store, executor=_fake_result)

    case_id = material["cases"][0]["case_id"]
    store.append(attempt_id="ha-first", case_id=case_id, state="started")
    with pytest.raises(HiddenExecutionError, match="cannot be overwritten"):
        store.append(attempt_id="ha-second", case_id=case_id, state="started")

    completed_store = HiddenPrivateStore.create(tmp_path / "complete", request)
    completion = execute_hidden_baseline(material_value=material, request=request, store=completed_store, executor=_fake_result)
    tampered = copy.deepcopy(completion)
    tampered["payload"]["passed_count"] = 4
    tampered["digest"] = _digest(tampered["payload"])
    with pytest.raises(HiddenExecutionError):
        validate_ordinary_completion(tampered)


@pytest.mark.parametrize("mutation", ["missing", "unknown", "negative", "aggregate"])
def test_hidden_usage_missing_unknown_negative_or_tampered_fails_closed(tmp_path: Path, mutation: str) -> None:
    material = _material()
    request = _request(material, run_id=f"usage-{mutation}")
    store = HiddenPrivateStore.create(tmp_path / mutation, request)

    def broken_executor(case: dict, request_payload: dict, attempt_id: str) -> dict:
        result = _fake_result(case, request_payload, attempt_id)
        usage = result["payload"]["usage"]
        if mutation == "missing":
            usage.pop("requests")
        elif mutation == "unknown":
            usage["future"] = True
        elif mutation == "negative":
            usage["requests"][0]["input_tokens"] = -1
        else:
            usage["total_tokens"] += 1
        result["digest"] = _digest(result["payload"])
        return result

    with pytest.raises(HiddenExecutionError):
        execute_hidden_baseline(material_value=material, request=request, store=store, executor=broken_executor)


def test_prepare_cli_is_zero_provider_and_refuses_overwrite(tmp_path: Path) -> None:
    _, development_path = write_samples(tmp_path)
    output = tmp_path / "cli-run"
    request = tmp_path / "request.json"
    args = [
        "prepare", "--material", str(development_path), "--output-root", str(output), "--request", str(request),
        "--run-id", "cli-fixture", "--purpose", "development_probe",
        "--candidate-digest", DIGEST, "--authorization-digest", "sha256:" + "b" * 64,
        "--runtime-digest", "sha256:" + "c" * 64, "--scorer-digest", "sha256:" + "d" * 64,
        "--oracle-digest", "sha256:" + "e" * 64,
    ]
    assert hidden_cli(args) == 0
    assert request.is_file()
    assert (output / "private/request.json").is_file()
    assert not (output / "ordinary-completion.json").exists()
    with pytest.raises(SystemExit):
        hidden_cli(args)


def test_development_singleton_is_separate_and_cannot_consume_formal_material(tmp_path: Path) -> None:
    development = validate_development_fixture(development_sample())
    request = build_execution_request(
        run_id="development-singleton",
        purpose="development_probe",
        offer=build_development_offer(development),
        candidate_digest=DIGEST,
        authorization_digest="sha256:" + "b" * 64,
        world={"runtime_digest": "sha256:" + "c" * 64, "scorer_digest": "sha256:" + "d" * 64, "oracle_digest": "sha256:" + "e" * 64},
        budget={"max_logical_works": 1, "max_physical_requests": 2, "max_observed_tokens": 6000, "max_wall_seconds": 180},
        model={"provider": "qwen", "model": "qwen3.7-plus", "temperature": 0, "retry": 0},
    )
    store = HiddenPrivateStore.create(tmp_path / "development", request)
    completion = execute_hidden_baseline(material_value=development, request=request, store=store, executor=_fake_result)
    assert validate_ordinary_completion(completion)["version"] == "datapilot-hidden-development-probe-v1"
    assert len(store.read().terminal_digests) == 1
    formal = _material()
    with pytest.raises(HiddenExecutionError):
        execute_hidden_baseline(material_value=formal, request=request, store=store, executor=_fake_result)


def test_public_preparation_export_is_zero_provider_and_separates_offers(tmp_path: Path) -> None:
    formal_path, development_path = write_samples(tmp_path)
    output = tmp_path / "public-inputs.json"
    assert export_inputs([
        "--formal-material", str(formal_path),
        "--development-material", str(development_path),
        "--output", str(output),
    ]) == 0
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["schema"] == "datapilot.evoloop-baseline-public-inputs/v1"
    assert len([item for item in value["catalog_projection"]["scenarios"] if item["classification"] == "core"]) == 19
    assert value["formal_hidden_offer"]["expected_count"] == 4
    assert value["development_hidden_offer"]["expected_count"] == 1
    assert value["formal_hidden_offer"]["private_digest"] != value["development_hidden_offer"]["private_digest"]
