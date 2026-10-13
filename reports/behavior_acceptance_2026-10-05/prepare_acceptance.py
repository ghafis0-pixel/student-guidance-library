"""Bind the new acceptance round to candidate v2 without changing runtime files."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tools.check_behavior_acceptance import capture_project, canonical_sha256, evaluate_runs
from tools.build_review_submission import verify


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(name: str, data: object) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    attachment = Path(r"C:\Users\CSS\Downloads\independent_review_v2_2026-10-05.md")
    package = Path(r"C:\Users\CSS\Downloads\student-guidance-library-candidate-v2-2026-10-05.zip")
    supplement = Path(r"C:\Users\CSS\Downloads\review-v2-verification-and-upload-instructions.zip")
    expected_package = "6a58e5d692376f574f22274e43b939c534f722250bb78da198a7e488b5562d59"
    expected_supplement = "bc7252ed1f3e01a982eadd3ab672ceb5f937fe3bf7dde1e040aa47ac9b8580cd"
    if sha(package.read_bytes()) != expected_package or sha(supplement.read_bytes()) != expected_supplement:
        raise RuntimeError("Attachment hash mismatch")
    verification = verify(package)
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("REVIEW_MANIFEST.json"))
        package_files = {}
        mismatches = []
        for item in manifest["files"]:
            if not item["path"].startswith("project/"):
                continue
            relative = item["path"][len("project/"):]
            current = ROOT / relative
            if not current.is_file() or sha(current.read_bytes()) != item["shared_sha256"]:
                mismatches.append(relative)
            package_files[relative] = item["shared_sha256"]
    if mismatches:
        raise RuntimeError("Workspace differs from candidate v2: " + repr(mismatches))
    head = subprocess.check_output(["git", "-c", "safe.directory=" + ROOT.as_posix(), "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    project = capture_project(ROOT, head=head, extra_files=sorted(package_files))
    save("project_before.json", project)
    save("candidate_package_verification.json", {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "package_sha256": expected_package,
        "supplement_sha256": expected_supplement,
        "verification": verification,
        "package_project_files": len(package_files),
        "workspace_mismatches": mismatches,
        "package_project_snapshot_sha256": canonical_sha256(package_files),
        "package_project_files_sha256": package_files,
    })
    shutil.copyfile(attachment, OUT / "independent_review_received.md")
    contract = json.loads((ROOT / "standards/behavior_acceptance.json").read_text(encoding="utf-8-sig"))
    requests = [{"scenario_id": s["id"], "scenario_text": s["prompt"], "critical": s["critical"], "fresh_required": s["fresh_required"]} for s in contract["scenarios"]]
    save("scenario_requests.json", {"contract_sha256": sha((ROOT / "standards/behavior_acceptance.json").read_bytes()), "requests": requests})
    save("run_plan.json", {
        "round": "candidate-v2-cold-retrieval-2026-10-05",
        "status": "PREPARED",
        "planned_scenarios": len(requests),
        "critical_scenarios": sum(s["critical"] for s in requests),
        "required_fresh_scenarios": sum(s["fresh_required"] for s in requests),
        "all_scenarios_planned_fresh": True,
        "project_snapshot_sha256": project["snapshot_sha256"],
        "contract_sha256": sha((ROOT / "standards/behavior_acceptance.json").read_bytes()),
        "input_policy": "Only the exact scenario prompt is dispatched; no expected answer, rubric, historical answer, review text, or governing source excerpt is supplied to the respondent.",
        "capture_policy": "Capture all visible assistant messages, tool calls, exact final text, input dispatch, context identifier, model metadata, actual reads, and source hashes before semantic review.",
        "review_policy": "A separate reviewer sees the fixed rubric only after response capture; reasons cover every visible assistant message and original source where relevant.",
        "completion_policy": "Missing actual response, full visible capture, independent context, or independent semantic review remains NOT_RUN. A failed criterion stays FAIL; previous 9/8 and 15/2 remain historical.",
        "operational_boundary": "No work-register, plan approval, execution, evidence, or Noor updates are authorized by test success.",
    })
    save("pre_run_NOT_RUN.json", evaluate_runs([], contract, root=ROOT))
    import pypdf
    import pypdfium2
    save("environment_preflight.json", {
        "python": sys.version,
        "pypdf": pypdf.__version__,
        "pypdfium2": pypdfium2.PYPDFIUM_INFO.version,
        "pdfium": pypdfium2.PDFIUM_INFO.version,
        "pdf_reproducibility": "No new privacy extraction or alarm list was generated. Old PDF alarm adjudications are not automatically transferred to this environment.",
        "higher_instruction_limits": "Current Codex developer instructions are present. Additional-agent execution requires direct user authorization. Exact proprietary system build and model weights are unavailable.",
    })
    print(json.dumps({"status": "PREPARED", "package_verification": verification.get("status"), "matched_project_files": len(package_files), "scenario_count": len(requests), "project_snapshot_sha256": project["snapshot_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
