"""Regression tests for record lifecycles, explicit update approval and live source links."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from . import check_work_register as work
    from . import check_weekly_plan_gate as gate
    from . import verify_library as library
except ImportError:
    import check_work_register as work
    import check_weekly_plan_gate as gate
    import verify_library as library

ROOT = work.ROOT


def register(*items: dict) -> dict:
    return {"schema_version": "1.1", "updated_at": "2026-10-02", "items": list(items)}


def incident(ident: str = "INC-001") -> dict:
    return {"work_id": ident, "type": "daily_incident", "title": "Neutral test event",
            "status": "recorded", "origin": {"kind": "user_input", "reference": "user_input:neutral-test"}}


def case(closed: bool = False) -> dict:
    item = {"work_id": "CASE-001", "type": "followup_case", "title": "Neutral test followup",
            "status": "closed" if closed else "active",
            "origin": {"kind": "diagnostic_action", "reference": "user_input:neutral-assessment"},
            "incident_refs": ["INC-001"],
            "followup_assessment": {"warrants_followup": True, "reason": "Explicit professional test assessment",
                                    "related_incident_ids": ["INC-001"]}}
    if closed:
        item["closure"] = {"reason": "Test completion", "result": "No further test action", "at": "2026-10-01"}
    return item


def action(needs_evidence: bool = True) -> dict:
    return {"work_id": "ACT-001", "type": "executive_action", "title": "Neutral test action",
            "status": "output_created", "origin": {"kind": "user_input", "reference": "user_input:neutral-action"},
            "requires_execution_cycle": True,
            "approval": {"required": True, "status": "approved", "reference": "DEC-012"},
            "output_refs": ["README.md"], "execution_status": "not_reported", "evidence_refs": [],
            "evidence_required_for_closure": needs_evidence}


def executed_action(needs_evidence: bool = True) -> dict:
    item = action(needs_evidence)
    item.update(status="executed", execution_status="executed",
                execution={"at": "2026-10-02", "summary": "Neutral simulated execution",
                           "input_ref": "user_input:neutral-execution"})
    return item


def receipt(proposal: dict) -> dict:
    return {"status": "approved", "approved_by": "user",
            "proposal_sha256": proposal["proposal_sha256"], "reference": "user_input:neutral-explicit-approval"}


class WorkRegisterTests(unittest.TestCase):
    def assertValid(self, data: dict, previous: dict | None = None) -> None:
        self.assertEqual(work.validate_register(data, previous=previous), [])

    def assertInvalid(self, data: dict, expected: str, previous: dict | None = None) -> None:
        self.assertTrue(any(expected in message for message in work.validate_register(data, previous=previous)))

    def test_public_register_rejects_identity_in_free_text(self) -> None:
        item = incident()
        item["title"] = "اسم الطالب: " + "طالب تجريبي اصطناعي"
        self.assertInvalid(register(item), "privacy")

    def test_public_register_rejects_indirect_identification(self) -> None:
        item = incident()
        item["next_action"] = "الطالب الوحيد في الصف الخامس الذي يسكن بجوار المدرسة وتعمل والدته فيها"
        self.assertInvalid(register(item), "privacy")

    def test_save_returns_bound_success_receipt_after_verified_write(self) -> None:
        before, after = register(), register(incident())
        proposal = work.propose_update(before, after, "Neutral audit test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            saved = work.save_approved_update(path, proposal, receipt(proposal))
            self.assertIsInstance(saved, dict)
            self.assertEqual(saved["status"], "saved")
            self.assertEqual(saved["before_sha256"], work.digest(before))
            self.assertEqual(saved["proposal_sha256"], proposal["proposal_sha256"])
            self.assertEqual(saved["result_sha256"], work.digest(work.load(path)))

    def test_old_approved_gate_cannot_survive_e01_fail(self) -> None:
        data = work.load(ROOT / "work/register.json")
        binding = data["items"][0]["gate"]
        assessment_path = (ROOT / binding["assessment_ref"]).resolve()
        assessment = work.load(assessment_path)
        next(row for row in assessment["results"] if row["rule_id"] == "E01")["result"] = "FAIL"
        original_load = work.load
        with mock.patch.object(work, "load", side_effect=lambda path: assessment if path.resolve() == assessment_path else original_load(path)):
            self.assertInvalid(data, "fresh Gate")

    def test_new_incident_stays_incident_and_does_not_open_case(self) -> None:
        before, after = register(), register(incident())
        proposal = work.propose_update(before, after, "Record user-provided neutral event")
        self.assertEqual(before["items"], [])
        self.assertEqual([item["type"] for item in proposal["after"]["items"]], ["daily_incident"])
        self.assertNotIn("approval", proposal["after"]["items"][0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            work.save_approved_update(path, proposal, receipt(proposal))
            self.assertEqual([item["type"] for item in work.load(path)["items"]], ["daily_incident"])

    def test_repeat_is_assessed_without_automatic_case(self) -> None:
        first, second = incident(), incident("INC-002")
        second["status"] = "diagnosing"
        second["followup_assessment"] = {"warrants_followup": False, "reason": "No followup warranted in test",
                                         "related_incident_ids": ["INC-001"]}
        data = register(first, second)
        self.assertValid(data)
        self.assertEqual(len(data["items"]), 2)
        self.assertFalse(any(item["type"] == "followup_case" for item in data["items"]))
        unwanted_case = case()
        unwanted_case["followup_assessment"]["warrants_followup"] = False
        self.assertInvalid(register(first, unwanted_case), "affirmative assessment")

    def test_case_opening_requires_linked_assessment(self) -> None:
        item = case()
        item.pop("followup_assessment")
        self.assertInvalid(register(incident(), item), "affirmative assessment")
        self.assertValid(register(incident(), case()))

    def test_case_keeps_original_incidents(self) -> None:
        self.assertInvalid(register(case()), "retain original daily incidents")

    def test_closed_case_new_information_remains_closed(self) -> None:
        before = register(incident(), case(True))
        after = copy.deepcopy(before)
        after["items"][1].update(
            information_refs=["user_input:neutral-new-information"],
            information_assessment={"new_information_ref": "user_input:neutral-new-information",
                                    "warrants_followup": False, "reason": "History reviewed; no followup in test"})
        proposal = work.propose_update(before, after, "Link evaluated new information")
        self.assertEqual(proposal["after"]["items"][1]["status"], "closed")
        self.assertEqual(before["items"][1]["status"], "closed")

    def test_closed_case_cannot_reopen_automatically(self) -> None:
        before = register(incident(), case(True))
        after = copy.deepcopy(before)
        after["items"][1]["status"] = "active"
        self.assertInvalid(after, "cannot reopen automatically", before)

    def test_reopening_is_proposed_with_reason_and_assessment(self) -> None:
        before = register(incident(), case(True))
        after = copy.deepcopy(before)
        item = after["items"][1]
        item.update(status="active", information_refs=["user_input:neutral-new-information"],
                    information_assessment={"new_information_ref": "user_input:neutral-new-information",
                                            "warrants_followup": True, "reason": "New need after history review"},
                    reopening={"at": "2026-10-02", "previous_closed_at": "2026-10-01",
                               "new_information_ref": "user_input:neutral-new-information", "reason": "New assessed need"})
        proposal = work.propose_update(before, after, "Propose reopening; await approval")
        self.assertEqual(before["items"][1]["status"], "closed")
        self.assertEqual(proposal["status"], "proposed")
        item["reopening"]["reason"] = ""
        self.assertInvalid(after, "reopening needs", before)

    def test_document_creation_is_not_execution(self) -> None:
        item = action()
        self.assertValid(register(item))
        self.assertEqual(item["execution_status"], "not_reported")
        item["execution_status"] = "executed"
        self.assertInvalid(register(item), "creating a document is not execution")

    def test_executed_action_needs_execution_information(self) -> None:
        item = action()
        item.update(status="executed", execution_status="executed")
        self.assertInvalid(register(item), "actual execution needs")
        self.assertValid(register(executed_action()))
        item = executed_action()
        item.update(status="output_created", execution_status="not_reported")
        self.assertInvalid(register(item), "contradicts non-executed status")

    def test_action_needing_evidence_cannot_close_without_it(self) -> None:
        item = executed_action()
        item.update(status="closed", closure={"reason": "Test end", "result": "Test result", "at": "2026-10-02"})
        self.assertInvalid(register(item), "closure requires evidence")
        item["evidence_refs"] = ["user_input:neutral-evidence-reference"]
        self.assertValid(register(item))

    def test_action_not_needing_evidence_can_close_without_it(self) -> None:
        item = executed_action(False)
        item.update(status="closed", closure={"reason": "Simple completed action", "result": "Test result", "at": "2026-10-02"})
        self.assertValid(register(item))
        self.assertEqual(item["evidence_refs"], [])

    def test_not_applicable_closure_requires_documented_basis(self) -> None:
        item = action()
        item.update(status="closed", execution_status="not_required",
                    closure={"reason": "No qualifying event", "result": "Not applicable", "at": "2026-10-02"})
        self.assertInvalid(register(item), "applicability basis")
        item["closure"]["proof_basis"] = {"kind": "not_applicable", "summary": "User confirmed no test event",
                                          "reference": "user_input:neutral-no-event"}
        self.assertValid(register(item))

    def test_closure_requires_reason_result_and_date(self) -> None:
        item = case(True)
        item["closure"].pop("result")
        self.assertInvalid(register(incident(), item), "closure needs")

    def test_required_approval_has_status_and_reference(self) -> None:
        item = action()
        item["approval"]["status"] = "pending"
        self.assertInvalid(register(item), "needs required approval")
        item["approval"].update(status="approved", reference="")
        self.assertInvalid(register(item), "approval reference")

    def test_simple_action_does_not_require_its_own_execution_approval(self) -> None:
        item = action(False)
        item["requires_execution_cycle"] = False
        item["approval"] = {"required": False, "status": "not_required"}
        self.assertValid(register(item))

    def test_invalid_ids_types_states_and_background_origin_are_rejected(self) -> None:
        for field, value, expected in [
            ("work_id", "", "invalid work_id"),
            ("type", "background_detected_event", "unknown record type"),
            ("status", "executed", "invalid status"),
            ("executed", True, "unknown fields"),
        ]:
            item = incident()
            item[field] = value
            self.assertInvalid(register(item), expected)
        item = incident()
        item["origin"]["kind"] = "background_monitor"
        self.assertInvalid(register(item), "authorized origin")

    def test_original_records_cannot_be_dropped_or_converted(self) -> None:
        before = register(incident())
        self.assertInvalid(register(), "discard original records", before)
        after = register(case())
        after["items"][0]["work_id"] = "INC-001"
        self.assertInvalid(after, "cannot convert", before)

    def test_malformed_record_fields_fail_closed(self) -> None:
        for field, value in [("type", []), ("status", []), ("information_refs", [{}])]:
            item = incident()
            item[field] = value
            self.assertTrue(work.validate_register(register(item)))
        item = action()
        item["approval"]["status"] = []
        self.assertTrue(work.validate_register(register(item)))

    def test_update_never_saves_without_exact_user_approval(self) -> None:
        before, after = register(), register(incident())
        proposal = work.propose_update(before, after, "Neutral proposed update")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            original = path.read_bytes()
            for approval in [{}, {"status": "approved"}, {**receipt(proposal), "proposal_sha256": "wrong"}]:
                with self.assertRaises(ValueError):
                    work.save_approved_update(path, proposal, approval)
                self.assertEqual(path.read_bytes(), original)

    def test_changed_proposal_and_stale_register_cannot_save(self) -> None:
        before, after = register(), register(incident())
        proposal = work.propose_update(before, after, "Neutral proposed update")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "register.json"
            path.write_text(json.dumps(before), encoding="utf-8")
            altered = copy.deepcopy(proposal)
            altered["after"]["items"][0]["title"] = "Different proposed update"
            with self.assertRaises(ValueError):
                work.save_approved_update(path, altered, receipt(proposal))
            path.write_text(json.dumps(after), encoding="utf-8")
            with self.assertRaises(ValueError):
                work.save_approved_update(path, proposal, receipt(proposal))

    def test_actual_work001_is_approved_ready_and_unexecuted(self) -> None:
        data = work.load(ROOT / "work/register.json")
        self.assertValid(data)
        item = data["items"][0]
        self.assertEqual(item["work_id"], "WORK-001")
        self.assertEqual(item["approval"]["status"], "approved")
        self.assertEqual(item["approval"]["reference"], "DEC-014")
        self.assertEqual(item["status"], "ready_for_execution")
        self.assertEqual(item["execution_status"], "not_reported")
        self.assertEqual(item["evidence_refs"], [])

    def test_stale_gate_blocks_readiness_without_revoking_content_approval(self) -> None:
        data = work.load(ROOT / "work/register.json")
        data["items"][0]["gate"]["plan_sha256"] = "0" * 64
        self.assertInvalid(data, "Gate must match")
        self.assertEqual(data["items"][0]["approval"]["status"], "approved")

    def test_current_gate_result_matches_actual_evaluation_and_plan_hash(self) -> None:
        binding = work.load(ROOT / "work/register.json")["items"][0]["gate"]
        assessment = work.load(ROOT / binding["assessment_ref"])
        result = work.load(ROOT / binding["result_ref"])
        plan = ROOT / binding["plan_ref"]
        self.assertEqual(gate.evaluate(assessment, plan), result)
        self.assertEqual(result["plan_sha256"], gate.sha256(plan))


class NoorAndCurrentnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = library.load("catalog/records_noor_decision_matrix.json")
        self.registry = library.load("catalog/source_registry.json")

    def test_all_31_paths_and_5_source_ids_resolve(self) -> None:
        self.assertEqual(len(self.matrix["records"]), 31)
        self.assertEqual(len(self.matrix["sources"]), 5)
        self.assertEqual(library.validate_noor_matrix(self.matrix, self.registry), [])
        self.assertTrue(all(not item["source_id"].startswith("SRC-") for item in self.matrix["sources"]))

    def test_unknown_source_id_is_rejected(self) -> None:
        self.matrix["sources"][0]["source_id"] = "SRC-NONEXISTENT"
        self.assertTrue(library.validate_noor_matrix(self.matrix, self.registry))
        self.matrix["sources"][0]["source_id"] = "REF-RECORDS-ZIP"
        self.matrix["records"][0]["source_refs"] = ["REF-NONEXISTENT"]
        self.assertTrue(library.validate_noor_matrix(self.matrix, self.registry))

    def test_missing_and_escaped_paths_are_rejected(self) -> None:
        for value in ["references/missing-neutral-template.docx", "../outside.docx"]:
            self.matrix["records"][0]["original_path"] = value
            self.assertTrue(library.validate_noor_matrix(self.matrix, self.registry))
        self.matrix = library.load("catalog/records_noor_decision_matrix.json")
        self.matrix["current_context_path"] = "context/nonexistent.json"
        self.assertTrue(library.validate_noor_matrix(self.matrix, self.registry))

    def test_currentness_is_user_approved_without_date_only_downgrades(self) -> None:
        self.assertEqual(self.registry["currentness_policy"],
                         {"status": "current_user_approved", "decision_ref": "DEC-015"})
        for item in self.registry["sources"]:
            self.assertNotIn("requires_latest_check", item["status"])
            self.assertNotEqual(item["status"], "requires_verification_of_currentness")
        historical = next(s for s in self.registry["sources"] if s["source_id"] == "REF-HISTORICAL-BEHAVIOR")
        self.assertEqual(historical["status"], "recognized_by_qassim_plan_1448")
        self.assertIn("Current", historical["currentness_note"])
        self.assertNotIn("أحدث", historical["warning"])

    def test_qassim_visual_report_is_not_transferred_between_binary_versions(self) -> None:
        source = next(s for s in self.registry["sources"] if s["source_id"] == "REF-QASSIM-1448")
        visual = source["visual_verification"]
        self.assertEqual(visual["status"], "report_link_unresolved")
        self.assertNotEqual(source["sha256"], visual["verified_version_sha256"])
        self.assertTrue((ROOT / visual["report_ref"]).is_file())
        self.assertEqual(source["text_status"], "needs_ocr")


if __name__ == "__main__":
    unittest.main()
