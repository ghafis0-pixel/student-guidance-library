"""Validate phase-specific Gate assessments and bind results to current inputs.

Location verification is structural. A located page is never a machine-verified
endorsement of its claim, the reviewer's identity, or a field event.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from importlib.metadata import PackageNotFoundError, version
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree


RUNNER_VERSION = "1.2.2"
BINDING_VERSION = "1.0"
LIB = Path(__file__).resolve().parents[1]
RULES_PATH = LIB / "standards/weekly_plan_gate_rules.yaml"
SOURCE_REGISTRY_PATH = LIB / "catalog/source_registry.json"
MANIFEST_PATH = LIB / "catalog/manifest.json"
SCHOOL_CONTEXT_PATH = LIB / "context/current.json"
PINNED_PLANNING_KEYS = {"SOURCE_ROUTING", "PROGRAM_SOURCE_RULES"}
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
LEVEL_ORDER = {"INFO": 0, "WARNING": 1, "REVIEW": 2, "BLOCKER": 3}
RESULTS = {"PASS", "FAIL", "REVIEW", "NOT_APPLICABLE", "NOT_ASSESSABLE_YET"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return data


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_date(value: Any) -> bool:
    if not nonempty(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def valid_datetime(value: Any) -> bool:
    if not nonempty(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def repository_file(relative: Any, root: Path | None = None) -> Path | None:
    if not nonempty(relative):
        return None
    root = Path(root or LIB).resolve()
    candidate = (root / PurePosixPath(relative)).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def source_ids(root: Path | None = None) -> set[str]:
    registry = load_json(Path(root or LIB) / "catalog/source_registry.json")
    return {
        item.get("source_id")
        for item in registry.get("sources", [])
        if isinstance(item, dict) and nonempty(item.get("source_id"))
    }


def canonical_sha256(value: Any) -> str:
    """All JSON content; object keys sorted, array order preserved, UTF-8, no NaN."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def source_records(root: Path) -> dict[str, dict[str, Any]]:
    registry = load_json(root / "catalog/source_registry.json")
    return {item["source_id"]: item for item in registry.get("sources", [])
            if isinstance(item, dict) and nonempty(item.get("source_id"))}


def _normalized_text(text: str) -> str:
    # Whitespace only: no fuzzy match or transliteration can invent a heading.
    return " ".join(text.split())


