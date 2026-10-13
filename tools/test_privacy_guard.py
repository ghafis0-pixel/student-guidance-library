"""Synthetic privacy, explicit export-scope and failure-safe approval regressions."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

try:
    from . import privacy_guard as privacy
    from . import build_delivery as delivery
    from . import check_work_register as work
except ImportError:
    import privacy_guard as privacy
    import build_delivery as delivery
    import check_work_register as work


def reviewed(content: bytes, suffix: str) -> dict:
    return {"guard_version": privacy.VERSION, "decision": "cleared", "content_sha256": hashlib.sha256(content).hexdigest(),
            "findings_sha256": privacy.fingerprint(privacy.scan_bytes(content, suffix)),
            "reference": "user_input:synthetic-fixture-review", "reason": "Synthetic neutral fixture inspected in this test"}


def prepared() -> tuple[dict, dict, dict, dict]:
    before = {"schema_version": "1.1", "updated_at": "2026-10-04", "items": []}
    after = copy.deepcopy(before)
    after["items"].append({"work_id": "INC-001", "type": "daily_incident", "status": "recorded",
                           "title": "Neutral synthetic event", "origin": {"kind": "user_input", "reference": "user_input:synthetic"}})
    proposal = work.propose_update(before, after, "Synthetic exact proposal")
    approval = {"status": "approved", "approved_by": "user", "proposal_sha256": proposal["proposal_sha256"],
                "reference": "user_input:synthetic-explicit-approval"}
    return before, after, proposal, approval


class PrivacyTests(unittest.TestCase):
    def test_authorized_initials_are_pseudonymous_not_a_violation(self) -> None:
        data = {"student_initials": "أ. ب.", "grade": "5", "case_details": "تفاصيل اصطناعية"}
        self.assertEqual(privacy.scan_data(data, audience="restricted", authorization_ref="user_input:authorized-private-home"), [])
        self.assertTrue(privacy.scan_data(data, audience="restricted"))
        self.assertTrue(privacy.scan_data(data))

    def test_initials_alone_are_not_automatically_rejected_publicly(self) -> None:
        self.assertEqual(privacy.scan_data({"initials": "أ. ب."}), [])

    def test_identical_initials_cannot_merge_students(self) -> None:
        records = [{"internal_student_key": "synthetic-1", "initials": "أ. ب."},
                   {"internal_student_key": "synthetic-2", "initials": "أ. ب."}]
        self.assertIs(privacy.resolve_internal_student(records, "synthetic-1"), records[0])
        self.assertIs(privacy.resolve_internal_student(records, "synthetic-2"), records[1])
        for value in ("أ. ب.", "", "unknown-key"):
            with self.assertRaises(ValueError):
                privacy.resolve_internal_student(records, value)
        self.assertEqual(len(records), 2)

    def test_ambiguous_internal_key_cannot_be_guessed(self) -> None:
        with self.assertRaises(ValueError):
            privacy.resolve_internal_student([{"internal_student_key": "synthetic"}, {"internal_student_key": "synthetic"}], "synthetic")

    def test_direct_synthetic_identity_is_blocked_in_deep_free_text(self) -> None:
        content = {"items": [{"notes": "اسم الطالب: " + "شخص تجريبي اصطناعي"}]}
        findings = privacy.scan_data(content)
        self.assertTrue(any(f["code"] == "DIRECT_IDENTITY_LABEL" for f in findings))
        self.assertNotIn("شخص", json.dumps(findings, ensure_ascii=False))

    def test_direct_identity_fields_and_contact_numbers_are_blocked(self) -> None:
        self.assertTrue(privacy.scan_data({"student_name": "Synthetic example"}))
        self.assertTrue(privacy.scan_data({"notes": "05" + "12345678"}))
        self.assertTrue(privacy.scan_data({"notes": "١٠" + "١٢٣٤٥٦٧٨"}))

    def test_indirect_synthetic_identity_combination_is_blocked(self) -> None:
        self.assertTrue(privacy.scan_data({"grade": "5", "school": "synthetic", "diagnosis": "synthetic"}))
        self.assertTrue(privacy.scan_data("الطالب الوحيد في الصف الخامس الذي تسكن أسرته بجانب المدرسة"))

    def test_empty_templates_are_allowed(self) -> None:
        self.assertEqual(privacy.scan_data({"student_name": "", "phone": None, "home_address": "........"}), [])
        self.assertEqual(privacy.scan_data("اسم الطالب: ........\nرقم الجوال: __________"), [])

    def test_general_policy_and_school_context_are_not_case_identity(self) -> None:
        self.assertEqual(privacy.scan_data("لا تُعرض أسماء الطلاب؛ تحفظ تفاصيل الحالات في موطنها المصرح. تستخدم الأحرف الأولى دون توسيعها."), [])
        self.assertEqual(privacy.scan_data({"school": "مدرسة تجريبية", "grade": "2-6", "student_count": 140}), [])

    def test_valid_fingerprint_key_is_not_a_contact_number(self) -> None:
        value = "a" * 20 + "05" + "12345678" + "b" * 34
        self.assertEqual(len(value), 64)
        self.assertEqual(privacy.scan_data({"text_sha256": value}), [])
        self.assertTrue(privacy.scan_data({"notes": "05" + "12345678"}))
        self.assertTrue(privacy.scan_data({"text_sha256": "05" + "12345678"}))

    def test_untrusted_object_key_does_not_leak_in_finding(self) -> None:
        key = "اسم الطالب: " + "شخص اصطناعي"
        findings = privacy.scan_data({key: ""})
        self.assertTrue(findings)
        self.assertNotIn("شخص", json.dumps(findings, ensure_ascii=False))

    def test_review_must_match_exact_bytes_findings_and_guard_version(self) -> None:
        content = b"synthetic neutral binary"
        review = reviewed(content, ".bin")
        self.assertEqual(privacy.require_public_bytes(content, ".bin", review)["status"], "REVIEWED")
        for field in ("content_sha256", "findings_sha256", "guard_version", "reference", "reason"):
            changed = {**review, field: ""}
            with self.assertRaises(privacy.PrivacyReviewRequired):
                privacy.require_public_bytes(content, ".bin", changed)
        with self.assertRaises(privacy.PrivacyReviewRequired):
            privacy.require_public_bytes(content + b"changed", ".bin", review)

    def test_invalid_json_and_unknown_binary_require_review(self) -> None:
        for content, suffix in ((b"{broken", ".json"), (b"binary", ".pdf"), (b"\xff", ".txt")):
            with self.assertRaises(privacy.PrivacyReviewRequired):
                privacy.require_public_bytes(content, suffix)


class AuditTests(unittest.TestCase):
    def test_restricted_initials_persist_only_to_bound_authorized_home(self) -> None:
        before, after, _, _ = prepared()
        after["items"][0]["title"] = "أ. ب. في الصف الخامس؛ تفاصيل اصطناعية لازمة للمتابعة"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            options = {"audience": "restricted", "authorization_ref": "user_input:authorized-synthetic-home", "restricted_home": home}
            proposal = work.propose_update(before, after, "Restricted synthetic update", destination=path, **options)
            approval = {"status": "approved", "approved_by": "user", "proposal_sha256": proposal["proposal_sha256"],
                        "reference": "user_input:synthetic-explicit-approval"}
            saved = work.save_approved_update(path, proposal, approval, **options)
            self.assertEqual(saved["status"], "saved")
            self.assertEqual(saved["audience"], "restricted")
            self.assertEqual(work.load(path), after)
            self.assertNotIn("أ. ب.", path.with_name("register.json.audit.jsonl").read_text(encoding="utf-8"))

    def test_restricted_proposal_cannot_redirect_or_reuse_as_public(self) -> None:
        before, after, _, _ = prepared()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path, other = home / "register.json", home / "other.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            other.write_text(json.dumps(before), encoding="utf-8")
            options = {"audience": "restricted", "authorization_ref": "user_input:authorized-synthetic-home", "restricted_home": home}
            proposal = work.propose_update(before, after, "Restricted synthetic update", destination=path, **options)
            approval = {"status": "approved", "approved_by": "user", "proposal_sha256": proposal["proposal_sha256"],
                        "reference": "user_input:synthetic-explicit-approval"}
            for target, arguments in ((path, {}), (other, options), (path, {**options, "authorization_ref": "user_input:different"})):
                with self.assertRaises(ValueError):
                    work.save_approved_update(target, proposal, approval, **arguments)
            self.assertEqual(work.load(path), before)
            self.assertEqual(work.load(other), before)

    def test_restricted_destination_inside_public_root_or_git_is_rejected(self) -> None:
        before, after, _, _ = prepared()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for root in (home, work.ROOT):
                if root == work.ROOT:
                    (home / ".git").mkdir()
                with self.assertRaises(ValueError):
                    work.propose_update(before, after, "Restricted synthetic update", root=root,
                                        audience="restricted", authorization_ref="user_input:authorized-synthetic-home",
                                        restricted_home=home, destination=home / "register.json")

    def test_restricted_audit_cannot_leave_authorized_home(self) -> None:
        before, after, _, _ = prepared()
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as another:
            home, path = Path(directory), Path(directory) / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            options = {"audience": "restricted", "authorization_ref": "user_input:authorized-synthetic-home", "restricted_home": home}
            proposal = work.propose_update(before, after, "Restricted synthetic update", destination=path, **options)
            approval = {"status": "approved", "approved_by": "user", "proposal_sha256": proposal["proposal_sha256"],
                        "reference": "user_input:synthetic-explicit-approval"}
            with self.assertRaises(ValueError):
                work.save_approved_update(path, proposal, approval, audit_path=Path(another) / "audit.jsonl", **options)
            self.assertEqual(work.load(path), before)

    def test_success_journal_contains_bound_hashes_without_payload(self) -> None:
        before, after, proposal, approval = prepared()
        with tempfile.TemporaryDirectory() as directory:
            path, audit = Path(directory) / "register.json", Path(directory) / "audit.jsonl"
            path.write_text(json.dumps(before), encoding="utf-8")
            receipt = work.save_approved_update(path, proposal, approval, audit_path=audit)
            rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["status"] for row in rows], ["prepared", "saved"])
            self.assertEqual(receipt, rows[-1])
            self.assertEqual(receipt["before_sha256"], work.digest(before))
            self.assertEqual(receipt["proposal_sha256"], proposal["proposal_sha256"])
            self.assertEqual(receipt["result_sha256"], work.digest(after))
            self.assertEqual(receipt["approval_ref"], approval["reference"])
            self.assertNotIn("Neutral synthetic event", audit.read_text(encoding="utf-8"))

    def test_write_failure_never_emits_success_receipt(self) -> None:
        before, _, proposal, approval = prepared()
        with tempfile.TemporaryDirectory() as directory:
            path, audit = Path(directory) / "register.json", Path(directory) / "audit.jsonl"
            path.write_text(json.dumps(before), encoding="utf-8")
            with mock.patch.object(Path, "replace", side_effect=OSError("synthetic disk failure")):
                with self.assertRaises(OSError):
                    work.save_approved_update(path, proposal, approval, audit_path=audit)
            self.assertEqual(work.load(path), before)
            rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
            self.assertNotIn("saved", [row["status"] for row in rows])
            self.assertEqual(rows[-1]["status"], "failed_before_persistence")
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_audit_preflight_failure_does_not_change_state(self) -> None:
        before, _, proposal, approval = prepared()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            with mock.patch.object(work, "_append_audit", side_effect=OSError("synthetic failure")):
                with self.assertRaises(OSError):
                    work.save_approved_update(path, proposal, approval)
            self.assertEqual(work.load(path), before)

    def test_post_write_audit_failure_reports_uncertainty_not_success(self) -> None:
        before, after, proposal, approval = prepared()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            original, calls = work._append_audit, []
            def append(audit: Path, entry: dict) -> None:
                calls.append(entry["status"])
                if entry["status"] == "saved":
                    raise OSError("synthetic journal failure")
                original(audit, entry)
            with mock.patch.object(work, "_append_audit", side_effect=append):
                with self.assertRaisesRegex(RuntimeError, "state persisted"):
                    work.save_approved_update(path, proposal, approval)
            self.assertEqual(work.load(path), after)
            rows = [json.loads(line) for line in path.with_name(path.name + ".audit.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertNotIn("saved", [row["status"] for row in rows])
            self.assertEqual(rows[-1]["status"], "state_persisted_audit_unconfirmed")

    def test_rehashed_changed_proposal_cannot_use_previous_approval(self) -> None:
        before, _, proposal, approval = prepared()
        proposal["after"]["items"][0]["title"] = "Changed exact proposal"
        proposal["proposal_sha256"] = work.digest({key: proposal[key] for key in ("before_sha256", "after", "summary")})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact proposal"):
                work.save_approved_update(path, proposal, approval)
            self.assertEqual(work.load(path), before)


class DeliveryTests(unittest.TestCase):
    def test_actual_archive_contains_only_explicit_scanned_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.txt").write_text("General guidance only", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__/ignored.pyc").write_bytes(b"generated")
            (root / "private.txt").write_text("not selected", encoding="utf-8")
            archive = root / "delivery.zip"
            result = delivery.build_delivery(root, ["safe.txt"], archive)
            self.assertEqual(result["file_count"], 1)
            self.assertEqual(result, delivery.verify_delivery(archive))
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(set(package.namelist()), {"safe.txt", delivery.MANIFEST_NAME})

    def test_cache_temp_path_traversal_and_directory_scope_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ("__pycache__/a.pyc", "anything.tmp", "../outside.txt", "tmp/a.txt", "private/a.txt", "."):
                with self.assertRaises(ValueError):
                    delivery.build_delivery(root, [path], root / "out.zip")

    def test_public_leak_prevents_archive_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "unsafe.json").write_text(json.dumps({"student_name": "Synthetic identity"}), encoding="utf-8")
            archive = root / "delivery.zip"
            with self.assertRaises(privacy.PrivacyReviewRequired):
                delivery.build_delivery(root, ["unsafe.json"], archive)
            self.assertFalse(archive.exists())

    def test_binary_needs_exact_review_then_actual_archive_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b"synthetic neutral binary"
            (root / "safe.bin").write_bytes(content)
            archive = root / "delivery.zip"
            with self.assertRaises(privacy.PrivacyReviewRequired):
                delivery.build_delivery(root, ["safe.bin"], archive)
            delivery.build_delivery(root, ["safe.bin"], archive, {"safe.bin": reviewed(content, ".bin")})
            self.assertEqual(delivery.verify_delivery(archive)["file_count"], 1)

    def test_added_member_invalidates_archive_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.txt").write_text("General text", encoding="utf-8")
            archive = root / "delivery.zip"
            delivery.build_delivery(root, ["safe.txt"], archive)
            with zipfile.ZipFile(archive, "a") as package:
                package.writestr("__pycache__/extra.pyc", b"unapproved")
            with self.assertRaisesRegex(ValueError, "scope"):
                delivery.verify_delivery(archive)


if __name__ == "__main__":
    unittest.main()
