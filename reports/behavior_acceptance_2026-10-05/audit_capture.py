"""Verify saved captures against local journals; no inference or answer editing."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SESSIONS = Path(r"C:\Users\CSS\.codex\sessions\2026\10\05")
sys.path.insert(0, str(ROOT))
from tools.check_behavior_acceptance import canonical_sha256


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def message_text(q: dict) -> str:
    return "".join(v.get("text", "") for v in q.get("content", []) if v.get("type") in {"input_text", "output_text", "text"})


def rows(path: Path) -> list[dict]:
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def main() -> None:
    runs_path = OUT / "actual_runs_unreviewed.json"
    transcript_path = OUT / "actual_transcripts.json"
    runs = json.loads(runs_path.read_text(encoding="utf-8"))["runs"]
    transcripts = json.loads(transcript_path.read_text(encoding="utf-8"))
    checks = []
    context_ids = []
    parent_cache = {}
    live_hashes = {}
    source_files = set()
    for run in runs:
        ident = run["scenario_id"]
        capture = transcripts[ident]
        journal = rows(SESSIONS / capture["session_file"])
        meta = next(r["payload"] for r in journal if r["type"] == "session_meta")
        context = next(r["payload"] for r in journal if r["type"] == "turn_context")
        spawn = meta["source"]["subagent"]["thread_spawn"]
        assert meta["id"] == capture["context_id"] == run["execution"]["context_id"], ident
        assert spawn["agent_path"] == capture["agent_path"], ident
        starts = [r for r in journal if r["type"] == "event_msg" and r["payload"].get("type") == "task_started"]
        assert len(starts) == 1 and starts[0]["payload"]["turn_id"] == capture["turn_id"], ident
        assistant = [message_text(r["payload"]) for r in journal if r["type"] == "response_item" and r["payload"].get("type") == "message" and r["payload"].get("role") == "assistant"]
        assert assistant == capture["visible_assistant_messages"], ident
        assert assistant[-1] == run["actual_answer"] == capture["final_answer"], ident
        assert sha(run["actual_answer"].encode("utf-8")) == run["answer_sha256"], ident
        assert canonical_sha256(assistant) == run["execution"]["visible_messages_sha256"], ident
        assert context["model"] == run["execution"]["model"]["name"], ident
        complete = [r for r in journal if r["type"] == "event_msg" and r["payload"].get("type") == "task_complete"]
        assert len(complete) == 1 and not complete[0]["payload"].get("error"), ident
        assert complete[0]["timestamp"] == capture["captured_at"] == run["execution"]["captured_at"], ident
        dispatch = capture["dispatch"]
        if dispatch["root_session_file"] not in parent_cache:
            parent_cache[dispatch["root_session_file"]] = rows(SESSIONS / dispatch["root_session_file"])
        record = next(r for r in parent_cache[dispatch["root_session_file"]] if r["type"] == "response_item" and r["payload"].get("call_id") == dispatch["dispatch_call_id"])
        params = json.loads(record["payload"]["arguments"])
        assert params["fork_turns"] == "none" and "/root/" + params["task_name"] == capture["agent_path"], ident
        assert sha(params["message"].encode("utf-8")) == dispatch["recorded_payload_sha256"], ident
        assert dispatch["operator_captured_actual_prompt"] == run["scenario_text"], ident
        assert sha(run["scenario_text"].encode("utf-8")) == dispatch["operator_prompt_sha256"], ident
        if not params["message"].startswith("gAAAAA"):
            assert params["message"] == run["scenario_text"], ident
        raw_calls = []
        for r in journal:
            q = r["payload"]
            if r["type"] == "response_item" and q.get("type") in {"function_call", "custom_tool_call"}:
                raw_calls.append({"name": q["name"], "call_id": q["call_id"], "type": q["type"], "input": q.get("arguments", q.get("input", "")), "timestamp": r["timestamp"]})
        assert raw_calls == capture["tool_calls"], ident
        assert canonical_sha256(raw_calls) == run["execution"]["actual_tool_calls_sha256"], ident
        top_tools = {c["name"] for c in raw_calls}
        nested_tools = {n for c in raw_calls for n in re.findall(r"tools\.([A-Za-z0-9_]+)\s*\(", c["input"])}
        for name, checksum in run["project"]["files"].items():
            if name not in live_hashes:
                live_hashes[name] = sha((ROOT / name).read_bytes())
            assert live_hashes[name] == checksum, ident + ":" + name
        assert canonical_sha256(run["project"]["files"]) == run["project"]["snapshot_sha256"], ident
        context_ids.append(meta["id"])
        source_files.update(capture["project_files_referenced_in_tool_inputs"])
        checks.append({
            "scenario_id": ident, "context_id": meta["id"], "answer_sha256": run["answer_sha256"],
            "visible_messages_count": len(assistant), "first_and_only_response_turn": True,
            "raw_answers_and_all_messages_match_journal": True,
            "dispatch_target_and_recorded_payload_match": True,
            "prompt_plaintext_in_journal_verified": not params["message"].startswith("gAAAAA"),
            "tool_call_bytes_match_journal": True,
            "top_level_tool_names": sorted(top_tools), "nested_tool_names_referenced": sorted(nested_tools),
            "referenced_project_files": capture["project_files_referenced_in_tool_inputs"],
        })
    assert len(context_ids) == len(set(context_ids)), "Response contexts must be distinct"
    errors = []
    for path in SESSIONS.glob("*.jsonl"):
        journal = rows(path)
        meta = journal[0]["payload"]
        source = meta.get("source")
        if not isinstance(source, dict):
            continue
        agent = source.get("subagent", {}).get("thread_spawn", {}).get("agent_path", "")
        if not agent.startswith(("/root/response_b", "/root/review_")):
            continue
        for r in journal:
            q = r["payload"]
            if r["type"] == "event_msg" and q.get("type") == "task_complete" and q.get("error"):
                errors.append({"agent": agent, "context_id": meta["id"], "turn_id": q["turn_id"], "at": r["timestamp"], "error_message": q["error"].get("message"), "classification": "EXECUTION_ENVIRONMENT_ERROR; never acceptance"})
    result = {
        "status": "PASS", "audited_at": datetime.now(timezone.utc).isoformat(), "captured_responses": len(runs),
        "distinct_response_contexts": len(context_ids), "runs_sha256": sha(runs_path.read_bytes()),
        "transcripts_sha256": sha(transcript_path.read_bytes()), "checks": checks,
        "project_files_referenced_union": sorted(source_files), "execution_errors": errors,
        "limits": "Journal dispatch plaintext is encrypted in this environment. Prompt text is separately operator-captured; ciphertext binding does not authenticate its plaintext. Nested tool names are inferred from recorded invocation code. File references prove tool invocation content, not full file reading. No semantic or independent acceptance judgment is made by this audit.",
    }
    (OUT / "capture_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "captured_responses": len(runs), "distinct_response_contexts": len(context_ids), "execution_errors": len(errors)}))


if __name__ == "__main__":
    main()
