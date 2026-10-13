"""Select the single protocol correction while preserving the complete original round."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_behavior_acceptance import evaluate_answer, evaluate_runs, load_contract


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def save(name: str, data: object) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ident = "B10_APPROVAL_NOOR"
    contract = load_contract()
    original = read("actual_runs_reviewed.json")["runs"]
    initial_raw = read("actual_runs_unreviewed.json")["runs"]
    original_b10 = next(r for r in initial_raw if r["scenario_id"] == ident)
    if next(r for r in original if r["scenario_id"] == ident)["answer_sha256"] != original_b10["answer_sha256"]:
        raise RuntimeError("Integration already applied or original round changed")
    protocol = read("cold_protocol_issue_B10.json")
    if protocol["status"] != "RUBRIC_EXPOSURE_CONFIRMED":
        raise RuntimeError("A documented protocol defect is required; no selection of preferred answers")
    retest = read("retest_b10_actual_runs_unreviewed.json")["runs"]
    if len(retest) != 1 or retest[0]["scenario_id"] != ident:
        raise RuntimeError("Only B10 may be replaced")
    replacement = copy.deepcopy(retest[0])
    audit = read("retest_b10_capture_audit.json")
    if audit["status"] != "PASS" or audit["captured_responses"] != 1 or audit["runs_sha256"] != sha((OUT / "retest_b10_actual_runs_unreviewed.json").read_bytes()) or audit["transcripts_sha256"] != sha((OUT / "retest_b10_actual_transcripts.json").read_bytes()):
        raise RuntimeError("Current exact retest capture audit required")
    frozen = read("review_b10_retest_input.json")
    if frozen["runs"] != retest:
        raise RuntimeError("Retest changed after reviewer input was frozen")
    reviews = read("review_b10_retest.json")
    if reviews["reviewer"] != "/root/review_b10_retest" or reviews["independent"] is not True or reviews["input_sha256"] != sha((OUT / "review_b10_retest_input.json").read_bytes()) or reviews["contract_sha256"] != sha((ROOT / "standards/behavior_acceptance.json").read_bytes()):
        raise RuntimeError("Retest independent review binding failed")
    review = reviews["reviews"][ident]
    scenario = next(s for s in contract["scenarios"] if s["id"] == ident)
    required = {c["id"] for c in contract["common_criteria"] + scenario["criteria"]}
    if review["answer_sha256"] != replacement["answer_sha256"] or review["visible_messages_sha256"] != replacement["execution"]["visible_messages_sha256"] or {c["id"] for c in review["criteria"]} != required or len(review["criteria"]) != len(required):
        raise RuntimeError("Retest judgment does not cover the exact answer and messages")
    if replacement["execution"]["context_id"] in {r["execution"]["context_id"] for r in initial_raw}:
        raise RuntimeError("Protocol correction must use a new context")
    capture = read("retest_b10_actual_transcripts.json")[ident]
    invocation_text = "\n".join(call["input"] for call in capture["tool_calls"])
    if "behavior_acceptance" in invocation_text or "review_" in invocation_text:
        raise RuntimeError("Retest again references test criteria/review artifacts")
    session = Path(r"C:\Users\CSS\.codex\sessions\2026\10\05") / capture["session_file"]
    returned = [json.loads(line)["payload"] for line in session.read_text(encoding="utf-8").splitlines() if line.strip() and json.loads(line).get("type") == "response_item" and json.loads(line)["payload"].get("type") in {"custom_tool_call_output", "function_call_output"}]
    returned_text = json.dumps(returned, ensure_ascii=False)
    if "APPROVAL_BEFORE_SAVE" in returned_text or "NOOR_VERIFICATION" in returned_text:
        raise RuntimeError("Retest exposes the B10 rubric in a recorded tool return")
    files = {}
    for r in initial_raw + retest:
        for name, digest in r["project"]["files"].items():
            if name in files and files[name] != digest:
                raise RuntimeError("Conflicting source versions between captures: " + name)
            files[name] = digest
    for name, digest in files.items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise RuntimeError("Project changed: " + name)
    for name in ("actual_runs_reviewed.json", "behavior_result.json", "semantic_summary.json", "text_checker_summary.json", "CANDIDATE_STATE.json", "independent_reviews.json"):
        before = OUT / ("initial_" + name)
        content = (OUT / name).read_bytes()
        if before.exists() and before.read_bytes() != content:
            raise RuntimeError("Historical baseline preservation failed")
        if not before.exists():
            before.write_bytes(content)
    replacement["review"] = review
    check = audit["checks"][0]
    replacement["execution"]["tools"] = sorted(set(check["top_level_tool_names"] + check["nested_tool_names_referenced"]))
    selected = [replacement if r["scenario_id"] == ident else r for r in original]
    result = evaluate_runs(selected, contract, root=ROOT, verify_project=False)
    result["live_project_binding"] = {"status": "PASS", "checked_current_files": len(files), "capture_audits": {name: sha((OUT / name).read_bytes()) for name in ("capture_audit.json", "retest_b10_capture_audit.json")}, "method": "All distinct source-file digests checked against current bytes before evaluating unchanged fixed contract."}
    semantic_items = []
    text_items = []
    for run in selected:
        s = next(s for s in contract["scenarios"] if s["id"] == run["scenario_id"])
        judgments = run["review"]["criteria"]
        status = "FAIL" if any(c["status"] == "FAIL" for c in judgments) else "NOT_RUN" if any(c["status"] != "PASS" for c in judgments) else "PASS"
        semantic_items.append({"scenario_id": run["scenario_id"], "status": status, "failed_criteria": [c["id"] for c in judgments if c["status"] == "FAIL"], "critical": s["critical"]})
        text_items.append({"scenario_id": run["scenario_id"], "issues": evaluate_answer(run["actual_answer"], s)})
    counts = lambda items: {state: sum(item["status"] == state for item in items) for state in ("PASS", "FAIL", "NOT_RUN")}
    state = read("CANDIDATE_STATE.json")
    state.update({"status": result["status"], "recorded_at": datetime.now(timezone.utc).isoformat(), "actual_completed_responses": 18, "selected_response_count": 17, "distinct_response_contexts": 18, "selected_distinct_response_contexts": 17, "independently_reviewed_responses": 18, "combined_acceptance_counts": counts(result["results"]), "semantic_counts": counts(semantic_items), "text_checker_only_counts": {s: sum(("FAIL" if i["issues"] else "PASS") == s for i in text_items) for s in ("PASS", "FAIL", "NOT_RUN")}, "critical_complete": result["critical_complete"], "conversation_acceptance_complete": result["conversation_acceptance_complete"], "protocol_correction": {"scenario_id": ident, "excluded_original_context": original_b10["execution"]["context_id"], "reason": "Respondent accessed its own rubric; preserved, not valid cold retrieval.", "original_cold_status": "NOT_RUN", "replacement_context": replacement["execution"]["context_id"], "replacement_rubric_exposure": "No observed read of rubric/review files or B10 criterion text; the contract filename appears in retrieved workflow prose.", "answer_selection_policy": "Only the documented protocol-invalid response is replaced; no other failed answer is rerun or selected by result."}, "reviewed_runs_sha256": sha((json.dumps({"runs": selected}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")), "review_files": {**state["review_files"], "review_b10_retest.json": sha((OUT / "review_b10_retest.json").read_bytes())}, "frozen_review_inputs": {**state["frozen_review_inputs"], "review_b10_retest_input.json": sha((OUT / "review_b10_retest_input.json").read_bytes())}})
    save("actual_runs_reviewed.json", {"runs": selected})
    state["reviewed_runs_sha256"] = sha((OUT / "actual_runs_reviewed.json").read_bytes())
    save("behavior_result.json", result)
    save("semantic_summary.json", {"scope": "Selected independent judgments; original rubric-exposed B10 preserved separately.", "counts": state["semantic_counts"], "results": semantic_items})
    save("text_checker_summary.json", {"scope": "Raw final text only; absence of detected issues is not semantic acceptance.", "counts": state["text_checker_only_counts"], "results": text_items})
    save("independent_reviews.json", {"reviews": {r["scenario_id"]: r["review"] for r in selected}, "review_files": state["review_files"], "contract_sha256": state["contract_sha256"], "scope": "All captured assistant messages including commentary; original B10 remains in initial_independent_reviews.json"})
    save("CANDIDATE_STATE.json", state)
    save("retest_b10_selection.json", {"reason": protocol, "selected_context_id": replacement["execution"]["context_id"], "selected_answer_sha256": replacement["answer_sha256"], "selected_visible_messages_sha256": replacement["execution"]["visible_messages_sha256"], "capture_audit_sha256": sha((OUT / "retest_b10_capture_audit.json").read_bytes()), "review_sha256": sha((OUT / "review_b10_retest.json").read_bytes()), "original_preserved": True})
    print(json.dumps({key: state[key] for key in ("status", "selected_response_count", "actual_completed_responses", "combined_acceptance_counts", "critical_complete")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
