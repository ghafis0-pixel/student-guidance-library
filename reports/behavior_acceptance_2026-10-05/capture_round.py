"""Capture completed fresh agents from actual session journals without rewriting answers."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SESSION_DIR = Path(r"C:\Users\CSS\.codex\sessions\2026\10\05")
PARENT_ID = "01a108d7-1817-7261-8432-a7e2be564ca1"
sys.path.insert(0, str(ROOT))
from tools.check_behavior_acceptance import canonical_sha256, capture_project, evaluate_answer

# Tool-status failures observed by the parent; these are retained even when the
# child journal has no task_complete event for the failed turn.
FAILED_ATTEMPTS = {
    "/root/response_b05": "Fatal error: application network permission was revoked",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plain(q: dict) -> str:
    return "".join(v.get("text", "") for v in q.get("content", []) if v.get("type") in {"input_text", "output_text", "text"})


def read_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A concurrently appended final line is not a completed record.
            if line != path.read_text(encoding="utf-8").splitlines()[-1]:
                raise
    return rows


def save(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    requests = json.loads((OUT / "scenario_requests.json").read_text(encoding="utf-8"))["requests"]
    contract = json.loads((ROOT / "standards/behavior_acceptance.json").read_text(encoding="utf-8-sig"))
    initial_project = json.loads((OUT / "project_before.json").read_text(encoding="utf-8"))
    for name, checksum in initial_project["files"].items():
        if sha((ROOT / name).read_bytes()) != checksum:
            raise RuntimeError("Project changed while responding: " + name)
    available_files = list(initial_project["files"])
    available_files += [p.relative_to(ROOT).as_posix() for p in (ROOT / "extracted_text").rglob("*") if p.is_file()]
    parent = next(SESSION_DIR.glob("*" + PARENT_ID + ".jsonl"))
    dispatches = {}
    for row in read_rows(parent):
        q = row.get("payload", {})
        if row["type"] == "response_item" and q.get("type") == "function_call" and q.get("name") == "spawn_agent":
            args = json.loads(q["arguments"])
            path = "/root/" + args["task_name"]
            if path.startswith("/root/response_b"):
                dispatches[path] = {
                    "dispatch_call_id": q["call_id"], "method": q["name"],
                    "timestamp": row["timestamp"], "fork_turns": args.get("fork_turns"),
                    "root_session_file": parent.name,
                    "recorded_payload_sha256": sha(args["message"].encode("utf-8")),
                    "recorded_payload_encrypted": args["message"].startswith("gAAAAA"),
                    "input_plaintext_status": "OPERATOR_CAPTURED_AT_TOOL_DISPATCH; LOCAL_JOURNAL_ENCRYPTED" if args["message"].startswith("gAAAAA") else "JOURNAL_PLAINTEXT",
                }
    transcripts = {}
    runs = []
    statuses = []
    incomplete_attempts = []
    for path in sorted(SESSION_DIR.glob("*.jsonl")):
        rows = read_rows(path)
        meta = next((r["payload"] for r in rows if r["type"] == "session_meta"), {})
        source = meta.get("source")
        if not isinstance(source, dict):
            continue
        agent_path = source.get("subagent", {}).get("thread_spawn", {}).get("agent_path", "")
        if not agent_path.startswith("/root/response_b"):
            continue
        matched = re.fullmatch(r"/root/response_b(\d{2})(?:_attempt(\d+))?", agent_path)
        if not matched:
            continue
        code = "B" + matched.group(1)
        attempt = int(matched.group(2) or "1")
        request = next((r for r in requests if r["scenario_id"].startswith(code + "_")), None)
        if not request:
            continue
        turn_starts = [r for r in rows if r["type"] == "event_msg" and r["payload"].get("type") == "task_started"]
        completions = [r for r in rows if r["type"] == "event_msg" and r["payload"].get("type") == "task_complete" and not r["payload"].get("error")]
        if not completions:
            aborted = any(r["type"] == "event_msg" and r["payload"].get("type") in {"turn_aborted", "task_aborted"} for r in rows)
            recorded_errors = [r["payload"]["error"].get("message", "Actor failure") for r in rows if r["type"] == "event_msg" and r["payload"].get("type") == "task_complete" and r["payload"].get("error")]
            failed = recorded_errors[-1] if recorded_errors else FAILED_ATTEMPTS.get(agent_path)
            partial_messages = [plain(r["payload"]) for r in rows if r["type"] == "response_item" and r["payload"].get("type") == "message" and r["payload"].get("role") == "assistant"]
            reason = ("Tool-reported actor failure: " + failed) if failed else "Interrupted after extended wait without a completed final response; rerun is a new context, not an edited answer." if aborted else "No completed final response at capture time."
            incomplete_attempts.append({"scenario_id": request["scenario_id"], "attempt": attempt, "context_id": meta["id"], "agent_path": agent_path, "session_file": path.name, "execution": {"status": "NOT_RUN", "reason": reason}, "visible_assistant_messages": partial_messages, "last_activity_at": rows[-1]["timestamp"], "dispatch": dispatches.get(agent_path)})
            statuses.append({"scenario_id": request["scenario_id"], "attempt": attempt, "status": "ERRORED_NOT_RUN" if failed else "INTERRUPTED_NOT_RUN" if aborted else "RUNNING", "context_id": meta["id"]})
            continue
        if len(turn_starts) != 1 or len(completions) != 1:
            raise RuntimeError("Response context reused: " + agent_path)
        messages = [
            {"phase": r["payload"].get("phase"), "text": plain(r["payload"]), "timestamp": r["timestamp"]}
            for r in rows if r["type"] == "response_item" and r["payload"].get("type") == "message" and r["payload"].get("role") == "assistant"
        ]
        finals = [m for m in messages if m["phase"] in {"final", "final_answer"}]
        if len(finals) != 1:
            raise RuntimeError("Final response capture ambiguous: " + agent_path)
        final_answer = finals[0]["text"]
        calls = []
        for r in rows:
            q = r.get("payload", {})
            if r["type"] == "response_item" and q.get("type") in {"function_call", "custom_tool_call"}:
                raw = q.get("arguments", q.get("input", ""))
                calls.append({"name": q["name"], "call_id": q["call_id"], "type": q["type"], "input": raw, "timestamp": r["timestamp"]})
        inputs = "\n".join(c["input"] for c in calls).replace("\\\\", "/").replace("\\", "/")
        referenced = sorted(set(n for n in available_files if n in inputs))
        bound_files = dict(initial_project["files"])
        for name in referenced:
            if name not in bound_files:
                bound_files[name] = sha((ROOT / name).read_bytes())
        project = {"head": initial_project["head"], "files": bound_files, "snapshot_sha256": canonical_sha256(bound_files)}
        ctx = next((r["payload"] for r in rows if r["type"] == "turn_context"), {})
        instruction_refs = []
        for r in rows:
            q = r.get("payload", {})
            if r["type"] == "response_item" and q.get("type") == "message" and q.get("role") in {"system", "developer", "user"}:
                text = plain(q)
                instruction_refs.append({"role": q.get("role"), "sha256": sha(text.encode("utf-8")), "characters": len(text), "timestamp": r["timestamp"], "encrypted_content_present": any(v.get("type") == "encrypted_content" for v in q.get("content", []))})
        dispatch = dispatches[agent_path]
        dispatch["operator_captured_actual_prompt"] = request["scenario_text"]
        dispatch["operator_prompt_sha256"] = sha(request["scenario_text"].encode("utf-8"))
        if dispatch["fork_turns"] != "none":
            raise RuntimeError("Response was forked with history")
        visible_text = [m["text"] for m in messages]
        transcript = {
            "scenario_id": request["scenario_id"], "context_id": meta["id"], "agent_path": agent_path,
            "session_file": path.name, "turn_id": turn_starts[0]["payload"]["turn_id"],
            "captured_at": completions[0]["timestamp"], "visible_assistant_messages": visible_text,
            "assistant_message_records": messages, "final_answer": final_answer,
            "tool_calls": calls, "project_files_referenced_in_tool_inputs": referenced,
            "instruction_fingerprints": instruction_refs, "dispatch": dispatch,
            "raw_capture_policy": "Exact assistant output_text preserved, including any memory-citation metadata. No trimming, URL rewriting, citation removal, or text normalization.",
            "capture_limits": "Local journals encrypt dispatched task plaintext; exact prompt is separately operator-recorded at the tool call. File mentions in tool inputs identify referenced files, not proof that every byte was read. Proprietary system build and model weights unavailable. Raw memory-citation metadata may be rendered specially by the app; raw checker still receives it unchanged.",
        }
        if request["scenario_id"] in transcripts:
            raise RuntimeError("Multiple completed answers cannot be silently selected: " + request["scenario_id"])
        transcript["attempt"] = attempt
        transcripts[request["scenario_id"]] = transcript
        tools = sorted(set(c["name"] for c in calls))
        if any("tools.exec_command" in c["input"] for c in calls):
            tools.append("exec_command")
        run = {
            "schema_version": contract["schema_version"], "scenario_id": request["scenario_id"], "scenario_text": request["scenario_text"],
            "actual_answer": final_answer, "answer_sha256": sha(final_answer.encode("utf-8")), "project": project,
            "execution": {
                "status": "RUN", "kind": "actual_conversation", "context_id": meta["id"],
                "isolated": True, "prior_messages_count": 0,
                "model": {"name": ctx.get("model", "unavailable"), "version": ctx.get("model", "unavailable") + "; exact build unavailable"},
                "tools": tools, "captured_at": completions[0]["timestamp"],
                "transcript_ref": "reports/behavior_acceptance_2026-10-05/actual_transcripts.json#" + request["scenario_id"],
                "visible_messages_sha256": canonical_sha256(visible_text),
                "input_delivery": "exact scenario only; fork_turns=none; runtime/source retrieval from files; no expected answer or rubric supplied",
                "input_plaintext_status": dispatch["input_plaintext_status"],
                "dispatch_ref": parent.name + "#" + dispatch["dispatch_call_id"],
                "actual_tool_calls_sha256": canonical_sha256(calls),
                "runtime_cli_version": meta.get("cli_version", "unavailable"),
            },
        }
        runs.append(run)
        scenario = next(s for s in contract["scenarios"] if s["id"] == request["scenario_id"])
        statuses.append({"scenario_id": request["scenario_id"], "status": "CAPTURED_UNREVIEWED", "context_id": meta["id"], "visible_message_count": len(messages), "raw_text_checker_issues": evaluate_answer(final_answer, scenario)})
    runs.sort(key=lambda r: r["scenario_id"])
    save("actual_transcripts.json", transcripts)
    save("actual_runs_unreviewed.json", {"runs": runs})
    save("incomplete_attempts.json", incomplete_attempts)
    status = {"captured_at": datetime.now(timezone.utc).isoformat(), "captured_runs": len(runs), "planned_runs": len(requests), "items": sorted(statuses, key=lambda r: r["scenario_id"])}
    save("capture_progress.json", status)
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
