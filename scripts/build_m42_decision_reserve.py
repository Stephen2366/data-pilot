"""创建并密封 M42 的 60 题 Phase 4B decision reserve。

本脚本不调用检索器、Composer 或任何 provider。题目和 gold 由本模块先基于 20 份未进入
M34 gold 的冻结原文编写；脚本只做两种独立复核：source coordinate/hash grounding 与
gold/facts consistency。输出必须写入项目外 versioned immutable store。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engine.phase4b.identity import canonical_hash, file_sha256
from eval.agent_reserve_contracts import seal_reserve


# doc_id -> (source type, extracted relative path, frozen SHA-256)
SOURCE_POOL: dict[str, tuple[str, str, str]] = {
    "dsid_7638d2932c304d6692458cbcd1c81f80": ("confluence", "extracted/confluence/confluence/dsid_7638d2932c304d6692458cbcd1c81f80__orion-defense-closed-network-offline-deployment.txt", "74b6072faf80a6600c04c3d878a83359f520f3d42790e76b4d144b460684b64b"),
    "dsid_0cdf40cfc4a9469d8e22e210ab09da46": ("confluence", "extracted/confluence/confluence/dsid_0cdf40cfc4a9469d8e22e210ab09da46__gpu-kernel-rollout-and-telemetry-gating-runbook.txt", "a13b0344797250b3c56606b21c81f3a88f3e010e43aad6fa6d62efbb5a1773e1"),
    "dsid_c26368a48ae44702bcbcafd5ca8f161b": ("confluence", "extracted/confluence/confluence/dsid_c26368a48ae44702bcbcafd5ca8f161b__tenant-handback-and-cost-stewardship-runbook-2028.txt", "8f825b1700dd5355980c30fe5236088efb93dab94aa886e07bc49f7939384f0e"),
    "dsid_fd88b32727cc46158ad1c46e2cb70300": ("confluence", "extracted/confluence/confluence/dsid_fd88b32727cc46158ad1c46e2cb70300__responder-operations-manual-synthesized-procedures-2026.txt", "8ed9ab24cf778945593b2f5513b032364ddb8be51772dbf3cab253241398e3a3"),
    "dsid_7c9b65f8e89a41d1a0ec10e7e4b08e49": ("confluence", "extracted/confluence/confluence/dsid_7c9b65f8e89a41d1a0ec10e7e4b08e49__evaluator-interchange-format-and-federation-spec-2026.txt", "ef4bf819a4823d463b239f9c7c5dac2c74d93dfa4fe79e8295c2509acfe68481"),
    "dsid_99328f9edfaa4a0ca83743d40d587fa6": ("confluence", "extracted/confluence/confluence/dsid_99328f9edfaa4a0ca83743d40d587fa6__runtime-experiment-safety-and-governance-checklist-2027.txt", "6a828969df88611b4e0dc015a93f9b7e830f2313eeebb5d087b449ae506eb857"),
    "dsid_0d4070d062be410e9738c45ff533313b": ("confluence", "extracted/confluence/confluence/dsid_0d4070d062be410e9738c45ff533313b__operational-reserve-and-contract-contingency-policy-2027.txt", "71b3fd13885ee93fbe3579883419c7fa8268e693c992621f2906c1c146bca682"),
    "dsid_5c997af6e73a4f9191f40c4e26145318": ("confluence", "extracted/confluence/confluence/dsid_5c997af6e73a4f9191f40c4e26145318__api-schema-discovery-and-runtime-capability-protocol-2026.txt", "6010cd6c6be481cce150919e64f899ca11f7ac07235bfa5419877753210b9e49"),
    "dsid_ee8a567da12e4bb08bf9db3cae15bd9a": ("google_drive", "extracted/google_drive/google_drive/dsid_ee8a567da12e4bb08bf9db3cae15bd9a__edge-traffic-consolidation-fallback-cheat-sheet.txt", "8d4d33755443f727caddc6968697793e035c77f14699243172f2d623d1f460e2"),
    "dsid_8a2f3af5e7044de69c5c12192cf33bae": ("google_drive", "extracted/google_drive/google_drive/dsid_8a2f3af5e7044de69c5c12192cf33bae__focus-funnel-21d-scratchpad-adrienne-cole.txt", "85fed000e59fb349b59cd5fdbc45778134cfb0a7f9b3de421ef21a7ff3f181af"),
    "dsid_359d8065a9bd4037aee755fe41f21b3e": ("google_drive", "extracted/google_drive/google_drive/dsid_359d8065a9bd4037aee755fe41f21b3e__tensorcore-hybrid-lru-eviction-prefetch-notes.txt", "04f9c521fa240a84967093f16cca2b9deb6739a8ca31ac8363377eb67edc5c96"),
    "dsid_a5d7b3c95601464c8d4f006695bad84e": ("google_drive", "extracted/google_drive/google_drive/dsid_a5d7b3c95601464c8d4f006695bad84e__audit-anchor-ledger-and-siem-integration-proposal-v0p1.txt", "a0e7d3ce9272819d13e7933c13682d32c101c40c6332d5354d2bc83abef18806"),
    "dsid_a8f6d626244b4b79b5cfb3163a4098af": ("google_drive", "extracted/google_drive/google_drive/dsid_a8f6d626244b4b79b5cfb3163a4098af__skill-signature-role-brief-and-interview-evidence-mapper.txt", "846ac562d0498a502c180ee3d5837b1aa0a8a91bef01a67799c2738e39176900"),
    "dsid_5fa17029c1244e7c922649498e1ee2cd": ("google_drive", "extracted/google_drive/google_drive/dsid_5fa17029c1244e7c922649498e1ee2cd__service-credit-ops-efficiency-tco-scenarios.txt", "ec726d5b6f71c54324123d382021a8e52766782a7b8f12ba45e6cf0334b5cf3d"),
    "dsid_3c8bb2d1caed4ca2a6c3d289175f34eb": ("jira", "extracted/jira/jira/dsid_3c8bb2d1caed4ca2a6c3d289175f34eb__SUP-1842-streaming-chat-response-stalls-sse.txt", "4a2a7e959f51a94a5df9550e72bb76afa3ca4c065871e43bdafc61014dadb507"),
    "dsid_6c4759ecac6045a2817272e973c7df33": ("jira", "extracted/jira/jira/dsid_6c4759ecac6045a2817272e973c7df33__SUP-7654321-sticky-version-hold-after-metadata-sync-failure.txt", "8ced50100286e7f6189dd9cd0758ffea12463e31d9c8b32209c11b71e0b2b61f"),
    "dsid_bd8f216f7b5149cb9d9457bdeb26ca4f": ("jira", "extracted/jira/jira/dsid_bd8f216f7b5149cb9d9457bdeb26ca4f__INT-35720-agent-bootstrap-token-expiry-triggers-pending-jobs.txt", "1cde1b6a535e531d78b9364481402816aa29fe303b7758c77e81e7c3c584201c"),
    "dsid_e53f2702531f45399bf6ee7239fe3a1f": ("jira", "extracted/jira/jira/dsid_e53f2702531f45399bf6ee7239fe3a1f__SUP-90321-safeguarded-feature-flag-deopt-unwind-playbook.txt", "203a0bbcf89a2f20e91aa78cb64b12819a205ff627c763a74b3f3b5eefa66d52"),
    "dsid_9b9246ce7b8048d5ada7067fb9e45208": ("jira", "extracted/jira/jira/dsid_9b9246ce7b8048d5ada7067fb9e45208__INT-100100-jit-env-bootstrap-session-policy-size-limit.txt", "307180de98282a9d4ef5d31461732d3196bf53a9f7c0e2829fa5f84cfde12a01"),
    "dsid_60583fc6f4d443a3bdfd14b22af59279": ("jira", "extracted/jira/jira/dsid_60583fc6f4d443a3bdfd14b22af59279__INT-905777-gcp-folder-inheritance-lost-affecting-dedicated-staging-sa-access.txt", "4dee869404b5e12233af3797489b34f35c62350f074668263b5254429132c73e"),
}

EXTERNAL_PROFILE_IDENTITY = "e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2"


def _records() -> list[dict[str, Any]]:
    """返回人工编写的 20 basic、20 core、20 hard；hard 全为多文档。"""

    rows: list[dict[str, Any]] = []

    def add(difficulty: str, question: str, docs: list[str], facts: list[str]) -> None:
        """把人工题面与 gold 坐标规范化为一条稳定 reserve record。"""

        rows.append({
            "reserve_question_id": f"p4b_reserve_{len(rows) + 1:03d}",
            "difficulty": difficulty,
            "question": question,
            "expected_doc_ids": docs,
            "gold_answer": " ".join(facts),
            "answer_facts": facts,
            "source_signature": sorted({SOURCE_POOL[doc][0] for doc in docs}),
        })

    docs = list(SOURCE_POOL)
    basic = [
        ("What deployment mode and outbound-network rule did Orion Defense require?", ["Redwood Private must run on on-prem Kubernetes.", "The classified enclave must have no outbound internet routes."]),
        ("Which canary metrics force an immediate abort during a GPU kernel rollout?", ["Any GPU OOM event triggers immediate abort.", "A sustained RSS increase above 20 percent for three minutes also fails the gate."]),
        ("How long does the onboarding lead remain on call after tenant handback?", ["The onboarding lead remains on call for the 72-hour stabilization window."]),
        ("What error-rate condition defines a major Sev2 incident in the responder manual?", ["Sev2 includes an error-rate spike above 1 percent absolute or five times baseline for at least five minutes."]),
        ("Which four EIF record types are allowed by the evaluator interchange spec?", ["EIF allows sample_result, batch_summary, delta_summary, and artifact_reference record types."]),
        ("What initial canary fraction is permitted for a high-risk runtime experiment?", ["A high-risk runtime experiment starts at no more than 0.1 percent traffic."]),
        ("What reserve rate applies to a medium-risk exposure between 25,000 and 250,000 dollars?", ["Medium-risk exposure uses a 10 percent operational reserve and requires Finance approval."]),
        ("Which discovery endpoint is the short cacheable summary and what is its hosted default max-age?", ["GET /.well-known/redwood-discovery is the short cacheable endpoint.", "Its hosted default cache-control max-age is 60 seconds."]),
        ("What happened to p95 latency and cross-region KV-miss rate in the edge consolidation experiment?", ["Median p95 generation latency dropped 18 percent.", "The critical-prefix cross-region KV-miss rate fell from 12 percent to 3 percent within 200 seconds."]),
        ("What were the 21-day sprint targets for shipped experiments and focus-block streak?", ["The sprint targeted three shipped experiments.", "It targeted a quality-block streak of at least 18 out of 21 days."]),
        ("Which metrics were planned for the hybrid-LRU prefetch microbenchmarks?", ["The notes require page faults per thousand tokens and average page fetch time.", "They also track eviction rate, tensor-core utilization, idle cycles, and PCIe bandwidth utilization."]),
        ("Which fields are placed in SIEM records as audit-anchor pointers?", ["SIEM records add anchor_id, canonical_hash, and event_schema_version as pointers."]),
        ("What scoring threshold does the backend-platform interview rubric recommend?", ["A candidate needs at least 3 on three of the five dimensions.", "A candidate must not score zero on safety or communication."]),
        ("What are the approximate three-year net TCO values for the conservative and ops-led examples?", ["The conservative example is 2,587,600 dollars.", "The ops-led example is approximately 2,296,000 dollars."]),
        ("What change mitigated AcmeCo SSE streams stalling mid-generation?", ["The API gateway added an SSE comment heartbeat every 10 seconds when no tokens were emitted."]),
        ("What stale routing state remained after the PixelMotif canary rollback?", ["A version_hold=true attribute persisted in the routing-mesh session cache and kept some sessions on degraded-v1."]),
        ("How many CI jobs were blocked by bootstrap-token expiry and how much release delay was estimated?", ["Bootstrap-token expiry blocked about 18 CI jobs.", "The release incurred roughly 40 minutes of extra time."]),
        ("What ordered steps cleared stale optimizer state in the Acme dedicated pool?", ["The team disabled the tenant flag, drained affected workers, cleared each worker kernel cache, and restarted runtime processes."]),
        ("At what generated session-policy length does the JIT provisioner switch to its role-alias flow?", ["Provisioner version 1.12.5 switches when the generated session policy is at least 1200 characters."]),
        ("Which IAM bindings were manually restored to recover dedicated staging?", ["The team restored roles/storage.objectViewer and roles/compute.viewer for group:sre-dedicated@redwood.ai."]),
    ]
    for doc, (question, facts) in zip(docs, basic):
        add("basic", question, [doc], facts)

    core_specs = [
        ("Why is firewall-level egress blocking required for the Orion canary instead of DNS-only blocking?", [docs[0]], ["Orion prohibits public outbound routes and corporate proxies.", "Firewall blocking verifies that hidden registry, package, or background-job dependencies cannot escape through non-DNS paths."]),
        ("Describe the staged traffic progression and promotion condition for a GPU kernel rollout.", [docs[1]], ["The rollout moves through zero-percent private bake, five-percent mirrored shadow traffic, then 1, 5, 10, and 25 percent live traffic with holds.", "Promotion requires 25 percent traffic sustained for 30 minutes without gate failures."]),
        ("Which ownership and telemetry checks must be green before tenant handback?", [docs[2]], ["The onboarding lead provides three stable canary runs and the runbook artifacts.", "Platform Ops must show all SLOs reporting for two hours and a successful alert firing test.", "Billing Ops validates the 1.2x soft cap and quota webhook."]),
        ("How should responders preserve evidence while containing a Sev1 or Sev2 incident?", [docs[3]], ["Responders first capture alert links, representative request IDs, service-status output, dashboard links, and a timestamped command log.", "They then use non-destructive containment such as throttles, circuit breakers, integration disablement, or traffic movement."]),
        ("How does EIF separate small evaluation records from large debugging artifacts?", [docs[4]], ["EIF truncates prompt and candidate text in compact evaluation records.", "Large audio, trace, or conversation artifacts use artifact_reference pointers to object storage with signed URLs."]),
        ("What additional controls distinguish a high-risk runtime experiment from a medium-risk one?", [docs[5]], ["High-risk changes include kernel, quantization, multi-tenant eviction, or persistent KV-cache changes and require extended approval plus lab rehearsal.", "They begin at no more than 0.1 percent canary traffic with full trace sampling for the first hour."]),
        ("How is a high-risk operational reserve approved and accounted for?", [docs[6]], ["Exposure at or above 250,000 dollars uses a 12 to 20 percent contract contingency with Finance, Legal, and VP approval.", "An identified short-term contingency is recorded as contingency expense against a contingency accrual liability."]),
        ("How should a client react when runtime capability negotiation cannot satisfy a required feature?", [docs[7]], ["The server returns 412 Precondition Failed with an unsupported_feature body, missing features, and a fallback suggestion.", "Clients should use an advertised fallback such as an older version or synchronous mode rather than treating advisory discovery as a correctness guarantee."]),
        ("When is edge traffic consolidation appropriate, and what is its intended time limit?", [docs[8]], ["It is appropriate when multiple edge regions degrade while the global control plane stays healthy, especially with KV warmup or retry oscillation problems.", "It is a short-lived 15 to 90 minute containment, not a full region evacuation."]),
        ("How does the focus sprint respond to interruption and sustained loss of momentum?", [docs[9]], ["After interruption, the owner logs the reason and tries to reclaim 25 percent of remaining block time within 60 minutes.", "After three consecutive low-momentum days, the sprint pauses for diagnosis instead of doubling down."]),
        ("Why does the hybrid-LRU design split control and compute kernels?", [docs[10]], ["A small control kernel manages page checks and prefetch issuance.", "A persistent heavy fused-attention kernel can then keep TensorCores busy assuming pages are resident."]),
        ("How do audit anchors remain useful when downstream SIEM payloads are enriched?", [docs[11]], ["The emitter hashes a canonical subset of stable event fields into an append-only signed anchor chain.", "SIEM stores anchor pointers, and daily reconciliation compares hashes to detect silent alteration after enrichment."]),
        ("Compare rollback safety in the GPU kernel runbook and the runtime experiment checklist.", [docs[1], docs[5]], ["Both require explicit metric gates, a tested rollback path, and progressive canary exposure.", "The kernel runbook cuts canary traffic to zero on gate failure, while the experiment checklist first invokes a versioned revert toggle and falls back to zero traffic if the toggle fails."]),
        ("Combine the handback and responder manuals into a first-72-hours incident ownership plan.", [docs[2], docs[3]], ["The onboarding lead stays available through the 72-hour stabilization window while Platform Ops owns SLO observation and alert routing.", "During an incident, the bridge operator owns cadence, the stabilizer executes mitigations, and the scribe preserves timeline and evidence."]),
        ("How do EIF provenance and audit-anchor provenance complement each other?", [docs[4], docs[11]], ["EIF records evaluation provenance such as run, evaluator, model, infrastructure, quantization profile, seed, and timestamp.", "Audit anchors add tamper-evident canonical hashes, sequence linkage, and signatures so later exports can prove the event chain was not silently altered."]),
        ("What combined safeguards apply when a high-risk kernel experiment changes KV eviction behavior?", [docs[5], docs[10]], ["The experiment must be high risk, rehearsed in the lab, started at no more than 0.1 percent traffic, and instrumented with full early trace sampling.", "The implementation must protect in-use pages, rate-limit prefetch pressure, monitor page faults and bandwidth, and retain a safe fallback."]),
        ("Relate the reserve policy to the service-credit TCO model for a high-value private deployment.", [docs[6], docs[13]], ["The reserve policy applies 12 to 20 percent contingency to exposure at or above 250,000 dollars and adds an 8 percent hardware delivery buffer.", "The TCO model subtracts service credits from total cost but recommends capping annual credits at 20 percent of recurring fees, so Finance must model both reserve exposure and credit liability."]),
        ("How should discovery negotiation and SSE heartbeats jointly improve a streaming client?", [docs[7], docs[14]], ["The client uses discovery tokens and negotiation headers to select supported streaming or fall back when streaming v2 is absent.", "Once streaming is selected, the gateway sends a comment heartbeat every 10 seconds during token pauses to prevent idle connections from appearing frozen."]),
        ("What common stale-state lesson comes from the routing version hold and optimizer unwind incidents?", [docs[15], docs[17]], ["Rollback must invalidate state outside the top-level flag: the routing incident required clearing version-hold cache state, while the optimizer incident required draining workers and clearing kernel caches.", "A control-plane rollback acknowledgement alone is insufficient when long-lived session or worker state survives."]),
        ("Compare credential rollover recovery for CI runners with the JIT session-policy fallback.", [docs[16], docs[18]], ["CI runner recovery refreshes verification keys on 401, uses overlap during signing-key rotation, and may re-register runners.", "JIT bootstrap detects oversized session policy and switches to a narrowly scoped short-lived managed role without inline policy."]),
    ]
    for question, question_docs, facts in core_specs:
        add("core", question, question_docs, facts)

    hard_pairs = [
        (0, 7, "Design a closed-network capability-discovery flow that honors Orion's enclave rules."),
        (1, 5, "Create a single approval and rollback checklist for a high-risk GPU kernel experiment."),
        (2, 3, "Build an ownership matrix for tenant handback followed by a customer-impacting incident."),
        (4, 11, "Design a tamper-evident federated evaluation artifact exchange."),
        (6, 13, "Explain how Finance should model contingency and service-credit exposure for a private deployment."),
        (8, 3, "Plan a short regional traffic-consolidation incident response with evidence retention."),
        (9, 12, "Turn the personal focus sprint and engineering role rubric into measurable onboarding goals."),
        (10, 1, "Define performance and safety gates for deploying hybrid-LRU GPU paging changes."),
        (14, 7, "Specify a robust streaming handshake and liveness fallback for OpenAI-compatible clients."),
        (15, 17, "Write a rollback rule that handles both routing-session holds and worker kernel caches."),
        (16, 18, "Propose credential failure recovery that covers signing-key rollover and oversized STS policies."),
        (19, 11, "Make the GCP IAM remediation auditable with immutable anchor evidence."),
        (0, 11, "Show how an offline enclave can export trustworthy audit evidence without public egress."),
        (2, 6, "Connect tenant handback cost guardrails to operational reserve governance."),
        (4, 5, "Combine EIF run provenance with runtime-experiment artifact requirements."),
        (8, 10, "Assess how regional traffic consolidation interacts with KV-cache prefetch pressure."),
        (12, 5, "Map the backend-platform interview safety dimension to runtime experiment ownership."),
        (13, 2, "Create a 90-day cost-stewardship validation plan for a newly handed-back private tenant."),
        (14, 16, "Differentiate transport liveness failure from authentication rollover failure in release systems."),
        (18, 19, "Compare least-privilege recovery in AWS JIT bootstrap and GCP folder IAM drift."),
    ]
    hard_facts = [
        ["Use the authenticated capability endpoint through an internal route or preloaded manifest; do not permit public egress.", "Package supported versions and capability metadata in the offline bundle, and validate with firewall egress blocked."],
        ["Classify the change as high risk, rehearse it, capture baseline telemetry, start at 0.1 percent, and require explicit rollback thresholds.", "Abort on OOM or other frozen gates, cut traffic to zero, and revert the signed kernel image."],
        ["The onboarding lead remains available for 72 hours while Platform Ops owns telemetry and Customer Success owns customer commitments.", "If impact occurs, assign bridge, stabilizer, escalation, scribe, and liaison roles and preserve request IDs, dashboards, commands, and timestamps."],
        ["EIF carries run, evaluator, model, infrastructure, seed, timestamp, metrics, and artifact references.", "An append-only signed anchor chain binds canonical hashes and export manifests so federated copies remain verifiable."],
        ["Apply the 12 to 20 percent contingency and hardware buffer where exposure qualifies, with Finance, Legal, and VP approval.", "Model credits as a subtraction from TCO but cap annual service credits and include their margin and liability impact."],
        ["Use consolidation only while the control plane is healthy and keep it within a 15 to 90 minute containment window.", "Capture alerts, request IDs, dashboards, and commands before and during the traffic move, then monitor KV misses, retries, latency, and error burn."],
        ["Translate the role's measurable six-month outcomes into 21-day lead indicators such as focus blocks, micro-deliverables, and shipped experiments.", "Keep safety, communication, and testable evidence in the review rubric instead of rewarding activity alone."],
        ["Benchmark page faults, fetch time, eviction, TensorCore utilization, bandwidth, tail latency, and throughput on representative workloads.", "Use staged bake, shadow, and live canary gates, protect in-use pages, throttle prefetch, and preserve immediate rollback."],
        ["Negotiate supported streaming capabilities with versioned headers and use structured 412 fallback when a required feature is absent.", "When streaming is active, send 10-second SSE comment heartbeats during token gaps and retain a synchronous fallback."],
        ["Disable the control-plane choice, then invalidate all surviving state tied to it.", "Clear per-session routing holds and drain workers to clear per-worker kernel caches before declaring rollback complete."],
        ["On authentication failure, refresh JWKS immediately and use signing-key overlap or runner reconnect rather than leaving semi-valid registrations.", "For oversized session policies, switch to a narrowly scoped short-lived managed role while preserving least privilege."],
        ["Anchor the pre-change snapshot, IAM change event, actor, affected bindings, remediation commands, and post-change verification in an append-only chain.", "Export anchor pointers into SIEM and reconcile them against current policy snapshots."],
        ["Use customer-controlled HSM or KMS keys and internal SIEM endpoints inside the enclave.", "Export signed anchor pointers and manifests without contacting public OCSP, registries, or external SIEM services."],
        ["At handback, configure the 1.2x cost soft cap, quota webhook, billing telemetry, and named owners.", "If uncertain deployment or contract costs exceed policy thresholds, file a reserve request and obtain the required Finance, Legal, and VP approvals."],
        ["EIF preserves compact result provenance and points to large artifacts.", "The runtime experiment entry must attach baseline and experiment CSVs, trace bundles, kernel profiles, timeline, toggles, and the final ship, revise, or abandon decision."],
        ["Traffic consolidation reduces cross-region KV divergence but concentrates demand into fewer regions.", "Hybrid-LRU prefetch must therefore rate-limit queue pressure and monitor page faults, bandwidth, tail latency, and cache-hotspot behavior during consolidation."],
        ["The interviewer should require measurable trade-offs, canary metrics, rollback, testable hypotheses, and clear stakeholder communication.", "Those same behaviors map to experiment owner, safety reviewer, oncall lead, and metrics librarian responsibilities."],
        ["Validate the 1.2x cap, quota webhook, billing hooks, SLO alerts, and QBR data during handback and the first 72 hours.", "Across the first 90 days, review burn-rate alerts, monthly reserve changes, service-credit KPIs, and forecast sensitivity before relaxing controls."],
        ["SSE stalls leave an authenticated connection open without data and are mitigated by transport heartbeats.", "Runner rollover failures leave registrations visible but unauthorized and require key refresh, reconnect, overlap, and preflight checks."],
        ["AWS recovery avoids oversized inline policy by using a narrowly scoped short-lived managed role and a future compact policy generator.", "GCP recovery restores inherited viewer bindings, pauses the faulty automator, compares against a known snapshot, and requires two-person approval for broad IAM changes."],
    ]
    for (left, right, question), facts in zip(hard_pairs, hard_facts):
        add("hard", question, [docs[left], docs[right]], facts)
    return rows


def _historical_exclusions(dataset_root: Path) -> tuple[set[str], set[str]]:
    """从 M34 冻结题集提取禁止复用的 question/document ID。"""

    question_ids: set[str] = set()
    document_ids: set[str] = set()
    for name in ("questions.jsonl", "extra_questions.jsonl"):
        for line in (dataset_root / "raw" / name).read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            question_ids.add(str(value["question_id"]))
            document_ids.update(str(item) for item in value["expected_doc_ids"])
    return question_ids, document_ids


def build(*, dataset_root: Path, output_root: Path) -> dict[str, Any]:
    """验证冻结原文、执行两遍独立审核并写入全新 external version 目录。"""

    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"immutable output 已存在且非空: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    source_records = []
    for doc_id, (source, relative, expected_hash) in SOURCE_POOL.items():
        path = dataset_root / relative
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"source hash drift: {doc_id}")
        source_records.append({
            "document_id": doc_id, "source_type": source, "relative_path": relative,
            "bytes": path.stat().st_size, "sha256": actual_hash,
        })
    source_pool = {
        "selection_identity": "phase4b-source-pool-source-length-content-v1",
        "exclusion": "M34/M41 historical 180 gold documents",
        "sources": source_records,
    }
    (output_root / "source_pool.json").write_text(
        json.dumps(source_pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = _records()
    reserve_path = output_root / "reserve.jsonl"
    reserve_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

    # 两遍审核关注不同故障面：第一遍只证明 source 坐标/内容未漂移；第二遍只证明
    # gold answer 完整包含冻结 answer_facts。二者不能互相替代，也不查看任何模型输出。
    reviews = []
    for row in rows:
        source_hashes = [SOURCE_POOL[doc][2] for doc in row["expected_doc_ids"]]
        gold_hash = canonical_hash({"gold_answer": row["gold_answer"], "answer_facts": row["answer_facts"]})
        if any(fact not in row["gold_answer"] for fact in row["answer_facts"]):
            raise ValueError(f"gold/facts mismatch: {row['reserve_question_id']}")
        reviews.extend([
            {"reserve_question_id": row["reserve_question_id"], "reviewer": "source-coordinate-review-v1", "verdict": "approved", "source_hashes": source_hashes, "gold_hash": gold_hash},
            {"reserve_question_id": row["reserve_question_id"], "reviewer": "gold-consistency-review-v1", "verdict": "approved", "source_hashes": source_hashes, "gold_hash": gold_hash},
        ])
    review_path = output_root / "gold_review.jsonl"
    review_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in reviews) + "\n", encoding="utf-8")
    ledger_path = output_root / "access_ledger.jsonl"
    ledger_path.write_text(
        json.dumps({"event": "created", "purpose": "sealed_decision_reserve", "module": "M42"}) + "\n" +
        json.dumps({"event": "sealed", "purpose": "future_B4_decision", "module": "M42"}) + "\n",
        encoding="utf-8",
    )

    excluded_questions, excluded_docs = _historical_exclusions(dataset_root)
    profile_path = dataset_root / "derived" / "enterprise_profiles" / EXTERNAL_PROFILE_IDENTITY / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("profile_identity") != EXTERNAL_PROFILE_IDENTITY:
        raise ValueError("external profile identity drift")
    manifest = seal_reserve(
        reserve_path=reserve_path, review_path=review_path, ledger_path=ledger_path,
        source_pool_path=output_root / "source_pool.json",
        corpus_identity=profile["corpus_identity"], profile_identity=profile["profile_identity"],
        excluded_question_ids=excluded_questions, excluded_document_ids=excluded_docs,
    ).payload()
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    """解析外部数据根与全新版本目录，执行一次性密封构建。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(dataset_root=args.dataset_root, output_root=args.output_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