def _json_pointer_exists(data: Any, pointer: str) -> bool:
    if not pointer.startswith("/"):
        return False
    try:
        for token in pointer[1:].split("/"):
            if re.search(r"~(?![01])", token):
                return False
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(data, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", token):
                    return False
                data = data[int(token)]
            elif isinstance(data, dict):
                data = data[token]
            else:
                return False
    except (KeyError, IndexError):
        return False
    return True


def inspect_locator(locator: Any, root: Path | None = None,
                    records: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return separate source/location/semantic facts, never sensitive excerpts.

    PDF physical pages are 1-based. Printed labels require an explicit map tied
    to the source bytes. PDF sections and OCR cannot be mechanically confirmed.
    """
    root = Path(root or LIB).resolve()
    checked: dict[str, Any] = {"source_status": "UNRESOLVED", "location_status": "INVALID",
        "semantic_support": "NOT_AUTOMATICALLY_VERIFIED", "input_paths": [], "issue": None}

    def invalid(message: str, review: bool = False) -> dict[str, Any]:
        checked["issue"] = message
        checked["location_status"] = "REVIEW_REQUIRED" if review else "INVALID"
        return checked

    if not isinstance(locator, dict):
        return invalid("locator must be an object")
    allowed = {"path", "pdf_page", "printed_page", "page_map", "section",
               "paragraph", "text", "page_or_section"}
    if set(locator) - allowed:
        return invalid("unknown locator fields: " + ", ".join(sorted(set(locator) - allowed)))
    relative = locator.get("path")
    if not nonempty(relative):
        return invalid("locator.path is required")
    record: dict[str, Any] | None = None
    if relative.startswith("source_id:"):
        source_id = relative.removeprefix("source_id:").strip()
        records = records if records is not None else source_records(root)
        record = records.get(source_id)
        if record is None:
            return invalid("unknown source identifier: " + source_id)
        relative = record.get("reference_path")
    path = repository_file(relative, root)
    if path is None:
        return invalid("locator path does not exist inside the library or does not resolve to a file")
    relative = path.relative_to(root).as_posix()
    checked.update(source_status="EXISTS", resolved_path=relative, input_paths=[relative])
    if record and nonempty(record.get("sha256")) and record["sha256"] != sha256(path):
        return invalid("registered locator source does not match its recorded version")

    selectors = [key for key in ("pdf_page", "printed_page", "section", "paragraph", "page_or_section")
                 if key in locator]
    if len(selectors) != 1:
        return invalid("locator requires exactly one typed page, section, or paragraph selector")
    selector = selectors[0]
    if "page_map" in locator and selector != "printed_page":
        return invalid("page_map is only valid with printed_page")
    if "text" in locator and selector != "paragraph":
        return invalid("text is only valid with paragraph")
    if selector == "page_or_section":
        return invalid("legacy page_or_section is ambiguous; migrate to an explicit typed locator", True)

    suffix = path.suffix.lower()
    if selector in {"pdf_page", "printed_page"}:
        if suffix != ".pdf":
            return invalid("PDF page selector requires a PDF file")
        try:
            from pypdf import PdfReader
            page_count = len(PdfReader(path).pages)
        except ImportError:
            return invalid("PDF reader unavailable; physical page needs review", True)
        except Exception:
            return invalid("PDF could not be read; physical page needs review", True)
        checked["page_count"] = page_count
        page = locator.get("pdf_page")
        if selector == "printed_page":
            label = locator.get("printed_page")
            if not nonempty(label):
                return invalid("printed_page must be a non-empty printed label")
            mapping_path = repository_file(locator.get("page_map"), root)
            if mapping_path is None:
                return invalid("printed page needs a documented version-bound page_map; no implicit conversion", True)
            checked["input_paths"].append(mapping_path.relative_to(root).as_posix())
            try:
                mapping = load_json(mapping_path)
            except (OSError, ValueError):
                return invalid("page_map is unavailable or invalid")
            if mapping.get("source_sha256") != sha256(path):
                return invalid("page_map source hash mismatch")
            if not nonempty(mapping.get("reviewed_by")) or not valid_datetime(mapping.get("reviewed_at")):
                return invalid("page_map requires review attribution and date")
            entries = mapping.get("mapping")
            if not isinstance(entries, dict) or label not in entries:
                return invalid("printed page is not present in the page_map", True)
            page = entries[label]
            checked["printed_page"] = label
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= page_count:
            return invalid(f"PDF page {page!r} outside physical page range 1..{page_count}")
        checked.update(location_status="VERIFIED", pdf_page=page)
        return checked

    if selector == "paragraph":
        index, expected = locator.get("paragraph"), locator.get("text")
        if suffix != ".docx":
            return invalid("paragraph selector currently requires DOCX")
        if isinstance(index, bool) or not isinstance(index, int) or index < 1 or not nonempty(expected):
            return invalid("DOCX paragraph requires a positive 1-based index and exact text")
    else:
        section = locator.get("section")
        if not nonempty(section):
            return invalid("section must be a non-empty verifiable title or JSON Pointer")

    try:
        if suffix in {".md", ".markdown"}:
            text = path.read_text(encoding="utf-8-sig")
            headings = []
            fenced = False
            previous = ""
            for line in text.splitlines():
                if re.match(r"^\s*(```|~~~)", line):
                    fenced = not fenced
                    previous = ""
                    continue
                if fenced:
                    continue
                match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
                if match:
                    headings.append(_normalized_text(match.group(1)))
                elif previous and re.fullmatch(r" {0,3}(?:=+|-+)\s*", line):
                    headings.append(_normalized_text(previous))
                previous = line
            found = _normalized_text(section) in headings
        elif suffix in {".json", ".yaml", ".yml"}:
            # Project YAML is JSON-compatible; unsupported real YAML gets review.
            found = _json_pointer_exists(load_json(path), section)
        elif suffix == ".docx":
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            with zipfile.ZipFile(path) as archive:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            paragraphs = ["".join(node.text or "" for node in p.findall(".//w:t", ns))
                          for p in document.findall(".//w:p", ns)]
            if selector == "paragraph":
                found = index <= len(paragraphs) and _normalized_text(paragraphs[index - 1]) == _normalized_text(expected)
            else:
                # Plain Word titles often have no heading style. Require an
                # exact whole paragraph title, never a loose multi-part phrase.
                found = _normalized_text(section) in {_normalized_text(p) for p in paragraphs}
        else:
            return invalid("section cannot be automatically verified for this file type; review source", True)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return invalid("section cannot be verified from the available source; review required", True)
    if not found:
        return invalid("section or paragraph does not exist at the stated location")
    checked["location_status"] = "VERIFIED"
    return checked


def locator_error(locator: Any, known_source_ids: set[str], root: Path | None = None) -> str | None:
    """Compatibility helper; new callers should use the three-part inspection."""
    return inspect_locator(locator, root).get("issue")


def result_binding(assessment: dict[str, Any], plan: Path, ruleset: dict[str, Any],
                   root: Path, locator_checks: dict[str, Any]) -> dict[str, Any]:
    paths = {"standards/weekly_plan_gate_rules.yaml", "catalog/source_registry.json",
             "catalog/manifest.json", "context/current.json"}
    schema = "standards/weekly_plan_gate_assessment.schema.json"
    if repository_file(schema, root):
        paths.add(schema)
    references = assessment.get("references_checked", [])
    for reference in references if isinstance(references, list) else []:
        if isinstance(reference, dict) and nonempty(reference.get("path")):
            paths.add(reference["path"])
    for check in locator_checks.values():
        paths.update(check.get("input_paths", []))
    fingerprints = []
    for relative in sorted(paths):
        path = repository_file(relative, root)
        fingerprints.append({"path": relative, "sha256": sha256(path) if path else None})
    try:
        pdf_reader_version = version("pypdf")
    except PackageNotFoundError:
        pdf_reader_version = "unavailable"
    binding = {
        "binding_version": BINDING_VERSION,
        "assessment_sha256": canonical_sha256(assessment),
        "rules_sha256": sha256(root / "standards/weekly_plan_gate_rules.yaml"),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "input_fingerprints": fingerprints,
        "runtime_dependencies": {"pypdf": pdf_reader_version},
    }
    binding["binding_sha256"] = canonical_sha256({**binding,
        "gate_version": ruleset.get("gate_version"), "runner_version": RUNNER_VERSION,
        "phase": assessment.get("phase"), "plan_sha256": sha256(plan) if plan.is_file() else None})
    return binding


def verify_current_result(assessment: dict[str, Any], plan: Path, saved: Any,
                          root: Path | None = None) -> list[str]:
    """Re-evaluate current bytes; return errors instead of trusting stored status."""
    if not isinstance(saved, dict) or saved.get("binding_version") != BINDING_VERSION:
        return ["Historical or unbound Gate result is insufficient for current readiness"]
    try:
        fresh = evaluate(assessment, plan, root=root)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return ["Current Gate evaluation could not complete; readiness is not established"]
    errors = []
    if saved != fresh:
        errors.append("Saved Gate result differs from current assessment, rules, runner, phase, or inputs")
    if fresh["gate_status"] not in {"APPROVED", "APPROVED_WITH_WARNINGS"}:
        errors.append("Current Gate evaluation is not ready: " + fresh["gate_status"])
    return errors


def empty_result(ruleset: dict[str, Any], assessment: Any, issues: list[str]) -> dict[str, Any]:
    assessment = assessment if isinstance(assessment, dict) else {}
    return {
        "gate_status": "BLOCKED",
        "gate_version": ruleset.get("gate_version"),
        "runner_version": RUNNER_VERSION,
        "schema_version": ruleset.get("schema_version"),
        "phase": assessment.get("phase"),
        "gate_result_date": assessment.get("gate_result_date"),
        "checked_by": assessment.get("checked_by"),
        "plan_sha256": assessment.get("plan_sha256"),
        "references_checked": assessment.get("references_checked", []),
        "blocking_issues": issues,
        "human_reviews": [],
        "warnings": [],
        "information": [],
        "pending_items": [],
        "passed_rules": [],
        "failed_rules": [],
        "not_applicable_rules": [],
        "not_assessable_rules": [],
        "affected_rules_by_reference": {},
        "scope": "Phase-specific review; never proof of field execution or Noor save by itself.",
    }


def evaluate(assessment: Any, plan: Path, root: Path | None = None) -> dict[str, Any]:
    root = Path(root or LIB).resolve()
    try:
        ruleset = load_json(root / "standards/weekly_plan_gate_rules.yaml")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return empty_result({}, assessment, [f"Ruleset unavailable or invalid: {error}"])

    if not isinstance(assessment, dict):
        return empty_result(ruleset, {}, ["Assessment must be a JSON object"])

    blockers: list[str] = []
    human_reviews: list[str] = []
    warnings: list[str] = []
    information: list[str] = []
    pending_items: list[str] = []
    passed: list[str] = []
    failed: list[str] = []
    not_applicable: list[str] = []
    not_assessable: list[str] = []
    affected_rules: dict[str, list[str]] = {}
    locator_checks: dict[str, dict[str, Any]] = {}

    required_metadata = {
        "schema_version",
        "gate_version",
        "phase",
        "gate_result_date",
        "checked_by",
        "plan_sha256",
        "references_checked",
        "results",
    }
    allowed_metadata = required_metadata | {"notes"}
    missing_metadata = sorted(required_metadata - assessment.keys())
    if missing_metadata:
        blockers.append("Assessment metadata missing: " + ", ".join(missing_metadata))
    unexpected_metadata = sorted(assessment.keys() - allowed_metadata)
    if unexpected_metadata:
        blockers.append("Unknown assessment fields: " + ", ".join(unexpected_metadata))

    if ruleset.get("schema_version") != "2.1":
        blockers.append("Unsupported ruleset schema version")
    if assessment.get("schema_version") != ruleset.get("schema_version"):
        blockers.append("Assessment schema version mismatch")
    if assessment.get("gate_version") != ruleset.get("gate_version"):
        blockers.append("Gate version mismatch")
    compatibility = ruleset.get("runner_compatibility", {})
    if compatibility.get("compatible_runner") != f">={RUNNER_VERSION}":
        blockers.append("Ruleset does not declare compatibility with this runner")
    if compatibility.get("compatible") is not True:
        blockers.append("Ruleset runner compatibility is not enabled")

    phase = assessment.get("phase")
    phases = set(ruleset.get("phases", []))
    if phase not in phases:
        blockers.append("Unknown or missing Gate phase")
    if not valid_date(assessment.get("gate_result_date")):
        blockers.append("gate_result_date must be a valid ISO date")
    if not nonempty(assessment.get("checked_by")):
        blockers.append("checked_by must be non-empty")

    plan = Path(plan)
    if not plan.is_file():
        blockers.append(f"Plan file unavailable: {plan}")
    else:
        plan_hash = assessment.get("plan_sha256")
        if not nonempty(plan_hash) or not HEX_64.fullmatch(plan_hash):
            blockers.append("plan_sha256 must be a lowercase SHA-256 value")
        elif plan_hash != sha256(plan):
            blockers.append("Plan hash mismatch")

    definitions = ruleset.get("rule_definitions", [])
    if not isinstance(definitions, list):
        blockers.append("Ruleset rule_definitions must be an array")
        definitions = []
    definition_ids = [
        rule.get("rule_id") for rule in definitions if isinstance(rule, dict) and nonempty(rule.get("rule_id"))
    ]
    if len(definition_ids) != len(definitions) or len(set(definition_ids)) != len(definition_ids):
        blockers.append("Ruleset contains missing or duplicate rule identifiers")
    if any(rule.get("review_level") not in LEVEL_ORDER for rule in definitions if isinstance(rule, dict)):
        blockers.append("Ruleset contains an unknown review level")
    applicable = [rule for rule in definitions if isinstance(rule, dict) and phase in rule.get("phases", [])]
    rule_by_id = {
        rule.get("rule_id"): rule
        for rule in applicable
        if isinstance(rule, dict) and nonempty(rule.get("rule_id"))
    }

    reference_catalog = ruleset.get("reference_catalog", {})
    try:
        school_context = load_json(root / "context/current.json")
        if not isinstance(school_context.get("student_count"), int) or school_context["student_count"] <= 0:
            blockers.append("School context student_count is missing or invalid")
    except (OSError, ValueError, json.JSONDecodeError):
        blockers.append("School context unavailable or invalid")
    try:
        approved_assets = {
            item["path"]: item["sha256"]
            for item in load_json(root / "catalog/manifest.json")["files"]
        }
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        approved_assets = {}
        blockers.append("Approved planning-asset manifest unavailable or invalid")
    required_reference_keys = {
        key
        for rule in applicable
        for key in rule.get("reference_keys", [])
    }
    references = assessment.get("references_checked", [])
    if not isinstance(references, list) or not references:
        blockers.append("references_checked must be a non-empty array")
        references = []
    checked_by_key: dict[str, dict[str, Any]] = {}
    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            blockers.append(f"Reference #{index + 1} must be an object")
            continue
        key = reference.get("key")
        path_text = reference.get("path")
        digest = reference.get("sha256")
        unexpected_reference_fields = sorted(set(reference) - {"key", "path", "sha256"})
        if unexpected_reference_fields:
            blockers.append(
                f"Reference #{index + 1} has unknown fields: " + ", ".join(unexpected_reference_fields)
            )
        if not nonempty(key) or key in checked_by_key:
            blockers.append(f"Reference #{index + 1} has a missing or duplicate key")
            continue
        checked_by_key[key] = reference
        expected_path = reference_catalog.get(key)
        if not nonempty(expected_path):
            blockers.append(f"Unknown reference key: {key}")
            continue
        if path_text != expected_path:
            blockers.append(f"Reference path mismatch for {key}")
        path = repository_file(path_text, root)
        if path is None:
            blockers.append(f"Reference unavailable: {key}")
        elif not nonempty(digest) or not HEX_64.fullmatch(digest) or sha256(path) != digest:
            blockers.append(f"Reference changed or hash invalid: {key}")
        if key in PINNED_PLANNING_KEYS and approved_assets.get(path_text) != digest:
            blockers.append(f"Planning input is not the approved version: {key}")

    for key in sorted(required_reference_keys - checked_by_key.keys()):
        impacted = sorted(
            rule["rule_id"] for rule in applicable if key in rule.get("reference_keys", [])
        )
        affected_rules[key] = impacted
        blockers.append(f"Required reference missing: {key}; affects {', '.join(impacted)}")

    results = assessment.get("results", [])
    if not isinstance(results, list):
        blockers.append("results must be an array")
        results = []
    by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            blockers.append("Every result must be an object")
            continue
        rule_id = result.get("rule_id")
        if rule_id in by_id:
            duplicate_ids.add(str(rule_id))
        elif nonempty(rule_id):
            by_id[rule_id] = result
        else:
            blockers.append("A result has no rule_id")
    if duplicate_ids:
        blockers.append("Duplicate assessment rules: " + ", ".join(sorted(duplicate_ids)))
    expected_ids = set(rule_by_id)
    actual_ids = set(by_id)
    if expected_ids - actual_ids:
        blockers.append("Missing phase rules: " + ", ".join(sorted(expected_ids - actual_ids)))
    if actual_ids - expected_ids:
        blockers.append("Unknown or non-phase rules: " + ", ".join(sorted(actual_ids - expected_ids)))

    try:
        records = source_records(root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        blockers.append(f"Source registry unavailable or invalid: {error}")
        records = {}
    # The approved complete procedural source owns this mapping. A historical
    # extract may remain readable but must not silently regain authority here.
    if "PROCEDURAL_GUIDE" in required_reference_keys:
        procedural = records.get("REF-PROCEDURAL-FULL-1446", {})
        original_path = repository_file(procedural.get("reference_path"), root)
        if (not procedural or procedural.get("coverage") != "full"
                or procedural.get("governing") is not True or original_path is None
                or procedural.get("status") != "current_user_approved"
                or reference_catalog.get("PROCEDURAL_GUIDE") != procedural.get("reference_path")
                or procedural.get("sha256") != sha256(original_path)):
            blockers.append("PROCEDURAL_GUIDE must use the registered complete approved original")
    required_result_fields = set(ruleset.get("evidence_contract", {}).get("required_fields", []))
    allowed_information_statuses = set(ruleset.get("information_statuses", []))

    for rule_id, rule in rule_by_id.items():
        result = by_id.get(rule_id)
        if result is None:
            failed.append(rule_id)
            continue
        rule_errors: list[str] = []
        allowed_result_fields = required_result_fields | {
            "level",
            "escalation_reason",
            "applicability_reason",
            "scope",
        }
        unexpected_result_fields = sorted(set(result) - allowed_result_fields)
        if unexpected_result_fields:
            rule_errors.append("unknown fields: " + ", ".join(unexpected_result_fields))
        missing = sorted(required_result_fields - result.keys())
        if missing:
            rule_errors.append("missing fields: " + ", ".join(missing))
        if result.get("phase") != phase:
            rule_errors.append("result phase mismatch")
        state = result.get("result")
        if state not in RESULTS:
            rule_errors.append("unknown result state")
        info_status = result.get("information_status")
        if info_status not in allowed_information_statuses:
            rule_errors.append("unknown information status")
        for field in ("evidence_type", "claim", "reviewed_by"):
            if not nonempty(result.get(field)):
                rule_errors.append(f"{field} must be non-empty")
        if not valid_datetime(result.get("reviewed_at")):
            rule_errors.append("reviewed_at must be an ISO date-time")
        locator = result.get("locator")
        location_check = inspect_locator(locator, root, records)
        locator_checks[rule_id] = location_check
        if location_check["location_status"] == "INVALID":
            rule_errors.append(location_check["issue"])
        if state == "NOT_APPLICABLE":
            if info_status != "NOT_APPLICABLE":
                rule_errors.append("NOT_APPLICABLE result requires NOT_APPLICABLE information status")
            if not nonempty(result.get("applicability_reason")) or not nonempty(result.get("scope")):
                rule_errors.append("NOT_APPLICABLE requires applicability_reason and scope")
        if state == "NOT_ASSESSABLE_YET" and info_status != "NOT_ASSESSABLE_YET":
            rule_errors.append("NOT_ASSESSABLE_YET result requires matching information status")

        if rule_errors:
            blockers.append(f"{rule_id}: " + "; ".join(rule_errors))
            failed.append(rule_id)
            continue

        base_level = rule.get("review_level", "REVIEW")
        message = f"{rule_id}: {rule.get('message_if_failed', 'rule not satisfied')} - {result['claim']}"

        if location_check["location_status"] == "REVIEW_REQUIRED":
            failed.append(rule_id)
            review_message = f"{rule_id}: {location_check['issue']}"
            if base_level == "BLOCKER":
                blockers.append(review_message)
            else:
                human_reviews.append(review_message)
            continue

        if state == "PASS":
            if info_status in {"UNVERIFIED", "INFERENCE"}:
                if base_level == "BLOCKER":
                    blockers.append(f"{rule_id}: unresolved {base_level} cannot pass with {info_status}")
                    failed.append(rule_id)
                else:
                    human_reviews.append(f"{rule_id}: PASS relies on {info_status} - {result['claim']}")
                    failed.append(rule_id)
            elif info_status == "NOT_ASSESSABLE_YET":
                not_assessable.append(rule_id)
                pending_items.append(f"{rule_id}: not assessable in this phase")
            elif info_status in {"PENDING", "NOT_MEASURED"}:
                if info_status in set(rule.get("non_failure_statuses", [])):
                    passed.append(rule_id)
                    pending_items.append(f"{rule_id}: {info_status} - {result['claim']}")
                elif base_level == "BLOCKER":
                    blockers.append(f"{rule_id}: {info_status} is not allowed for this rule")
                    failed.append(rule_id)
                else:
                    human_reviews.append(f"{rule_id}: {info_status} needs review")
                    failed.append(rule_id)
            elif info_status == "NOT_APPLICABLE":
                blockers.append(f"{rule_id}: use NOT_APPLICABLE result for a non-applicable rule")
                failed.append(rule_id)
            else:
                passed.append(rule_id)
            continue

        if state == "NOT_APPLICABLE":
            not_applicable.append(rule_id)
            passed.append(rule_id)
            continue
        if state == "NOT_ASSESSABLE_YET":
            not_assessable.append(rule_id)
            pending_items.append(message)
            failed.append(rule_id)
            continue
        if state == "REVIEW":
            failed.append(rule_id)
            if base_level == "BLOCKER":
                blockers.append(f"{rule_id}: unresolved BLOCKER - {result['claim']}")
            else:
                human_reviews.append(message)
            continue

        level = result.get("level", base_level)
        if level not in LEVEL_ORDER:
            blockers.append(f"{rule_id}: invalid failure level")
            failed.append(rule_id)
            continue
        if LEVEL_ORDER[level] < LEVEL_ORDER.get(base_level, LEVEL_ORDER["REVIEW"]):
            blockers.append(f"{rule_id}: failure level cannot downgrade {base_level} to {level}")
            failed.append(rule_id)
            continue
        if level != base_level and not nonempty(result.get("escalation_reason")):
            blockers.append(f"{rule_id}: escalation to {level} requires escalation_reason")
            failed.append(rule_id)
            continue
        failed.append(rule_id)
        if level == "BLOCKER":
            blockers.append(message)
        elif level == "REVIEW":
            human_reviews.append(message)
        elif level == "WARNING":
            warnings.append(message)
        else:
            information.append(message)

    try:
        binding = result_binding(assessment, plan, ruleset, root, locator_checks)
    except (OSError, TypeError, ValueError):
        binding = {}
        blockers.append("Current inputs could not be fingerprinted consistently")

    if blockers:
        status = "BLOCKED"
    elif human_reviews:
        status = "HUMAN_REVIEW_REQUIRED"
    elif not_assessable:
        status = "NOT_READY_FOR_PHASE"
    elif warnings:
        status = "APPROVED_WITH_WARNINGS"
    else:
        status = "APPROVED"

    return {
        **binding,
        "gate_status": status,
        "gate_version": ruleset.get("gate_version"),
        "runner_version": RUNNER_VERSION,
        "schema_version": ruleset.get("schema_version"),
        "phase": phase,
        "gate_result_date": assessment.get("gate_result_date"),
        "checked_by": assessment.get("checked_by"),
        "plan_sha256": assessment.get("plan_sha256"),
        "references_checked": references,
        "blocking_issues": blockers,
        "human_reviews": human_reviews,
        "warnings": warnings,
        "information": information,
        "pending_items": pending_items,
        "passed_rules": sorted(set(passed)),
        "failed_rules": sorted(set(failed)),
        "not_applicable_rules": sorted(set(not_applicable)),
        "not_assessable_rules": sorted(set(not_assessable)),
        "affected_rules_by_reference": affected_rules,
        "locator_checks": locator_checks,
        "scope": "Phase-specific review; never proof of field execution or Noor save by itself.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--root", type=Path, default=LIB)
    parser.add_argument("--privacy-review", type=Path,
                        help="Optional content-bound review of a public-output false positive")
    args = parser.parse_args()

    try:
        assessment = load_json(args.assessment)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        assessment = {}
        try:
            ruleset = load_json(args.root / "standards/weekly_plan_gate_rules.yaml")
        except (OSError, ValueError, json.JSONDecodeError):
            ruleset = {}
        result = empty_result(ruleset, assessment, [f"Assessment unavailable or invalid: {error}"])
    else:
        result = evaluate(assessment, args.plan, root=args.root)

    # The command only publishes public Gate artifacts. Check free-text claims
    # before either a saved output or console export can copy them onward.
    try:
        try:
            from .privacy_guard import PrivacyReviewRequired, require_public_bytes
        except ImportError:
            from privacy_guard import PrivacyReviewRequired, require_public_bytes
    except ImportError:
        print(json.dumps({"status": "PUBLIC_OUTPUT_BLOCKED", "reason": "Privacy check unavailable"}))
        raise SystemExit(1)
    try:
        serialized = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        review = load_json(args.privacy_review) if args.privacy_review else None
        require_public_bytes(serialized, ".json", review=review)
    except PrivacyReviewRequired as error:
        print(json.dumps({"status": "PUBLIC_OUTPUT_BLOCKED", "findings": error.findings}, ensure_ascii=False))
        raise SystemExit(1)
    except (OSError, ValueError):
        print(json.dumps({"status": "PUBLIC_OUTPUT_BLOCKED", "reason": "Privacy check or review unavailable"}))
        raise SystemExit(1)
    if args.output:
        args.output.write_bytes(serialized)
    print(serialized.decode("utf-8"), end="")
    exit_code = 0 if result["gate_status"] in {"APPROVED", "APPROVED_WITH_WARNINGS"} else 2 if result["gate_status"] in {"HUMAN_REVIEW_REQUIRED", "NOT_READY_FOR_PHASE"} else 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
