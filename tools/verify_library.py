"""Read-only integrity check for registered fixed assets and source originals."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

try:
    from .check_work_register import validate_register
except ImportError:
    from check_work_register import validate_register


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def library_file(relative: object, root: Path) -> Path | None:
    """Resolve a declared library file, never a traversal or symlink escape."""
    if not isinstance(relative, str) or not relative:
        return None
    rel = PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    path = (root / rel).resolve()
    return path if path.is_relative_to(root.resolve()) and path.is_file() else None


def source_file(item: dict, root: Path) -> Path | None:
    """Either registered original copy suffices; a derived text never substitutes."""
    for key in ("reference_path", "archive_path"):
        path = library_file(item.get(key), root)
        if path is not None and sha256(path) == item.get("sha256"):
            return path
    return None


def validate_manifest(manifest: dict, registry: list[dict], root: Path,
                      *, templates_available: bool = False) -> list[str]:
    """Keep byte integrity without requiring a second identical archived copy."""
    errors: list[str] = []
    entries = manifest["files"]
    if manifest.get("file_count") != len(entries):
        errors.append("manifest file_count mismatch")
    listed = [item["path"] for item in entries]
    if len(listed) != len(set(listed)):
        errors.append("duplicate manifest path")
    archive_sources = {item.get("archive_path"): item for item in registry}
    for item in entries:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"unsafe manifest path: {item['path']}")
            continue
        path = library_file(item["path"], root)
        if path is None:
            source = archive_sources.get(item["path"])
            if source is not None and source.get("sha256") == item["sha256"]:
                if source.get("source_type") == "templates_archive" and templates_available:
                    continue
                path = source_file(source, root)
        if path is None:
            errors.append(f"missing: {item['path']}")
        elif (("size_bytes" in item and path.stat().st_size != item["size_bytes"])
              or sha256(path) != item["sha256"]):
            errors.append(f"hash/size mismatch: {item['path']}")
    return errors


def validate_noor_matrix(matrix: dict, registry: dict, root: Path = ROOT) -> list[str]:
    """All declared source IDs and template paths must resolve directly."""
    errors: list[str] = []
    known = {item["source_id"] for item in registry["sources"]}
    context_path = matrix.get("current_context_path")
    context = (root / context_path).resolve() if isinstance(context_path, str) else None
    if context is None or not context.is_relative_to(root.resolve()) or not context.is_file():
        errors.append("Noor-matrix current context path does not resolve")
    for item in matrix.get("sources", []):
        if item.get("source_id") not in known:
            errors.append(f"unknown Noor-matrix source ID: {item.get('source_id')}")
    records = matrix.get("records", [])
    if any(not isinstance(item.get("record_id"), str) or not item["record_id"].strip()
           for item in records):
        errors.append("missing Noor-matrix record ID")
    if len({item.get("record_id") for item in records}) != len(records):
        errors.append("duplicate Noor-matrix record ID")
    for item in records:
        relative = item.get("original_path")
        path = (root / relative).resolve() if isinstance(relative, str) else None
        if path is None or not path.is_relative_to(root.resolve()) or not path.is_file():
            errors.append(f"Noor-matrix template missing: {item.get('record_id')}: {relative}")
        for source_id in item.get("source_refs", []):
            if source_id not in known:
                errors.append(f"unknown Noor-matrix source ID: {source_id}")
    return errors


def main() -> int:
    errors: list[str] = []
    manifest = load("catalog/manifest.json")
    listed = [item["path"] for item in manifest["files"]]
    registry = load("catalog/source_registry.json")["sources"]
    matrix = load("catalog/records_noor_decision_matrix.json")
    matrix_errors = validate_noor_matrix(matrix, {"sources": registry})
    errors.extend(matrix_errors)
    templates_available = bool(matrix.get("records")) and not matrix_errors
    errors.extend(validate_manifest(manifest, registry, ROOT,
                                    templates_available=templates_available))
    for item in registry:
        if (item.get("source_type") == "templates_archive" and templates_available
                and library_file(item.get("archive_path"), ROOT) is None):
            continue
        if source_file(item, ROOT) is None:
            errors.append(f"original source mismatch: {item['source_id']}")

    errors.extend(validate_register(load("work/register.json"), ROOT))
    archive = next((library_file(item.get("archive_path"), ROOT) for item in registry
                    if item.get("source_type") == "templates_archive"), None)
    if archive is None and not templates_available:
        errors.append("records ZIP missing")
    elif archive is not None:
        with zipfile.ZipFile(archive) as package:
            if package.testzip() is not None:
                errors.append("records ZIP failed CRC check")

    report = {
        "status": "pass" if not errors else "fail",
        "manifest_files": len(listed),
        "source_records": len(registry),
        "noor_matrix_records": len(matrix["records"]),
        "work_records": len(load("work/register.json")["items"]),
        "ocr_required": [item["source_id"] for item in registry if item.get("text_status") == "needs_ocr"],
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
