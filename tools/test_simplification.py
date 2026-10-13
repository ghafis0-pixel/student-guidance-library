"""Synthetic functional and preservation checks; not live assistant acceptance."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from . import verify_library as library
from . import privacy_guard as privacy

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(os.environ.get("SIMPLIFICATION_BASELINE", str(ROOT.parent / "improvement_baseline")))


class LibrarySimplificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = b"synthetic original reference"
        self.digest = hashlib.sha256(self.original).hexdigest()
        self.source = {"source_id": "S1", "reference_path": "references/source.pdf",
                       "archive_path": "archive/original.pdf", "sha256": self.digest}

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def manifest(self, path="archive/original.pdf", content=None):
        raw = self.original if content is None else content
        return {"file_count": 1, "files": [{"path": path, "size_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()}]}

    def matrix(self):
        self.write("context.json", b"{}")
        self.write("template.docx", b"synthetic empty template")
        return {"current_context_path": "context.json", "sources": [{"source_id": "S1"}],
                "records": [{"record_id": "R1", "original_path": "template.docx", "source_refs": ["S1"]}]}

    def test_reference_original_without_archive(self):
        expected = self.write(self.source["reference_path"], self.original)
        self.assertEqual(library.source_file(self.source, self.root), expected)

    def test_archive_original_still_supported(self):
        expected = self.write(self.source["archive_path"], self.original)
        self.assertEqual(library.source_file(self.source, self.root), expected)

    def test_changed_reference_is_not_original(self):
        self.write(self.source["reference_path"], b"modified")
        self.assertIsNone(library.source_file(self.source, self.root))

    def test_derived_text_cannot_replace_original(self):
        self.write("extracted.txt", self.original)
        self.assertIsNone(library.source_file(self.source, self.root))

    def test_manifest_accepts_identical_retained_original(self):
        self.write(self.source["reference_path"], self.original)
        self.assertEqual(library.validate_manifest(self.manifest(), [self.source], self.root), [])

    def test_manifest_changed_present_file_fails(self):
        self.write(self.source["archive_path"], b"modified")
        self.write(self.source["reference_path"], self.original)
        self.assertTrue(library.validate_manifest(self.manifest(), [self.source], self.root))

    def test_manifest_unknown_missing_file_fails(self):
        self.assertTrue(library.validate_manifest(self.manifest("other.pdf"), [self.source], self.root))

    def test_manifest_missing_zip_only_if_templates_verified(self):
        source = {**self.source, "source_type": "templates_archive", "archive_path": "records.zip"}
        manifest = self.manifest("records.zip")
        self.assertTrue(library.validate_manifest(manifest, [source], self.root))
        self.assertEqual(library.validate_manifest(manifest, [source], self.root, templates_available=True), [])

    def test_manifest_wrong_size_fails(self):
        self.write(self.source["reference_path"], self.original)
        manifest = self.manifest()
        manifest["files"][0]["size_bytes"] += 1
        self.assertTrue(library.validate_manifest(manifest, [self.source], self.root))

    def test_manifest_traversal_fails(self):
        self.assertTrue(library.validate_manifest(self.manifest("../outside.pdf"), [self.source], self.root))

    def test_matrix_not_required_to_have_31_records(self):
        self.assertEqual(library.validate_noor_matrix(self.matrix(), {"sources": [self.source]}, self.root), [])

    def test_matrix_duplicate_id_fails(self):
        matrix = self.matrix()
        matrix["records"] *= 2
        self.assertIn("duplicate Noor-matrix record ID", library.validate_noor_matrix(matrix, {"sources": [self.source]}, self.root))

    def test_matrix_missing_id_fails(self):
        matrix = self.matrix()
        matrix["records"][0].pop("record_id")
        self.assertIn("missing Noor-matrix record ID", library.validate_noor_matrix(matrix, {"sources": [self.source]}, self.root))

    def test_matrix_missing_template_fails(self):
        matrix = self.matrix()
        matrix["records"][0]["original_path"] = "missing.docx"
        self.assertTrue(library.validate_noor_matrix(matrix, {"sources": [self.source]}, self.root))

    def test_matrix_unknown_source_fails(self):
        matrix = self.matrix()
        matrix["records"][0]["source_refs"] = ["UNKNOWN"]
        self.assertTrue(library.validate_noor_matrix(matrix, {"sources": [self.source]}, self.root))


class ScopeAndPreservationTests(unittest.TestCase):
    def test_protected_files_unchanged(self):
        for path in ("standards/privacy_guard.md", "standards/weekly_plan_gate_rules.yaml",
                     "standards/weekly_plan_gate_assessment.schema.json", "tools/check_weekly_plan_gate.py",
                     "standards/behavior_acceptance.json", "tools/check_behavior_acceptance.py"):
            baseline = BASE / path
            if not baseline.exists():
                baseline = ROOT.parent / "p0_contents" / path
            self.assertEqual(baseline.read_bytes(), (ROOT / path).read_bytes(), path)

    def test_gate_contract_and_rule_blocks_unchanged(self):
        before = (BASE / "standards/WEEKLY_PLAN_GATE.md").read_text()
        after = (ROOT / "standards/WEEKLY_PLAN_GATE.md").read_text()
        self.assertEqual(before[before.index("## 2."):], after[after.index("## 2."):])

    def test_urgent_protection_unchanged(self):
        def block(path):
            text = path.read_text()
            return text[text.index("### الحماية العاجلة"):text.index("## السؤال المعرفي")]
        self.assertEqual(block(BASE / "guide/workflow.md"), block(ROOT / "guide/workflow.md"))

    def test_clarification_contract_unchanged(self):
        def block(path):
            text = path.read_text()
            return text[text.index("## الاستيضاح والتنفيذ السابق"):text.index("### الحماية العاجلة")]
        self.assertEqual(block(BASE / "guide/workflow.md"), block(ROOT / "guide/workflow.md"))

    def test_behavior_protocol_moved_without_loss(self):
        before = (BASE / "guide/workflow.md").read_text().split("## قبول السلوك\n\n")[1].strip()
        self.assertIn(before, (ROOT / "standards/BEHAVIOR_TESTING.md").read_text())
        self.assertNotIn("## قبول السلوك", (ROOT / "guide/workflow.md").read_text())

    def test_index_links_resolve(self):
        agents = (ROOT / "AGENTS.md").read_text()
        workflow = (ROOT / "guide/workflow.md").read_text()
        headings = {line.lstrip("# ") for line in workflow.splitlines() if line.startswith("#")}
        for section in re.findall(r"طبّق قسم «(.+)» في", agents):
            self.assertIn(section, headings)
        self.assertLess(len(agents), len((BASE / "AGENTS.md").read_text()) / 2)

    def test_internal_synthetic_full_name_allowed_public_rejected(self):
        data = {"student_name": "طالب اصطناعي للاختبار", "case_details": "تفاصيل صناعية"}
        self.assertEqual(privacy.scan_data(data, audience="restricted", authorization_ref="DEC-021"), [])
        self.assertTrue(privacy.scan_data(data, audience="restricted"))
        self.assertTrue(privacy.scan_data(data, audience="public"))

    def test_versions_match_active_gate(self):
        versions = json.loads((ROOT / "catalog/versions.json").read_text())["weekly_system"]
        from . import check_weekly_plan_gate as gate
        rules = json.loads((ROOT / "standards/weekly_plan_gate_rules.yaml").read_text())
        self.assertEqual(versions["weekly_plan_gate"], rules["gate_version"])
        self.assertEqual(versions["weekly_plan_gate_schema"], rules["schema_version"])
        self.assertEqual(versions["weekly_plan_gate_runner"], gate.RUNNER_VERSION)


if __name__ == "__main__":
    unittest.main()
