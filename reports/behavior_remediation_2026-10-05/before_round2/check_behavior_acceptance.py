"""Check captured actual answers and their independent judgments.

Heuristics reject known surface failures; they do not assess all meaning.
Synthetic unit fixtures, missing captures, and reading instructions cannot PASS.
Output contains codes only, never the supplied answer or sensitive excerpts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
CONTRACT = ROOT / "standards/behavior_acceptance.json"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def answer_sha256(answer: str) -> str:
    """Hash the exact captured answer, without normalizing its whitespace."""
    return digest_bytes(answer.encode("utf-8"))


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return digest_bytes(encoded.encode("utf-8"))


def load_contract(path: Path = CONTRACT) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_project_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or not relative or ".." in path.parts:
        raise ValueError("invalid project file path")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("project file escapes root")
    return resolved


def capture_project(root: Path = ROOT, *, head: str = "unavailable", extra_files: list[str] | None = None) -> dict:
    """Capture governing files plus source files actually consulted by the runner."""
    contract = load_contract(root / "standards/behavior_acceptance.json")
    names = sorted(set(contract["required_project_files"] + (extra_files or [])))
    files = {name: digest_bytes(safe_project_path(root, name).read_bytes()) for name in names}
    return {"head": head, "files": files, "snapshot_sha256": canonical_sha256(files)}


def normalized(value: str) -> str:
    value = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", value)
    return value.translate(str.maketrans("أإآى", "اااي"))


def evaluate_answer(answer: str, scenario: dict) -> list[str]:
    """Evaluate actual text. An empty issue list is not semantic acceptance."""
    if not isinstance(answer, str) or not answer.strip():
        return ["EMPTY_ANSWER"]
    text = answer.strip()
    surface = normalized(text)
    opening = re.sub(r"^[\s\"'«»*_]+", "", surface)
    issues: list[str] = []
    if re.match(r"^(?:حسنا[،,:.! ]|بالطبع|بالتاكيد|دعني|سا(?:راجع|فحص|بدا|قوم|وضح|شرح|ساعد)|سوف |لفهم طلبك|بناء علي طلبك)", opening):
        issues.append("UNNECESSARY_INTRODUCTION")
    if re.match(r"^(?:طلبك هو|انت (?:تريد|تطلب|تسال)|تسال عن|سؤالك (?:هو|عن)|افهم انك|بما انك طلبت)", opening):
        issues.append("RESTATES_REQUEST")
    prompt_tokens = normalized(scenario.get("prompt", "")).split()
    if len(prompt_tokens) >= 8 and opening.startswith(" ".join(prompt_tokens[:8])):
        issues.append("RESTATES_REQUEST")
    if re.search(r"(?:AGENTS\.md|workflow\.md|\bDEC-\d+|\bWORK-\d+|\bREF-[A-Z]|\bGate\b|\bRouting\b|\bSource Registry\b|check_\w+\.py|(?:catalog|standards|tools|context)/|س-\d+-ا\d+)", text, re.IGNORECASE):
        issues.append("INTERNAL_MECHANISMS")
    if len(text.split()) > scenario.get("max_words", 200):
        issues.append("EXCESS_DETAIL")
    shape = scenario.get("answer_shape")
    if shape in {"simple", "knowledge", "question_only", "clarification"}:
        if re.search(r"^\s*#{1,6}\s|(?:الان|الناتج|بعدها)\s*[:：]|→|←|⇒", surface, re.MULTILINE):
            issues.append("FORCED_TEMPLATE")
    if shape == "simple" and len(re.findall(r"^\s*(?:[-*•]|\d+[.)])\s", text, re.MULTILINE)) > 1:
        issues.append("UNNEEDED_DECOMPOSITION")
    if shape == "question_only":
        single_question = (re.match(r"^(?:هل|ما|ماذا|متي|كم|من|اي|ا(?:حيل|بلغ|تم))\b", opening)
                           and text[-1:] in {"؟", "?"}
                           and len(re.findall(r"[؟?]", text)) == 1
                           and "\n" not in text
                           and not re.search(r"[.!؛;]|(?:يجب|ينبغي|تحقق من|تاكد من|المادة|اذا لم|ان لم)", surface))
        if not single_question:
            issues.append("QUESTION_ONLY_REQUIRED")
    if shape == "urgent" and (opening.startswith("هل احيل") or opening.startswith("هل نفذت")):
        issues.append("ADMIN_QUESTION_BEFORE_PROTECTION")
    for index, alternatives in enumerate(scenario.get("required_any", []), 1):
        if not any(normalized(item) in surface for item in alternatives):
            issues.append(f"MISSING_DECISIVE_CONSTRAINT_{index}")
    return list(dict.fromkeys(issues))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value: Any) -> bool:
    if not _nonempty(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def evaluate_run(run: dict, contract: dict | None = None, *, root: Path = ROOT, verify_project: bool = True) -> dict:
    """Validate capture provenance declarations, live binding, and rubric judgments.

    Declared context/reviewer identities remain evidence references, not authenticated identities.
    """
    contract = contract or load_contract()
    scenario_id = run.get("scenario_id", "UNKNOWN")
    scenario = next((item for item in contract["scenarios"] if item["id"] == scenario_id), None)
    result = {"scenario_id": scenario_id, "status": "NOT_RUN", "issues": []}
    if scenario is None:
        result.update(status="FAIL", issues=["UNKNOWN_SCENARIO"])
        return result
    execution = run.get("execution")
    if not isinstance(execution, dict) or execution.get("status") == "NOT_RUN":
        result["issues"] = ["ACTUAL_CONVERSATION_NOT_RUN"]
        return result
    if execution.get("kind") != "actual_conversation" or execution.get("status") != "RUN":
        result["issues"] = ["ACTUAL_CONVERSATION_REQUIRED"]
        return result
    issues = result["issues"]
    if run.get("schema_version") != contract["schema_version"]:
        issues.append("RUN_SCHEMA_VERSION")
    if run.get("scenario_text") != scenario["prompt"]:
        issues.append("SCENARIO_TEXT_MISMATCH")
    answer = run.get("actual_answer", "")
    issues.extend(evaluate_answer(answer, scenario))
    current_answer_hash = answer_sha256(answer) if isinstance(answer, str) else ""
    if run.get("answer_sha256") != current_answer_hash:
        issues.append("ANSWER_CHANGED_AFTER_CAPTURE")
    for key in ("context_id", "transcript_ref"):
        if not _nonempty(execution.get(key)):
            issues.append("MISSING_CAPTURE_" + key.upper())
    if not _timestamp(execution.get("captured_at")):
        issues.append("MISSING_CAPTURE_TIME")
    model = execution.get("model")
    if not isinstance(model, dict) or not all(_nonempty(model.get(key)) for key in ("name", "version")):
        issues.append("MISSING_MODEL_METADATA")
    if not isinstance(execution.get("tools"), list) or not all(_nonempty(item) for item in execution["tools"]):
        issues.append("MISSING_TOOL_METADATA")
    if scenario.get("fresh_required") and (execution.get("isolated") is not True or execution.get("prior_messages_count") != 0):
        issues.append("INDEPENDENT_FRESH_CONTEXT_REQUIRED")
    project = run.get("project", {})
    files = project.get("files") if isinstance(project, dict) else None
    if not isinstance(files, dict) or not files:
        issues.append("PROJECT_VERSION_REQUIRED")
    else:
        if not _nonempty(project.get("head")) or project.get("snapshot_sha256") != canonical_sha256(files):
            issues.append("PROJECT_SNAPSHOT_MISMATCH")
        for name in contract["required_project_files"]:
            if name not in files:
                issues.append("MISSING_PROJECT_BINDING:" + name)
        for name, checksum in files.items():
            if not isinstance(name, str) or not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                issues.append("INVALID_PROJECT_BINDING")
                continue
            try:
                path = safe_project_path(root, name)
                if verify_project and (not path.is_file() or digest_bytes(path.read_bytes()) != checksum):
                    issues.append("PROJECT_CHANGED:" + name)
            except (ValueError, OSError):
                issues.append("INVALID_PROJECT_PATH")
    review = run.get("review")
    review_missing = not isinstance(review, dict)
    if review_missing:
        review = {}
        issues.append("INDEPENDENT_REVIEW_NOT_RUN")
    if review.get("answer_sha256") != current_answer_hash:
        issues.append("REVIEW_NOT_BOUND_TO_ANSWER")
    if review.get("independent") is not True or not _nonempty(review.get("reviewer")) or not _timestamp(review.get("reviewed_at")):
        issues.append("INDEPENDENT_REVIEW_REQUIRED")
    judgments = review.get("criteria", [])
    if not isinstance(judgments, list):
        judgments = []
    ids = [item.get("id") for item in judgments if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        issues.append("DUPLICATE_JUDGMENT")
    required = contract["common_criteria"] + scenario["criteria"]
    expected_ids = {item["id"] for item in required}
    if any(ident not in expected_ids for ident in ids):
        issues.append("UNKNOWN_JUDGMENT")
    for criterion in required:
        judgment = next((item for item in judgments if isinstance(item, dict) and item.get("id") == criterion["id"]), {})
        if judgment.get("status") != "PASS":
            issues.append("RUBRIC_" + ("FAIL:" if judgment.get("status") == "FAIL" else "NOT_RUN:") + criterion["id"])
        if not _nonempty(judgment.get("reason")):
            issues.append("RUBRIC_REASON_REQUIRED:" + criterion["id"])
    result["issues"] = list(dict.fromkeys(issues))
    result["status"] = "FAIL" if issues else "PASS"
    if review_missing and all(code.startswith(("INDEPENDENT_REVIEW", "REVIEW_NOT_BOUND", "RUBRIC_")) for code in issues):
        result["status"] = "NOT_RUN"
    return result


def evaluate_runs(runs: list[dict], contract: dict | None = None, *, root: Path = ROOT, verify_project: bool = True) -> dict:
    contract = contract or load_contract()
    results = []
    contexts: dict[str, str] = {}
    known_ids = {item["id"] for item in contract["scenarios"]}
    for scenario in contract["scenarios"]:
        matches = [item for item in runs if item.get("scenario_id") == scenario["id"]]
        if not matches:
            results.append({"scenario_id": scenario["id"], "status": "NOT_RUN", "issues": ["ACTUAL_CONVERSATION_NOT_RUN"]})
            continue
        if len(matches) != 1:
            results.append({"scenario_id": scenario["id"], "status": "FAIL", "issues": ["DUPLICATE_SCENARIO_RUN"]})
            continue
        result = evaluate_run(matches[0], contract, root=root, verify_project=verify_project)
        execution = matches[0].get("execution", {})
        if scenario.get("fresh_required") and result["status"] == "PASS":
            context_id = execution.get("context_id")
            if context_id in contexts:
                result["status"] = "FAIL"
                result["issues"].append("FRESH_CONTEXT_REUSED")
            contexts[context_id] = scenario["id"]
        results.append(result)
    for run in runs:
        if run.get("scenario_id") not in known_ids:
            results.append({"scenario_id": run.get("scenario_id", "UNKNOWN"), "status": "FAIL", "issues": ["UNKNOWN_SCENARIO"]})
    statuses = [item["status"] for item in results]
    status = "FAIL" if "FAIL" in statuses else "NOT_RUN" if "NOT_RUN" in statuses else "PASS"
    critical_ids = {item["id"] for item in contract["scenarios"] if item.get("critical")}
    critical_complete = all(item["status"] == "PASS" for item in results if item["scenario_id"] in critical_ids)
    return {"checker_version": VERSION, "contract_version": contract["version"], "status": status,
            "critical_complete": critical_complete, "conversation_acceptance_complete": status == "PASS", "results": results,
            "limits": contract["limits"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, help="JSON list/object with runs, or JSONL; omit to report NOT_RUN")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    contract = load_contract(root / "standards/behavior_acceptance.json")
    runs: list[dict] = []
    if args.runs:
        raw = args.runs.read_text(encoding="utf-8-sig")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
        runs = parsed.get("runs", []) if isinstance(parsed, dict) else parsed
        if not isinstance(runs, list) or not all(isinstance(item, dict) for item in runs):
            raise ValueError("run input must contain a list of run objects")
    result = evaluate_runs(runs, contract, root=root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1 if result["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
