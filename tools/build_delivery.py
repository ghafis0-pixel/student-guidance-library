"""Create and inspect an explicit-file delivery archive after public privacy checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

try:
    from . import privacy_guard as privacy
except ImportError:
    import privacy_guard as privacy

MANIFEST_NAME = "DELIVERY_MANIFEST.json"
FORBIDDEN_PARTS = {".git", "__pycache__", "tmp", "temp", "private", "sensitive", "student-data"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".tmp", ".bak"}


def checked_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("scope entries must be explicit relative POSIX file paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"..", "."} or ":" in part for part in path.parts):
        raise ValueError("scope path escapes project root")
    if any(part.lower() in FORBIDDEN_PARTS for part in path.parts) or path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name.startswith("~$"):
        raise ValueError("temporary, cache or private material is outside delivery scope")
    if path.as_posix() != value or value == MANIFEST_NAME:
        raise ValueError("scope contains a noncanonical or reserved path")
    if privacy.scan_data(value):
        raise ValueError("scope path itself needs private review")
    return value


def verify_delivery(archive: Path, expected_manifest: dict | None = None) -> dict:
    """Check actual ZIP members, their bytes and privacy resolution; Git is not involved."""
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if len(names) != len(set(names)) or package.testzip() is not None:
            raise ValueError("archive has duplicate entries or failed CRC")
        manifest = json.loads(package.read(MANIFEST_NAME).decode("utf-8"))
        if expected_manifest is not None and manifest != expected_manifest:
            raise ValueError("archive manifest differs from approved build scope")
        if manifest.get("schema_version") != "1.0" or not isinstance(manifest.get("files"), list):
            raise ValueError("unsupported delivery manifest")
        if privacy.scan_data(manifest):
            raise ValueError("delivery manifest requires privacy review")
        entries = manifest["files"]
        paths = [checked_relative(entry["path"]) for entry in entries]
        if len(paths) != len(set(paths)) or set(names) != set(paths) | {MANIFEST_NAME}:
            raise ValueError("archive member scope differs from manifest")
        for entry in entries:
            content = package.read(entry["path"])
            if len(content) != entry["size"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError("archive member fingerprint mismatch")
            inspection = privacy.require_public_bytes(content, PurePosixPath(entry["path"]).suffix, entry.get("review"))
            if inspection != entry["privacy"]:
                raise ValueError("archive privacy evidence is stale")
    return {"status": "VERIFIED_WITH_LIMITS", "file_count": len(entries),
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "manifest_sha256": privacy.fingerprint(manifest), "guard_version": privacy.VERSION}


def build_delivery(root: Path, paths: list[str], output: Path, reviews: dict[str, dict] | None = None) -> dict:
    root, output = root.resolve(), output.resolve()
    if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
        raise ValueError("nonempty explicit unique file allowlist required")
    reviews = reviews or {}
    normalized = [checked_relative(path) for path in paths]
    if set(reviews) - set(normalized):
        raise ValueError("privacy review refers to a file outside explicit scope")
    payloads: dict[str, bytes] = {}
    entries = []
    for index, relative in enumerate(normalized):
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file() or source == output:
            raise ValueError(f"scope[{index}]: missing, escaped or output file")
        content = source.read_bytes()
        try:
            inspection = privacy.require_public_bytes(content, source.suffix, reviews.get(relative))
        except privacy.PrivacyReviewRequired as error:
            raise privacy.PrivacyReviewRequired([{**finding, "location": f"scope[{index}]:{finding['location']}"} for finding in error.findings]) from None
        payloads[relative] = content
        entry = {"path": relative, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(), "privacy": inspection}
        if inspection["status"] == "REVIEWED":
            entry["review"] = reviews[relative]
        entries.append(entry)
    manifest = {"schema_version": "1.0", "scope": "explicit_file_allowlist", "guard_version": privacy.VERSION,
                "limitations": "Pattern review aid; no complete identity detection or reviewer authentication claim.", "files": entries}
    privacy.require_public_bytes(json.dumps(manifest, ensure_ascii=False).encode("utf-8"), ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".delivery-", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for relative, content in payloads.items():
                package.writestr(relative, content)
            package.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        verify_delivery(temporary, manifest)
        temporary.replace(output)
        return verify_delivery(output, manifest)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify_delivery(args.verify)
        else:
            if not args.scope or not args.output:
                parser.error("--scope and --output are required for a build")
            paths = json.loads(args.scope.read_text(encoding="utf-8"))["paths"]
            reviews = json.loads(args.reviews.read_text(encoding="utf-8"))["reviews"] if args.reviews else None
            result = build_delivery(args.root, paths, args.output, reviews)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        # Exception messages are structural; scanner exceptions never include matched text.
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
