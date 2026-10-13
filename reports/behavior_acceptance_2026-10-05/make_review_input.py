"""Freeze captured response subsets before independent semantic review."""
import argparse
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
GROUPS = {
    "privacy": ["B10", "B11", "B12", "B13", "B16"],
    "sources": ["B01", "B02", "B03", "B04", "B08", "B17"],
    "daily": ["B05", "B06", "B07", "B09", "B14", "B15"],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=GROUPS)
    args = parser.parse_args()
    contract_path = ROOT / "standards/behavior_acceptance.json"
    runs = json.loads((OUT / "actual_runs_unreviewed.json").read_text(encoding="utf-8"))["runs"]
    transcripts = json.loads((OUT / "actual_transcripts.json").read_text(encoding="utf-8"))
    selected = [r for r in runs if r["scenario_id"].split("_", 1)[0] in GROUPS[args.group]]
    if len(selected) != len(GROUPS[args.group]):
        raise RuntimeError("Review subset not fully captured")
    target = OUT / ("review_" + args.group + "_input.json")
    data = {
        "group": args.group,
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "runs": selected,
        "transcripts": {r["scenario_id"]: transcripts[r["scenario_id"]] for r in selected},
        "capture_scope": "All exact assistant output_text messages, including commentary and memory-citation metadata; no raw answer rewriting.",
        "review_instruction": "Use every common and applicable scenario criterion in the unchanged contract. Assess all captured messages, and verify material source claims from original files. Explain metadata/rendering uncertainty separately from professional or conversational failures. No expected answers were supplied to response agents.",
    }
    encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if target.exists() and target.read_bytes() != encoded:
        raise RuntimeError("Frozen review input would change")
    target.write_bytes(encoded)
    print(json.dumps({"group": args.group, "runs": len(selected), "input_sha256": hashlib.sha256(encoded).hexdigest()}))


if __name__ == "__main__":
    main()
