"""Conservative public-output guard. Findings contain locations/codes, never excerpts.

This is a review aid, not an anonymization guarantee or a detector of every name.
Restricted access is an explicit authorization argument, not a directory-name guess.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

VERSION = "1.0.0"
TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".jsonl", ".yaml", ".yml", ".csv", ".tsv", ".toml", ".html", ".css", ".js"}
EMPTY = {"", "-", "—", "n/a", "null", "none", "غير مذكور", "غير متاح", "فارغ"}
DIRECT_KEYS = {"student_name", "full_name", "guardian_name", "national_id", "civil_id", "phone", "mobile", "email", "home_address", "اسم الطالب", "اسم ولي الأمر", "رقم الهوية", "رقم الجوال", "عنوان السكن"}
INITIAL_KEYS = {"initials", "student_initials", "أحرف الطالب", "الأحرف الأولى"}
QUASI_KEYS = {"grade", "class", "section", "school", "neighborhood", "parent_job", "sibling", "الصف", "الفصل", "المدرسة", "الحي", "عمل الأب", "عمل الأم"}
SENSITIVE_KEYS = {"diagnosis", "medical_condition", "case_details", "family_details", "attendance_history", "التشخيص", "تفاصيل الحالة", "تفاصيل الأسرة"}
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
INITIALS = re.compile(r"(?<![\w])(?:[ء-ي]\s*[.،·]\s*[ء-ي]\.?)(?![\w])")
DIRECT_LABEL = re.compile(r"(?:اسم\s+(?:الطالب|ولي\s+الأمر)|student\s+name|full\s+name|رقم\s+(?:الهوية|الجوال)|عنوان\s+السكن)\s*[:：=]\s*([^\n\r|]+)", re.I)
EMAIL = re.compile(r"(?<![\w])[^\s@]+@[^\s@]+\.[A-Za-z]{2,}(?![\w])")
PHONE = re.compile(r"(?<!\d)(?:(?:\+?966|00966)[ -]?5\d{8}|05\d{8})(?!\d)")
NATIONAL_ID = re.compile(r"(?<![\w])[12]\d{9}(?![\w])")
CASE_MARKER = re.compile(r"تشخيص|حالة\s+صحية|غياب(?:ه|ها)?\s+\d|والد(?:ه|ته)|والدت(?:ه|ها)|أسر(?:ته|تها)|يسكن|تسكن|diagnos|medical|family", re.I)
QUASI_MARKER = re.compile(r"الصف\s+(?:الثاني|الثالث|الرابع|الخامس|السادس|\d)|فصل\s+\d|حي\s+\S+|مدرسة\s+\S+|grade\s+\d|class\s+\d", re.I)
UNIQUE_MARKER = re.compile(r"(?:الطالب|الطالبة)\s+الوحيد(?:ة)?|only\s+(?:student|pupil)", re.I)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def nonempty(value: Any) -> bool:
    if value is None or value == [] or value == {}:
        return False
    if isinstance(value, str):
        stripped = value.strip().lower()
        return stripped not in EMPTY and bool(re.sub(r"[\s_.…\-—\[\](){}:/\\]", "", stripped))
    return True


def _location(parent: str, key: Any, index: int) -> str:
    # Arbitrary object keys can themselves contain identities. Only safe field labels are shown.
    safe = str(key) if isinstance(key, str) and re.fullmatch(r"[a-z_][a-z0-9_]{0,47}", key) else f"field#{index}"
    return f"{parent}.{safe}"


def scan_data(value: Any, *, audience: str = "public", authorization_ref: str | None = None) -> list[dict[str, str]]:
    """Recursively inspect values, including free text; return blocking review findings.

    Initials alone are not automatically a violation. Their combination with individual
    case/identifying details requires public review. Authorized restricted use is permitted.
    """
    if audience not in {"public", "restricted"}:
        raise ValueError("audience must be public or restricted")
    if audience == "restricted":
        if not isinstance(authorization_ref, str) or not authorization_ref.strip():
            return [{"location": "$", "code": "RESTRICTED_AUTHORIZATION_REQUIRED"}]
        return []
    findings: list[dict[str, str]] = []

    def flag(location: str, code: str) -> None:
        item = {"location": location, "code": code}
        if item not in findings:
            findings.append(item)

    def inspect_text(content: str, location: str) -> None:
        for number, line in enumerate(content.translate(DIGITS).splitlines() or [content], 1):
            position = f"{location}:line:{number}"
            for pattern, code in ((PHONE, "CONTACT_NUMBER"), (NATIONAL_ID, "IDENTITY_NUMBER"), (EMAIL, "EMAIL_ADDRESS")):
                if pattern.search(line):
                    flag(position, code)
            if any(nonempty(match.group(1)) for match in DIRECT_LABEL.finditer(line)):
                flag(position, "DIRECT_IDENTITY_LABEL")
            if UNIQUE_MARKER.search(line) and (CASE_MARKER.search(line) or QUASI_MARKER.search(line)):
                flag(position, "INDIRECT_UNIQUE_STUDENT")
            if INITIALS.search(line) and (CASE_MARKER.search(line) or QUASI_MARKER.search(line)):
                flag(position, "INITIALS_WITH_IDENTIFYING_CONTEXT")

    def walk(node: Any, location: str) -> None:
        if isinstance(node, dict):
            populated = {str(key) for key, child in node.items() if nonempty(child)}
            if populated & INITIAL_KEYS and populated & (QUASI_KEYS | SENSITIVE_KEYS):
                flag(location, "INITIALS_WITH_IDENTIFYING_CONTEXT")
            if len(populated & QUASI_KEYS) >= 2 and populated & SENSITIVE_KEYS:
                flag(location, "INDIRECT_IDENTITY_COMBINATION")
            for index, (key, child) in enumerate(node.items()):
                position = _location(location, key, index)
                if str(key) in DIRECT_KEYS and nonempty(child):
                    flag(position, "DIRECT_IDENTITY_FIELD")
                # Free-text keys are inspected too, without echoing them in a diagnostic.
                if isinstance(key, str):
                    inspect_text(key, f"{location}.key#{index}")
                if (isinstance(key, str) and (key == "sha256" or key.endswith("_sha256"))
                        and isinstance(child, str) and re.fullmatch(r"[0-9a-fA-F]{64}", child)):
                    continue
                walk(child, position)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{location}[{index}]")
        elif isinstance(node, str):
            inspect_text(node, location)

    walk(value, "$")
    return findings


def scan_bytes(data: bytes, suffix: str) -> list[dict[str, str]]:
    if suffix.lower() not in TEXT_SUFFIXES:
        return [{"location": "$", "code": "UNSUPPORTED_FORMAT_REQUIRES_REVIEW"}]
    try:
        content = data.decode("utf-8-sig")
    except UnicodeError:
        return [{"location": "$", "code": "UNREADABLE_TEXT_REQUIRES_REVIEW"}]
    if suffix.lower() == ".json":
        try:
            return scan_data(json.loads(content))
        except (ValueError, TypeError):
            return [{"location": "$", "code": "INVALID_JSON_REQUIRES_REVIEW"}]
    if suffix.lower() == ".jsonl":
        findings = []
        for number, line in enumerate(content.splitlines(), 1):
            if not line.strip():
                continue
            try:
                findings.extend({**finding, "location": f"line:{number}:{finding['location']}"} for finding in scan_data(json.loads(line)))
            except (ValueError, TypeError):
                findings.append({"location": f"line:{number}", "code": "INVALID_JSON_REQUIRES_REVIEW"})
        return findings
    return scan_data(content)


class PrivacyReviewRequired(ValueError):
    """Only structural locations and finding codes are safe to log."""

    def __init__(self, findings: list[dict[str, str]]) -> None:
        self.findings = findings
        super().__init__("privacy review required: " + json.dumps(findings, ensure_ascii=False))


def require_public_bytes(data: bytes, suffix: str, review: dict | None = None) -> dict:
    """Block unless clean or a documented review resolves this exact byte/finding set.

    Review does not imply user approval of operational content. Its reference must point
    to the actual scoped review; a fingerprint cannot authenticate its author.
    """
    findings = scan_bytes(data, suffix)
    content_hash = hashlib.sha256(data).hexdigest()
    finding_hash = fingerprint(findings)
    result = {"guard_version": VERSION, "content_sha256": content_hash,
              "findings_sha256": finding_hash, "status": "PASS_WITH_LIMITS"}
    if not findings:
        return result
    if not isinstance(review, dict) or not (
        review.get("guard_version") == VERSION and review.get("decision") == "cleared"
        and review.get("content_sha256") == content_hash
        and review.get("findings_sha256") == finding_hash
        and isinstance(review.get("reference"), str) and review["reference"].strip()
        and isinstance(review.get("reason"), str) and review["reason"].strip()
    ):
        raise PrivacyReviewRequired(findings)
    if scan_data({"reference": review["reference"], "reason": review["reason"]}):
        raise PrivacyReviewRequired([{"location": "$.review", "code": "REVIEW_METADATA_REQUIRES_PRIVATE_LOCATION"}])
    return {**result, "status": "REVIEWED", "review_ref": review["reference"]}


def resolve_internal_student(records: list[dict], internal_key: str) -> dict:
    """Look up the authorized internal key only; initials are never a join key."""
    if not isinstance(internal_key, str) or not internal_key.strip():
        raise ValueError("authorized internal student key required; initials cannot resolve identity")
    matched = [record for record in records if record.get("internal_student_key") == internal_key]
    if len(matched) != 1:
        raise ValueError("internal student key is missing or ambiguous; do not infer from initials")
    return matched[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    findings = scan_bytes(args.path.read_bytes(), args.path.suffix)
    print(json.dumps({"guard_version": VERSION, "status": "REVIEW_REQUIRED" if findings else "PASS_WITH_LIMITS", "findings": findings}, ensure_ascii=False, indent=2))
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
