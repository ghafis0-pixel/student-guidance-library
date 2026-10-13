"""Negative regressions for source locations and replayed Gate approvals.

All changed references and 63-page PDFs are isolated synthetic fixtures. These
tests establish structural safeguards; they are not school or chat acceptance.
"""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

try:
    from . import check_weekly_plan_gate as gate
    from .test_weekly_plan_gate import GateTests
except ImportError:
    import check_weekly_plan_gate as gate
    from test_weekly_plan_gate import GateTests


class ExistingLocatorRegressions(GateTests):
    """These first regressions exercise the old accepted locator contract."""

    def test_impossible_pdf_page_does_not_pass(self):
        assessment = self.assessment()
        self.find(assessment, "E01")["locator"] = {
            "path": self.ruleset["reference_catalog"]["QASSIM_PLAN"],
            "page_or_section": "PDF page 9999",
        }
        self.assertNotIn(gate.evaluate(assessment, self.plan)["gate_status"],
                         {"APPROVED", "APPROVED_WITH_WARNINGS"})

    def test_nonexistent_section_does_not_pass(self):
        assessment = self.assessment()
        self.find(assessment, "E01")["locator"]["page_or_section"] = "SECTION_DOES_NOT_EXIST_9999"
        self.assertNotIn(gate.evaluate(assessment, self.plan)["gate_status"],
                         {"APPROVED", "APPROVED_WITH_WARNINGS"})

    def test_result_has_complete_assessment_fingerprint(self):
        assessment = self.assessment()
        result = gate.evaluate(assessment, self.plan)
        self.assertIn("assessment_sha256", result)
        changed = copy.deepcopy(assessment)
        self.find(changed, "E01")["result"] = "FAIL"
        self.assertNotEqual(result["assessment_sha256"],
                            gate.evaluate(changed, self.plan)["assessment_sha256"])


class BoundGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gate-regression-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rules = gate.load_json(gate.LIB / "standards/weekly_plan_gate_rules.yaml")
        self.plan = self.write("plan.bin", b"synthetic approved plan")
        self.write("evidence.md", b"# Verified section\nSynthetic fixture.\n")
        for key in self.rules["reference_catalog"]:
            self.rules["reference_catalog"][key] = "evidence.md"
        for key, relative in {
            "GOVERNING_DECISIONS": "context/decisions.md",
            "NOOR_DECISION_MATRIX": "catalog/records_noor_decision_matrix.json",
            "SOURCE_ROUTING": "catalog/reference_matrix.json",
        }.items():
            self.rules["reference_catalog"][key] = relative
            self.write(relative, b"Original synthetic operational input.\n")
        self.rules["reference_catalog"]["PROCEDURAL_GUIDE"] = "procedural.pdf"
        writer = PdfWriter()
        for _ in range(63):
            writer.add_blank_page(width=100, height=100)
        self.pdf = self.root / "procedural.pdf"
        writer.write(self.pdf)
        self.write_json("standards/weekly_plan_gate_rules.yaml", self.rules)
        self.write_json("context/current.json", {"student_count": 130})
        self.write_json("catalog/source_registry.json", {"sources": [
            {"source_id": "REF-PROCEDURAL-FULL-1446", "reference_path": "procedural.pdf",
             "sha256": gate.sha256(self.pdf), "coverage": "full", "governing": True,
             "status": "current_user_approved"},
            {"source_id": "MISSING", "reference_path": "missing.pdf"},
        ]})
        self.write_json("catalog/manifest.json", {"files": [
            {"path": relative, "sha256": gate.sha256(self.root / relative)}
            for relative in ("evidence.md", "catalog/reference_matrix.json")]})
        applicable = [rule for rule in self.rules["rule_definitions"] if "DESIGN" in rule["phases"]]
        keys = {key for rule in applicable for key in rule["reference_keys"]}
        self.assessment = {
            "schema_version": self.rules["schema_version"],
            "gate_version": self.rules["gate_version"], "phase": "DESIGN",
            "gate_result_date": "2026-10-04", "checked_by": "Synthetic test reviewer",
            "plan_sha256": gate.sha256(self.plan),
            "references_checked": [{"key": key, "path": self.rules["reference_catalog"][key],
                "sha256": gate.sha256(self.root / self.rules["reference_catalog"][key])} for key in sorted(keys)],
            "results": [{"rule_id": rule["rule_id"], "phase": "DESIGN", "result": "PASS",
                "information_status": "SUPPORTED", "evidence_type": "synthetic_document_review",
                "claim": "Synthetic assertion; no field execution.",
                "locator": {"path": "evidence.md", "section": "Verified section"},
                "reviewed_by": "Synthetic test reviewer", "reviewed_at": "2026-10-04T12:00:00+03:00"}
                for rule in applicable],
        }

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_json(self, relative, data):
        return self.write(relative, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def evaluate(self):
        return gate.evaluate(self.assessment, self.plan, root=self.root)

    def at(self, rule_id="E01"):
        return next(item for item in self.assessment["results"] if item["rule_id"] == rule_id)

    def test_valid_result_rechecks_without_global_mutation(self):
        result = self.evaluate()
        self.assertEqual(result["gate_status"], "APPROVED", result["blocking_issues"])
        self.assertEqual(gate.verify_current_result(self.assessment, self.plan, result, root=self.root), [])

    def test_stale_approved_result_after_e01_fail_is_rejected(self):
        saved = self.evaluate()
        self.assertEqual(saved["gate_status"], "APPROVED")
        self.at()["result"] = "FAIL"
        self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))

    def test_current_source_governance_is_pinned_to_manifest(self):
        for key in ("SOURCE_ROUTING", "PROGRAM_SOURCE_RULES"):
            with self.subTest(key=key):
                path = self.root / self.rules["reference_catalog"][key]
                original = path.read_bytes()
                path.write_bytes(original + b"Changed governance after approval.\n")
                entry = next(item for item in self.assessment["references_checked"] if item["key"] == key)
                original_digest = entry["sha256"]
                entry["sha256"] = gate.sha256(path)
                result = self.evaluate()
                self.assertEqual(result["gate_status"], "BLOCKED")
                self.assertTrue(any("not the approved version: " + key in issue for issue in result["blocking_issues"]))
                path.write_bytes(original)
                entry["sha256"] = original_digest

    def test_stale_approved_result_after_rule_change_is_rejected(self):
        saved = self.evaluate()
        self.assertEqual(saved["gate_status"], "APPROVED")
        self.rules["rule_definitions"][0]["description"] += " changed governing rule"
        self.write_json("standards/weekly_plan_gate_rules.yaml", self.rules)
        self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))

    def test_stale_result_after_context_or_locator_file_change_is_rejected(self):
        for filename, data in [("context/current.json", b'{"student_count": 131}'),
                                ("evidence.md", b"# Verified section\nChanged evidence.\n")]:
            with self.subTest(filename=filename):
                original = (self.root / filename).read_bytes()
                saved = self.evaluate()
                self.write(filename, data)
                self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))
                self.write(filename, original)

    def test_stale_result_after_note_change_is_rejected(self):
        saved = self.evaluate()
        self.assessment["notes"] = "The complete assessment includes notes."
        self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))

    def test_stale_result_after_governing_decision_or_noor_mapping_change_is_rejected(self):
        # These inputs affect the reviewed meaning even when a locator points at the plan.
        inputs = ["context/decisions.md", "catalog/records_noor_decision_matrix.json",
                  "catalog/reference_matrix.json"]
        for relative in inputs:
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                saved = self.evaluate()
                self.assertEqual(saved["gate_status"], "APPROVED")
                path.write_bytes(b"Changed operational meaning after review.")
                self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))
                path.write_bytes(original)

    def test_unlisted_locator_file_and_page_map_are_bound(self):
        self.write("independent.md", b"# Independent heading\nOriginal.\n")
        self.at()["locator"] = {"path": "independent.md", "section": "Independent heading"}
        saved = self.evaluate()
        self.assertEqual(saved["gate_status"], "APPROVED")
        self.write("independent.md", b"# Independent heading\nChanged.\n")
        self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))
        self.write_json("page-map.json", {"source_sha256": gate.sha256(self.pdf), "mapping": {"3": 5},
            "reviewed_by": "Synthetic mapper", "reviewed_at": "2026-10-04T12:00:00+03:00"})
        self.at()["locator"] = {"path": "procedural.pdf", "printed_page": "3", "page_map": "page-map.json"}
        saved = self.evaluate()
        self.assertEqual(saved["gate_status"], "APPROVED")
        self.write_json("page-map.json", {"source_sha256": gate.sha256(self.pdf), "mapping": {"3": 6},
            "reviewed_by": "Synthetic mapper", "reviewed_at": "2026-10-04T12:00:00+03:00"})
        self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))

    def test_canonical_assessment_reorders_keys_but_includes_array_order(self):
        saved = self.evaluate()
        reordered = dict(reversed(list(self.assessment.items())))
        self.assertEqual(gate.verify_current_result(reordered, self.plan, saved, root=self.root), [])
        self.assessment["results"].reverse()
        self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))

    def test_result_status_cannot_be_forged(self):
        self.at()["result"] = "FAIL"
        saved = self.evaluate()
        saved["gate_status"] = "APPROVED"
        self.assertTrue(gate.verify_current_result(self.assessment, self.plan, saved, root=self.root))

    def test_page_9999_is_rejected_in_actual_63_page_pdf(self):
        self.at()["locator"] = {"path": "procedural.pdf", "pdf_page": 9999}
        result = self.evaluate()
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertTrue(any("63" in issue and "9999" in issue for issue in result["blocking_issues"]))

    def test_physical_page_is_distinct_from_printed_number(self):
        self.at()["locator"] = {"path": "procedural.pdf", "pdf_page": 3}
        self.assertEqual(self.evaluate()["gate_status"], "APPROVED")
        self.at()["locator"] = {"path": "procedural.pdf", "printed_page": "3"}
        self.assertNotEqual(self.evaluate()["gate_status"], "APPROVED")
        self.write_json("page-map.json", {"source_sha256": gate.sha256(self.pdf),
            "mapping": {"3": 5}, "reviewed_by": "Synthetic page mapper", "reviewed_at": "2026-10-04T12:00:00+03:00"})
        self.at()["locator"]["page_map"] = "page-map.json"
        result = self.evaluate()
        self.assertEqual(result["gate_status"], "APPROVED")
        self.assertEqual(result["locator_checks"]["E01"]["pdf_page"], 5)
        self.write_json("page-map.json", {"source_sha256": "0" * 64, "mapping": {"3": 5},
            "reviewed_by": "Synthetic page mapper", "reviewed_at": "2026-10-04T12:00:00+03:00"})
        self.assertEqual(self.evaluate()["gate_status"], "BLOCKED")

    def test_nonexistent_section_is_not_verified(self):
        self.at()["locator"]["section"] = "Absent section"
        result = self.evaluate()
        self.assertEqual(result["gate_status"], "BLOCKED")
        self.assertNotEqual(result["locator_checks"]["E01"]["location_status"], "VERIFIED")

    def test_pdf_section_without_reliable_text_requires_review(self):
        self.at("W02")["locator"] = {"path": "procedural.pdf", "section": "Unverifiable heading"}
        result = self.evaluate()
        self.assertEqual(result["gate_status"], "HUMAN_REVIEW_REQUIRED")
        self.assertEqual(result["locator_checks"]["W02"]["location_status"], "REVIEW_REQUIRED")

    def test_source_id_still_requires_existing_file(self):
        self.at()["locator"] = {"path": "source_id:MISSING", "pdf_page": 1}
        self.assertEqual(self.evaluate()["gate_status"], "BLOCKED")

    def test_source_and_location_never_claim_semantic_verification(self):
        checked = self.evaluate()["locator_checks"]["E01"]
        self.assertEqual(checked["source_status"], "EXISTS")
        self.assertEqual(checked["location_status"], "VERIFIED")
        self.assertEqual(checked["semantic_support"], "NOT_AUTOMATICALLY_VERIFIED")

    def test_historical_result_is_insufficient_for_readiness(self):
        old = {"gate_status": "APPROVED", "gate_version": "1.1.0", "plan_sha256": gate.sha256(self.plan)}
        self.assertTrue(gate.verify_current_result(self.assessment, self.plan, old, root=self.root))

    def test_complete_procedural_original_is_required(self):
        self.rules["reference_catalog"]["PROCEDURAL_GUIDE"] = "evidence.md"
        self.write_json("standards/weekly_plan_gate_rules.yaml", self.rules)
        ref = next(r for r in self.assessment["references_checked"] if r["key"] == "PROCEDURAL_GUIDE")
        ref.update(path="evidence.md", sha256=gate.sha256(self.root / "evidence.md"))
        self.assertEqual(self.evaluate()["gate_status"], "BLOCKED")

    def test_cli_rejects_sensitive_claim_before_public_save_or_print(self):
        self.at().update(result="FAIL", claim="student name: Synthetic Example")
        assessment_path = self.write_json("assessment.json", self.assessment)
        output = self.write("result.json", b"existing output must remain unchanged")
        argv = ["gate", "--assessment", str(assessment_path), "--plan", str(self.plan),
                "--root", str(self.root), "--output", str(output)]
        captured = io.StringIO()
        with patch("sys.argv", argv), redirect_stdout(captured), self.assertRaises(SystemExit) as exited:
            gate.main()
        self.assertEqual(exited.exception.code, 1)
        self.assertEqual(output.read_bytes(), b"existing output must remain unchanged")
        self.assertIn("PUBLIC_OUTPUT_BLOCKED", captured.getvalue())
        self.assertNotIn("Synthetic Example", captured.getvalue())

    def test_cli_writes_non_sensitive_gate_result(self):
        assessment_path = self.write_json("assessment.json", self.assessment)
        output = self.root / "result.json"
        argv = ["gate", "--assessment", str(assessment_path), "--plan", str(self.plan),
                "--root", str(self.root), "--output", str(output)]
        captured = io.StringIO()
        with patch("sys.argv", argv), redirect_stdout(captured), self.assertRaises(SystemExit) as exited:
            gate.main()
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), json.loads(captured.getvalue()))


def load_tests(loader, tests, pattern):
    # The old suite is run separately; don't count inherited/imported tests again.
    suite = unittest.TestSuite()
    for name in ExistingLocatorRegressions.__dict__:
        if name.startswith("test_"):
            suite.addTest(ExistingLocatorRegressions(name))
    suite.addTests(loader.loadTestsFromTestCase(BoundGateTests))
    return suite


if __name__ == "__main__":
    unittest.main()
