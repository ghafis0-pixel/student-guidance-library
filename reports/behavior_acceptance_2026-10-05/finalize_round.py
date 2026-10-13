"""Bind independent judgments to unchanged captured answers and evaluate the fixed contract."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_behavior_acceptance import canonical_sha256, evaluate_answer, evaluate_runs, load_contract


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def save(name: str, data: object) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    contract = load_contract()
    before = read("project_before.json")
    transcripts = read("actual_transcripts.json")
    original_runs = read("actual_runs_unreviewed.json")["runs"]
    required = {s["id"] for s in contract["scenarios"]}
    if {r["scenario_id"] for r in original_runs} != required:
        raise RuntimeError("All seventeen response captures are required before finalization")
    audit = read("capture_audit.json")
    if audit["status"] != "PASS" or audit["captured_responses"] != len(required):
        raise RuntimeError("Fresh full capture audit required")
    if audit["runs_sha256"] != sha((OUT / "actual_runs_unreviewed.json").read_bytes()) or audit["transcripts_sha256"] != sha((OUT / "actual_transcripts.json").read_bytes()):
        raise RuntimeError("Capture audit does not bind current artifacts")
    review_map = {}
    review_files = {}
    frozen_inputs = {}
    contract_hash = sha((ROOT / "standards/behavior_acceptance.json").read_bytes())
    for group in ("privacy", "sources", "daily"):
        review_name = "review_" + group + ".json"
        input_name = "review_" + group + "_input.json"
        review = read(review_name)
        frozen = read(input_name)
        if review.get("contract_sha256") != contract_hash or review.get("input_sha256") != sha((OUT / input_name).read_bytes()):
            raise RuntimeError("Independent review input binding failed: " + group)
        if review.get("independent") is not True or review.get("reviewer") != "/root/review_" + group:
            raise RuntimeError("Unexpected independent review actor: " + group)
        expected_ids = {r["scenario_id"] for r in frozen["runs"]}
        if set(review["reviews"]) != expected_ids or set(review_map) & expected_ids:
            raise RuntimeError("Review scope missing or duplicated")
        for run in frozen["runs"]:
            actual = next(r for r in original_runs if r["scenario_id"] == run["scenario_id"])
            if actual["actual_answer"] != run["actual_answer"] or actual["answer_sha256"] != run["answer_sha256"] or actual["execution"]["visible_messages_sha256"] != run["execution"]["visible_messages_sha256"]:
                raise RuntimeError("Capture changed after independent review input was frozen")
        review_map.update(review["reviews"])
        review_files[review_name] = sha((OUT / review_name).read_bytes())
        frozen_inputs[input_name] = sha((OUT / input_name).read_bytes())
    if set(review_map) != required:
        raise RuntimeError("Independent reviews incomplete")
    runs = copy.deepcopy(original_runs)
    semantic_items = []
    for run in runs:
        ident = run["scenario_id"]
        review = copy.deepcopy(review_map[ident])
        if review.get("answer_sha256") != run["answer_sha256"] or review.get("visible_messages_sha256") != run["execution"]["visible_messages_sha256"]:
            raise RuntimeError("Review does not bind exact response/messages: " + ident)
        scenario = next(s for s in contract["scenarios"] if s["id"] == ident)
        criteria = contract["common_criteria"] + scenario["criteria"]
        expected_ids = {c["id"] for c in criteria}
        judged = review.get("criteria", [])
        if len(judged) != len(expected_ids) or {c["id"] for c in judged} != expected_ids:
            raise RuntimeError("Criterion coverage mismatch: " + ident)
        if review.get("reviewer") == transcripts[ident]["agent_path"]:
            raise RuntimeError("Respondent cannot be its own reviewer")
        run["review"] = review
        tool_audit = next(c for c in audit["checks"] if c["scenario_id"] == ident)
        run["execution"]["tools"] = sorted(set(tool_audit["top_level_tool_names"] + tool_audit["nested_tool_names_referenced"]))
        status = "FAIL" if any(c["status"] == "FAIL" for c in judged) else "NOT_RUN" if any(c["status"] != "PASS" for c in judged) else "PASS"
        semantic_items.append({"scenario_id": ident, "status": status, "failed_criteria": [c["id"] for c in judged if c["status"] == "FAIL"], "critical": scenario["critical"]})
    save("actual_runs_reviewed.json", {"runs": runs})
    # Live version binding is verified by the current capture audit, including
    # all required and consulted source files; avoid hashing each PDF 17 times.
    result = evaluate_runs(runs, contract, root=ROOT, verify_project=False)
    result["live_project_binding"] = {"status": "PASS", "evidence": "capture_audit.json", "sha256": sha((OUT / "capture_audit.json").read_bytes()), "method": "Every run file fingerprint compared to current bytes by audit_capture.py before evaluation; evaluator receives verify_project=False only after this asserted check."}
    save("behavior_result.json", result)
    combined_counts = Counter(r["status"] for r in result["results"])
    text_items = [{"scenario_id": r["scenario_id"], "issues": evaluate_answer(r["actual_answer"], next(s for s in contract["scenarios"] if s["id"] == r["scenario_id"]))} for r in runs]
    text_counts = Counter("FAIL" if item["issues"] else "PASS" for item in text_items)
    semantic_counts = Counter(r["status"] for r in semantic_items)
    semantic = {"scope": "Independent rubric judgments covering all captured assistant messages; distinct from unchanged raw-text checker", "counts": {s: semantic_counts[s] for s in ("PASS", "FAIL", "NOT_RUN")}, "results": semantic_items}
    save("semantic_summary.json", semantic)
    save("text_checker_summary.json", {"scope": "Unchanged exact final raw text checks only; an empty issue list does not prove semantic acceptance.", "counts": {s: text_counts[s] for s in ("PASS", "FAIL", "NOT_RUN")}, "results": text_items})
    after = {name: sha((ROOT / name).read_bytes()) for name in before["files"]}
    changed = [name for name, checksum in before["files"].items() if after[name] != checksum]
    if changed:
        raise RuntimeError("Runtime project files changed during acceptance: " + repr(changed))
    unchanged = {"status": "PASS", "bound_files": len(after), "changed_bound_files": changed, "project_snapshot_sha256": canonical_sha256(after), "work_register_sha256": after["work/register.json"], "decisions_sha256": after["context/decisions.md"], "evidence": "Same source files as candidate-v2, independently verified at capture and finalization"}
    save("project_unchanged_after_round.json", unchanged)
    summary = {
        "status": result["status"], "candidate_status": "CANDIDATE", "recorded_at": datetime.now(timezone.utc).isoformat(),
        "actual_completed_responses": len(runs), "distinct_response_contexts": len({r["execution"]["context_id"] for r in runs}),
        "independently_reviewed_responses": len(review_map),
        "combined_acceptance_counts": {s: combined_counts[s] for s in ("PASS", "FAIL", "NOT_RUN")},
        "text_checker_only_counts": {s: text_counts[s] for s in ("PASS", "FAIL", "NOT_RUN")},
        "semantic_counts": semantic["counts"], "critical_complete": result["critical_complete"],
        "conversation_acceptance_complete": result["conversation_acceptance_complete"],
        "review_files": review_files, "frozen_review_inputs": frozen_inputs,
        "raw_capture_sha256": sha((OUT / "actual_runs_unreviewed.json").read_bytes()),
        "reviewed_runs_sha256": sha((OUT / "actual_runs_reviewed.json").read_bytes()),
        "transcripts_sha256": sha((OUT / "actual_transcripts.json").read_bytes()),
        "contract_sha256": contract_hash, "candidate_package_sha256": read("candidate_package_verification.json")["package_sha256"],
        "project_snapshot_sha256": before["snapshot_sha256"],
        "partial_attempts": len(read("incomplete_attempts.json")), "execution_errors": audit["execution_errors"],
        "historical_results": "9/8 and 15/2 retained in previous files; not used as acceptance of this round.",
        "operational_state": {"content_approval_ref": "DEC-014", "execution_status": "not_reported", "evidence_refs": [], "work_register_changed": False, "noor_save_performed": False},
        "limits": "This is a Codex subagent cold-context test with ambient instructions and memory, not certified equivalence to every future deployed environment. Dispatch plaintext is separately operator-recorded because local journals encrypt it. Raw memory citation metadata is retained; rendered-display equivalence was not verified. No failure is fixed by rewriting captured answers.",
    }
    save("CANDIDATE_STATE.json", summary)
    save("independent_reviews.json", {"reviews": review_map, "review_files": review_files, "contract_sha256": contract_hash, "scope": "All captured assistant messages including commentary"})
    print(json.dumps({k: summary[k] for k in ("status", "actual_completed_responses", "distinct_response_contexts", "independently_reviewed_responses", "combined_acceptance_counts", "text_checker_only_counts", "semantic_counts", "critical_complete")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
