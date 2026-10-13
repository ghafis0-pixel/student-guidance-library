from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import check_weekly_plan_gate as gate
except ImportError:
    import check_weekly_plan_gate as gate

LIB, evaluate = gate.LIB, gate.evaluate


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = LIB / "outputs/weekly_plans/2026-10-04_to_2026-10-08/weekly_plan_2026-10-04_adhd.docx"
        self.ruleset = json.loads(
            (LIB / "standards/weekly_plan_gate_rules.yaml").read_text(encoding="utf-8")
        )
        self.rules = self.ruleset["rule_definitions"]
        self.locator = {
            "path": "reports/master_review_2026-09-29/MASTER_REVIEW.md",
            "section": "D. مراجعة WEEKLY_PLAN_GATE قاعدةً قاعدة",
        }

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def applicable(self, phase: str) -> list[dict]:
        return [rule for rule in self.rules if phase in rule["phases"]]

    def reference_checks(self, phase: str) -> list[dict]:
        keys = {
            key
            for rule in self.applicable(phase)
            for key in rule.get("reference_keys", [])
        }
        return [
            {
                "key": key,
                "path": self.ruleset["reference_catalog"][key],
                "sha256": self.digest(LIB / self.ruleset["reference_catalog"][key]),
            }
            for key in sorted(keys)
        ]

    def result(self, rule_id: str, phase: str) -> dict:
        return {
            "rule_id": rule_id,
            "phase": phase,
            "result": "PASS",
            "information_status": "SUPPORTED",
            "evidence_type": "document_review",
            "claim": f"Structured test evidence for {rule_id}",
            "locator": copy.deepcopy(self.locator),
            "reviewed_by": "Gate test reviewer",
            "reviewed_at": "2026-09-29T12:00:00+03:00",
        }

    def assessment(self, phase: str = "DESIGN") -> dict:
        return {
            "schema_version": self.ruleset["schema_version"],
            "gate_version": self.ruleset["gate_version"],
            "phase": phase,
            "gate_result_date": "2026-09-29",
            "checked_by": "Gate test reviewer",
            "plan_sha256": self.digest(self.plan),
            "references_checked": self.reference_checks(phase),
            "results": [self.result(rule["rule_id"], phase) for rule in self.applicable(phase)],
        }

    @staticmethod
    def find(assessment: dict, rule_id: str) -> dict:
        return next(result for result in assessment["results"] if result["rule_id"] == rule_id)

    def test_clean_design_is_approved(self) -> None:
        self.assertEqual(evaluate(self.assessment(), self.plan)["gate_status"], "APPROVED")

    def test_source_authority_inputs_are_checked_against_manifest(self) -> None:
        assessment = self.assessment()
        self.assertTrue({"SOURCE_ROUTING", "PROGRAM_SOURCE_RULES"}.issubset(
            {item["key"] for item in assessment["references_checked"]}
        ))
        original_load = gate.load_json

        def changed_manifest(path):
            data = original_load(path)
            if path == gate.MANIFEST_PATH:
                data = copy.deepcopy(data)
                matrix_path = self.ruleset["reference_catalog"]["SOURCE_ROUTING"]
                next(item for item in data["files"] if item["path"] == matrix_path)["sha256"] = "0" * 64
            return data

        with patch.object(gate, "load_json", side_effect=changed_manifest):
            result = evaluate(assessment, self.plan)
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertTrue(any("not the approved version: SOURCE_ROUTING" in issue
                            for issue in result["blocking_issues"]))

    def test_school_context_is_read_from_current_json(self) -> None:
        original_load = gate.load_json

        def invalid_current(path):
            data = original_load(path)
            if path == gate.SCHOOL_CONTEXT_PATH:
                data = dict(data, student_count=0)
            return data

        with patch.object(gate, "load_json", side_effect=invalid_current):
            result = evaluate(self.assessment(), self.plan)
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertTrue(any("School context student_count" in issue
                            for issue in result["blocking_issues"]))

    def test_schema_and_rule_ids_are_complete(self) -> None:
        schema = json.loads(
            (LIB / "standards/weekly_plan_gate_assessment.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["gate_version"]["const"], self.ruleset["gate_version"])
        self.assertEqual(len(self.rules), 18)
        self.assertEqual(len({rule["rule_id"] for rule in self.rules}), 18)
        self.assertTrue(all(rule.get("reference_keys") for rule in self.rules))

    def test_status_precedence(self) -> None:
        warning = self.assessment()
        w03 = self.find(warning, "W03")
        w03.update(result="FAIL", level="WARNING")
        self.assertEqual(evaluate(warning, self.plan)["gate_status"], "APPROVED_WITH_WARNINGS")

        review = self.assessment()
        self.find(review, "W02")["result"] = "REVIEW"
        self.assertEqual(evaluate(review, self.plan)["gate_status"], "HUMAN_REVIEW_REQUIRED")

        blocked = self.assessment()
        self.find(blocked, "E01")["result"] = "FAIL"
        self.assertEqual(evaluate(blocked, self.plan)["gate_status"], "BLOCKED")

    def test_hash_change_blocks(self) -> None:
        assessment = self.assessment()
        assessment["plan_sha256"] = "0" * 64
        self.assertEqual(evaluate(assessment, self.plan)["gate_status"], "BLOCKED")

    def test_missing_or_extra_phase_rule_blocks(self) -> None:
        missing = self.assessment()
        missing["results"].pop()
        self.assertEqual(evaluate(missing, self.plan)["gate_status"], "BLOCKED")

        extra = self.assessment()
        extra["results"].append(self.result("N02", "DESIGN"))
        self.assertEqual(evaluate(extra, self.plan)["gate_status"], "BLOCKED")

    def test_fake_locator_blocks(self) -> None:
        assessment = self.assessment()
        self.find(assessment, "E01")["locator"]["path"] = "missing-evidence.md"
        result = evaluate(assessment, self.plan)
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertTrue(any("locator path does not exist" in item for item in result["blocking_issues"]))

    def test_metadata_validation_blocks_empty_reviewer_and_bad_dates(self) -> None:
        assessment = self.assessment()
        assessment["checked_by"] = ""
        assessment["gate_result_date"] = "not-a-date"
        self.find(assessment, "E01")["reviewed_at"] = "yesterday"
        result = evaluate(assessment, self.plan)
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertGreaterEqual(len(result["blocking_issues"]), 3)

    def test_schema_rejects_unexpected_fields(self) -> None:
        assessment = self.assessment()
        assessment["legacy_scope"] = "not allowed"
        self.find(assessment, "E01")["legacy_evidence"] = "not allowed"
        self.find(assessment, "E02")["locator"]["line"] = 10
        assessment["references_checked"][0]["label"] = "not allowed"
        result = evaluate(assessment, self.plan)
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertTrue(any("Unknown assessment fields" in item for item in result["blocking_issues"]))
        self.assertTrue(any("unknown fields" in item for item in result["blocking_issues"]))

    def test_reference_hash_and_affected_rules(self) -> None:
        assessment = self.assessment()
        assessment["references_checked"] = [
            ref for ref in assessment["references_checked"] if ref["key"] != "QASSIM_PLAN"
        ]
        result = evaluate(assessment, self.plan)
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertIn("QASSIM_PLAN", result["affected_rules_by_reference"])
        self.assertIn("E01", result["affected_rules_by_reference"]["QASSIM_PLAN"])

    def test_not_applicable_requires_reason_scope_and_matching_status(self) -> None:
        invalid = self.assessment()
        self.find(invalid, "N01")["result"] = "NOT_APPLICABLE"
        self.assertEqual(evaluate(invalid, self.plan)["gate_status"], "BLOCKED")

        valid = self.assessment()
        n01 = self.find(valid, "N01")
        n01.update(
            result="NOT_APPLICABLE",
            information_status="NOT_APPLICABLE",
            applicability_reason="No Noor route is required for this supporting activity",
            scope="This activity only",
        )
        result = evaluate(valid, self.plan)
        self.assertEqual(result["gate_status"], "APPROVED")
        self.assertIn("N01", result["not_applicable_rules"])

    def test_pending_indicator_is_not_failure(self) -> None:
        assessment = self.assessment("POST_EXECUTION")
        n03 = self.find(assessment, "N03")
        n03["information_status"] = "NOT_MEASURED"
        n03["claim"] = "The real indicator value is not available yet and no value is claimed"
        result = evaluate(assessment, self.plan)
        self.assertEqual(result["gate_status"], "APPROVED")
        self.assertTrue(any("N03" in item for item in result["pending_items"]))

    def test_not_assessable_returns_not_ready(self) -> None:
        assessment = self.assessment()
        w02 = self.find(assessment, "W02")
        w02.update(result="NOT_ASSESSABLE_YET", information_status="NOT_ASSESSABLE_YET")
        result = evaluate(assessment, self.plan)
        self.assertEqual(result["gate_status"], "NOT_READY_FOR_PHASE")

    def test_blocker_review_remains_blocked(self) -> None:
        assessment = self.assessment()
        self.find(assessment, "E01")["result"] = "REVIEW"
        self.assertEqual(evaluate(assessment, self.plan)["gate_status"], "BLOCKED")

    def test_escalation_requires_reason(self) -> None:
        invalid = self.assessment()
        self.find(invalid, "W03").update(result="FAIL", level="BLOCKER")
        self.assertEqual(evaluate(invalid, self.plan)["gate_status"], "BLOCKED")
        self.assertTrue(
            any("escalation_reason" in item for item in evaluate(invalid, self.plan)["blocking_issues"])
        )

        valid = self.assessment()
        self.find(valid, "W03").update(
            result="FAIL",
            level="BLOCKER",
            escalation_reason="The plan cannot be executed by one counselor",
        )
        self.assertEqual(evaluate(valid, self.plan)["gate_status"], "BLOCKED")

    def test_failure_level_cannot_be_downgraded(self) -> None:
        assessment = self.assessment()
        self.find(assessment, "E01").update(result="FAIL", level="WARNING")
        result = evaluate(assessment, self.plan)
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertTrue(any("cannot downgrade" in item for item in result["blocking_issues"]))

    def test_registered_source_id_is_valid_locator(self) -> None:
        assessment = self.assessment()
        self.find(assessment, "E01")["locator"] = {
            "path": "source_id:REF-QASSIM-1448",
            "pdf_page": 1,
        }
        self.assertEqual(evaluate(assessment, self.plan)["gate_status"], "APPROVED")

    def test_all_four_phases_have_distinct_rule_sets(self) -> None:
        sets = {
            phase: {rule["rule_id"] for rule in self.applicable(phase)}
            for phase in self.ruleset["phases"]
        }
        self.assertNotEqual(sets["DESIGN"], sets["POST_EXECUTION"])
        self.assertNotIn("N02", sets["DESIGN"])
        self.assertIn("N02", sets["POST_EXECUTION"])
        self.assertIn("D03", sets["CLOSURE"])

    def test_operational_scenarios(self) -> None:
        scenarios = [
            ("continuous_program", "DESIGN", "E04", "PASS", "SUPPORTED", "APPROVED"),
            ("event_driven_service", "DESIGN", "E04", "PASS", "SUPPORTED", "APPROVED"),
            ("emergency_with_priority", "DESIGN", "W01", "PASS", "SUPPORTED", "APPROVED"),
            ("executed_not_entered", "POST_EXECUTION", "D02", "PASS", "VERIFIED", "APPROVED"),
            ("entered_not_visible", "POST_EXECUTION", "D02", "REVIEW", "SUPPORTED", "HUMAN_REVIEW_REQUIRED"),
            ("incorrect_noor_entry", "POST_EXECUTION", "N01", "REVIEW", "VERIFIED", "HUMAN_REVIEW_REQUIRED"),
            ("noor_program_not_due", "DESIGN", "E01", "NOT_APPLICABLE", "NOT_APPLICABLE", "APPROVED"),
            ("due_item_without_noor_match", "DESIGN", "N01", "NOT_APPLICABLE", "NOT_APPLICABLE", "APPROVED"),
            ("signed_paper_original", "PRE_EXECUTION", "D03", "PASS", "SUPPORTED", "APPROVED"),
            ("temporary_capture", "PRE_EXECUTION", "D01", "PASS", "SUPPORTED", "APPROVED"),
            ("blank_form", "PRE_EXECUTION", "V01", "NOT_APPLICABLE", "NOT_APPLICABLE", "APPROVED"),
            ("filled_form_without_evidence", "POST_EXECUTION", "V01", "REVIEW", "SUPPORTED", "HUMAN_REVIEW_REQUIRED"),
            ("shared_evidence", "POST_EXECUTION", "V02", "PASS", "VERIFIED", "APPROVED"),
            ("photo_proves_execution_not_impact", "POST_EXECUTION", "V01", "PASS", "VERIFIED", "APPROVED"),
            ("indicator_without_value", "POST_EXECUTION", "N03", "PASS", "NOT_MEASURED", "APPROVED"),
            ("ended_program_followup", "DESIGN", "E04", "PASS", "SUPPORTED", "APPROVED"),
            ("continuous_item_not_reopened", "DESIGN", "E04", "PASS", "SUPPORTED", "APPROVED"),
        ]
        for name, phase, rule_id, state, info_status, expected in scenarios:
            with self.subTest(name=name):
                assessment = self.assessment(phase)
                result = self.find(assessment, rule_id)
                result.update(
                    result=state,
                    information_status=info_status,
                    claim=f"Scenario: {name}",
                )
                if state == "NOT_APPLICABLE":
                    result.update(
                        applicability_reason=f"Scenario-specific reason: {name}",
                        scope=f"Scenario scope: {name}",
                    )
                evaluated = evaluate(assessment, self.plan)
                self.assertEqual(evaluated["gate_status"], expected)


if __name__ == "__main__":
    unittest.main()
