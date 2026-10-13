"""Bind recorded tool returns without copying their potentially restricted content."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
SESSIONS = Path(r"C:\Users\CSS\.codex\sessions\2026\10\05")


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def exit_codes(value: object) -> list[int]:
    if isinstance(value, dict):
        return [value["exit_code"]] if isinstance(value.get("exit_code"), int) else [code for child in value.values() for code in exit_codes(child)]
    if isinstance(value, list):
        return [code for child in value for code in exit_codes(child)]
    return []


def main() -> None:
    transcripts = json.loads((OUT / "retest_b10_actual_transcripts.json").read_text(encoding="utf-8"))
    results = {}
    for ident, capture in transcripts.items():
        rows = [json.loads(line) for line in (SESSIONS / capture["session_file"]).read_text(encoding="utf-8").splitlines() if line.strip()]
        returns = {row["payload"]["call_id"]: row for row in rows if row["type"] == "response_item" and row["payload"].get("type") in {"custom_tool_call_output", "function_call_output"}}
        items = []
        for call in capture["tool_calls"]:
            returned = returns.get(call["call_id"])
            if not returned:
                items.append({"call_id": call["call_id"], "status": "RETURN_NOT_FOUND"})
                continue
            output = returned["payload"].get("output")
            blocks = output if isinstance(output, list) else [{"type": "text", "text": output}] if isinstance(output, str) else []
            texts = [block.get("text", "") for block in blocks if isinstance(block, dict) and isinstance(block.get("text"), str)]
            codes = []
            for text in texts:
                try:
                    codes.extend(exit_codes(json.loads(text)))
                except (ValueError, TypeError):
                    pass
            items.append({"call_id": call["call_id"], "name": call["name"], "returned_at": returned["timestamp"], "status": "RETURN_RECORDED", "output_sha256": hashlib.sha256(canonical(output)).hexdigest(), "text_blocks": len(texts), "image_blocks": sum(block.get("type") in {"image", "input_image"} for block in blocks if isinstance(block, dict)), "nested_shell_exit_codes_observed": codes, "nonempty_return": bool(output)})
        results[ident] = {"context_id": capture["context_id"], "referenced_project_paths_in_invocation": capture["project_files_referenced_in_tool_inputs"], "tool_returns": items}
    result = {"scope": "Recorded return hashes and status metadata for each captured invocation, without reproducing tool-output content.", "limits": "Successful returns and source paths in invocation show retrieval activity; they do not certify full original-source reading, exact page interpretation, absence of truncation, or rendered images. Exit codes are included only when explicitly printed in a parseable JSON return.", "results": results}
    (OUT / "retest_b10_tool_return_receipts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scenarios": len(results), "calls": sum(len(r["tool_returns"]) for r in results.values()), "returns_missing": sum(item["status"] == "RETURN_NOT_FOUND" for r in results.values() for item in r["tool_returns"])}))


if __name__ == "__main__":
    main()
