"""Review exact artifact bytes, then build and verify a local evidence archive."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DEST = Path(r"C:\Users\CSS\.codex\visualizations\2026\10\04\01a108d7-1817-7261-8432-a7e2be564ca1")
sys.path.insert(0, str(ROOT))
from tools.privacy_guard import VERSION, fingerprint, require_public_bytes, scan_bytes


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(name: str, data: object) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve(data: object, location: str) -> tuple[object, object, str]:
    path = location.rsplit(":line:", 1)[0]
    node, parent, actual_key = data, None, ""
    for match in re.finditer(r"\.(field#\d+|[a-z_][a-z0-9_]*)|\[(\d+)\]", path):
        parent = node
        if match.group(2) is not None:
            actual_key = int(match.group(2))
        elif match.group(1).startswith("field#"):
            actual_key = list(node)[int(match.group(1)[6:])]
        else:
            actual_key = match.group(1)
        node = node[actual_key]
    return node, parent, str(actual_key)


def main() -> None:
    state = json.loads((OUT / "CANDIDATE_STATE.json").read_text(encoding="utf-8"))
    if state.get("selected_response_count", state["actual_completed_responses"]) != 17:
        raise RuntimeError("Final state required before delivery")
    allowed_sources = json.loads((OUT / "project_before.json").read_text(encoding="utf-8"))["files"]
    entries = []
    excluded = {"DELIVERY_MANIFEST.json", "delivery_verification.json", "privacy_delivery_review.json"}
    for path in sorted(OUT.iterdir()):
        if not path.is_file() or path.name in excluded:
            continue
        content = path.read_bytes()
        findings = scan_bytes(content, path.suffix)
        review = None
        digest_findings = []
        if findings:
            if path.suffix != ".json":
                raise RuntimeError("Manual privacy review required: " + path.name)
            data = json.loads(content)
            for finding in findings:
                value, parent, key = resolve(data, finding["location"])
                # Clear only exact SHA values demonstrably matching project bytes.
                if finding["code"] != "CONTACT_NUMBER" or not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                    raise RuntimeError("Unresolved privacy finding: " + path.name + " " + finding["location"])
                source_path = ROOT / key
                if not isinstance(parent, dict) or allowed_sources.get(key) != value or not source_path.is_file() or sha(source_path.read_bytes()) != value:
                    raise RuntimeError("Digest finding is not bound to source bytes: " + path.name)
                digest_findings.append({"location": finding["location"], "code": finding["code"], "classification": "SOURCE_FILE_SHA256_FALSE_POSITIVE", "source_path": key, "source_sha256": value})
            review = {"guard_version": VERSION, "decision": "cleared", "content_sha256": sha(content), "findings_sha256": fingerprint(findings), "reference": "privacy_delivery_review.json", "reason": "Every finding in this exact content and finding set is a 64-character SHA256 value verified against its corresponding project file. No contact record is represented by these matched values."}
        gate = require_public_bytes(content, path.suffix, review)
        entries.append({"path": path.name, "bytes": len(content), "sha256": sha(content), "gate": gate, "review": review, "resolved_findings": digest_findings})
    privacy = {"reviewed_at": datetime.now(timezone.utc).isoformat(), "scope": "Exact new test artifacts only; fictional scenarios and tool invocation records, no school execution or case record. Pattern findings resolved only when demonstrably source-file digest values.", "limits": "Pattern scanning is not comprehensive identity detection. No PDF extraction adjudication, UI rendering guarantee, or original reference privacy clearance is inherited.", "files": entries}
    save("privacy_delivery_review.json", privacy)
    receipt = (OUT / "privacy_delivery_review.json").read_bytes()
    require_public_bytes(receipt, ".json")
    members = {item["path"]: {"bytes": item["bytes"], "sha256": item["sha256"]} for item in entries}
    members["privacy_delivery_review.json"] = {"bytes": len(receipt), "sha256": sha(receipt)}
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "candidate_status": state["candidate_status"], "acceptance_status": state["status"], "members": members, "limits": "Local evidence archive; excludes source project, original session journals, restricted case records, and this manifest's own digest."}
    save("DELIVERY_MANIFEST.json", manifest)
    require_public_bytes((OUT / "DELIVERY_MANIFEST.json").read_bytes(), ".json")
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / "behavior_acceptance_candidate_v2_2026-10-05_evidence.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for name in [*members, "DELIVERY_MANIFEST.json"]:
            target.write(OUT / name, arcname="behavior_acceptance_2026-10-05/" + name)
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None or len(check.namelist()) != len(set(check.namelist())):
            raise RuntimeError("Archive CRC or duplicate member check failed")
        for name, item in members.items():
            data = check.read("behavior_acceptance_2026-10-05/" + name)
            if len(data) != item["bytes"] or sha(data) != item["sha256"] or data != (OUT / name).read_bytes():
                raise RuntimeError("Archive byte binding failed: " + name)
        if check.read("behavior_acceptance_2026-10-05/DELIVERY_MANIFEST.json") != (OUT / "DELIVERY_MANIFEST.json").read_bytes():
            raise RuntimeError("Manifest byte binding failed")
    verification = {"status": "STRUCTURE_AND_BYTES_PASS", "archive_path": str(archive), "archive_bytes": archive.stat().st_size, "archive_sha256": sha(archive.read_bytes()), "members": len(members) + 1, "crc_pass": True, "duplicates": False, "manifest_sha256": sha((OUT / "DELIVERY_MANIFEST.json").read_bytes()), "local_only": True, "uploaded": False}
    save("delivery_verification.json", verification)
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == "__main__":
    main()
