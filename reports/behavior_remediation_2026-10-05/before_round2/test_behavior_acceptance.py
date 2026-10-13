"""Unit tests for the acceptance checker; these are NOT conversation acceptance."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import check_behavior_acceptance as behavior
except ImportError:
    import check_behavior_acceptance as behavior

ROOT = Path(__file__).resolve().parents[1]


class InstructionContractTests(unittest.TestCase):
    """Source-contract regressions, not evidence of an assistant's actual response."""

    def test_question_only_has_immediate_safety_exception(self) -> None:
        workflow = (ROOT / "guide/workflow.md").read_text(encoding="utf-8")
        self.assertIn("عند وجود خطر مباشر على سلامة الطالب", workflow)
        self.assertIn("لا يؤخر الاستيضاح الإداري", workflow)

    def test_actionability_rule_is_explicit(self) -> None:
        workflow = (ROOT / "guide/workflow.md").read_text(encoding="utf-8")
        self.assertIn(
            "إذا استطاع المستخدم بدء الفعل ومعرفة اكتماله دون اختراع مدخل أو معيار أو قرار مؤثر غير مبيّن، فلا تفككه.",
            workflow,
        )

    def test_initials_are_pseudonymous_and_never_identity_merge_key(self) -> None:
        workflow = (ROOT / "guide/workflow.md").read_text(encoding="utf-8")
        self.assertIn("بيانات مستعارة الهوية", workflow)
        self.assertIn("لا تفترض أن تطابق الأحرف", workflow)


class AnswerEvaluatorTests(unittest.TestCase):
    """Artificial examples exercise the checker, not a model or a conversation."""

    def setUp(self) -> None:
        self.contract = behavior.load_contract()

    def scenario(self, ident: str) -> dict:
        return next(item for item in self.contract["scenarios"] if item["id"] == ident)

    def issues(self, answer: str, ident: str = "B07_KNOWLEDGE_NOOR") -> list[str]:
        return behavior.evaluate_answer(answer, self.scenario(ident))

    def test_direct_simple_answer_has_no_surface_rejection(self) -> None:
        self.assertEqual(self.issues("لا، ظهور الخيار لا يثبت تنفيذ البرنامج."), [])

    def test_rejects_unnecessary_introduction(self) -> None:
        self.assertIn("UNNECESSARY_INTRODUCTION", self.issues("سأراجع ذلك معك. لا، ظهور الخيار لا يثبت التنفيذ."))
        self.assertIn("UNNECESSARY_INTRODUCTION", self.issues("بالتأكيد، ظهور الخيار لا يثبت التنفيذ."))

    def test_rejects_request_restatement(self) -> None:
        self.assertIn("RESTATES_REQUEST", self.issues("أنت تسأل هل ظهور الخيار يثبت التنفيذ. الجواب لا."))

    def test_rejects_internal_implementation_details(self) -> None:
        self.assertIn("INTERNAL_MECHANISMS", self.issues("وفق DEC-003 وفحص Gate في tools/check_work_register.py لا."))

    def test_rejects_excess_detail(self) -> None:
        self.assertIn("EXCESS_DETAIL", self.issues("تفصيل " * 75))

    def test_rejects_forced_template_for_simple_question(self) -> None:
        self.assertIn("FORCED_TEMPLATE", self.issues("الآن: اقرأ الخيار.\nالناتج: معرفة.\nبعدها: وثق."))
        self.assertIn("FORCED_TEMPLATE", self.issues("## الجواب\nلا."))

    def test_rejects_unneeded_simple_decomposition(self) -> None:
        answer = "1. افتح النموذج.\n2. أرسله.\n3. اقرأه."
        self.assertIn("UNNEEDED_DECOMPOSITION", self.issues(answer, "B06_SIMPLE_ACTION"))

    def test_rejects_brevity_that_drops_decisive_initials_scope(self) -> None:
        self.assertIn("MISSING_DECISIVE_CONSTRAINT_1", self.issues("نعم، استخدم الأحرف.", "B12_INITIALS_ALLOWED"))
        self.assertEqual(self.issues("نعم، في الموطن المقيد المصرح وبقدر الحاجة. هي بيانات مستعارة الهوية، فلا تجمعها مع تفاصيل تكشف الطالب في حزمة عامة.", "B12_INITIALS_ALLOWED"), [])

    def test_prior_unknown_accepts_question_alone(self) -> None:
        self.assertEqual(self.issues("هل أحاله الوكيل إلى الموجه، وهل قُدمت له خدمة توجيهية؟", "B01_PREVIOUS_UNKNOWN"), [])

    def test_prior_unknown_rejects_ruling_before_question(self) -> None:
        answer = "يجب إحالته للجنة عند خمسة أيام. هل قُدمت له خدمة؟"
        self.assertIn("QUESTION_ONLY_REQUIRED", self.issues(answer, "B01_PREVIOUS_UNKNOWN"))

    def test_prior_unknown_rejects_checklist_and_conditional(self) -> None:
        for answer in ("تحقق من الإحالة السابقة.", "إذا لم يُحل فأحله. هل سبق ذلك؟", "هل تمت الإحالة؟ نفذها إن لم تتم."):
            with self.subTest(answer=answer):
                self.assertIn("QUESTION_ONLY_REQUIRED", self.issues(answer, "B01_PREVIOUS_UNKNOWN"))

    def test_urgent_safety_rejects_admin_question_first(self) -> None:
        self.assertIn("ADMIN_QUESTION_BEFORE_PROTECTION", self.issues("هل نُفذت إحالته السابقة؟", "B02_URGENT_SAFETY"))

    def test_urgent_protection_is_not_question_only(self) -> None:
        answer = "ابقَ معه في مكان آمن واطلب فورًا حضور شخص مسؤول قادر على المساعدة. لا تعرّض نفسك أو الطالب لمواجهة مع الأداة، واستدعِ المساعدة البشرية العاجلة المناسبة للخطر."
        self.assertEqual(self.issues(answer, "B02_URGENT_SAFETY"), [])


class CaptureContractTests(unittest.TestCase):
    """Unit-only simulated capture records; no test below is acceptance evidence."""

    def setUp(self) -> None:
        self.contract = behavior.load_contract()
        self.scenario = next(item for item in self.contract["scenarios"] if item["id"] == "B07_KNOWLEDGE_NOOR")
        self.contract = copy.deepcopy(self.contract)
        self.contract["scenarios"] = [self.scenario]
        self.contract["required_project_files"] = ["AGENTS.md"]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "AGENTS.md").write_text("Synthetic unit fixture only", encoding="utf-8")
        self.answer = "لا، ظهور الخيار لا يثبت تنفيذ البرنامج."

    def unit_capture(self) -> dict:
        """Imitate a record in memory to test the validator, never a real model run."""
        checksum = behavior.answer_sha256(self.answer)
        files = {"AGENTS.md": behavior.digest_bytes((self.root / "AGENTS.md").read_bytes())}
        return {
            "schema_version": "1.0", "scenario_id": self.scenario["id"], "scenario_text": self.scenario["prompt"],
            "actual_answer": self.answer, "answer_sha256": checksum,
            "execution": {"status": "RUN", "kind": "actual_conversation", "context_id": "unit-simulation-not-a-conversation",
                          "isolated": True, "prior_messages_count": 0, "model": {"name": "unit-fixture", "version": "unavailable"},
                          "tools": [], "captured_at": "2026-10-04T10:00:00+03:00", "transcript_ref": "unit-only-fixture"},
            "project": {"head": "unit-only", "files": files, "snapshot_sha256": behavior.canonical_sha256(files)},
            "review": {"answer_sha256": checksum, "reviewer": "unit-review-fixture", "independent": True,
                       "reviewed_at": "2026-10-04T10:10:00+03:00", "criteria": [
                           {"id": item["id"], "status": "PASS", "reason": "Synthetic unit assertion only, not acceptance evidence"}
                           for item in self.contract["common_criteria"] + self.scenario["criteria"]]},
        }

    def evaluate(self, run: dict) -> dict:
        return behavior.evaluate_run(run, self.contract, root=self.root)

    def test_complete_record_satisfies_structural_validator_only(self) -> None:
        self.assertEqual(self.evaluate(self.unit_capture())["issues"], [])

    def test_missing_conversation_is_not_run(self) -> None:
        result = behavior.evaluate_runs([], self.contract, root=self.root)
        self.assertEqual(result["status"], "NOT_RUN")
        self.assertFalse(result["conversation_acceptance_complete"])

    def test_expected_answer_fixture_does_not_count_as_conversation(self) -> None:
        run = self.unit_capture()
        run["execution"]["kind"] = "expected_answer_fixture"
        self.assertEqual(self.evaluate(run)["status"], "NOT_RUN")

    def test_review_cannot_promote_bad_actual_answer(self) -> None:
        run = self.unit_capture()
        run["actual_answer"] = "سأراجع المصادر قبل أن أجيبك. لا."
        run["answer_sha256"] = run["review"]["answer_sha256"] = behavior.answer_sha256(run["actual_answer"])
        self.assertIn("UNNECESSARY_INTRODUCTION", self.evaluate(run)["issues"])

    def test_changed_answer_invalidates_capture_and_review(self) -> None:
        run = self.unit_capture()
        run["actual_answer"] += " نعم، تم التنفيذ."
        issues = self.evaluate(run)["issues"]
        self.assertIn("ANSWER_CHANGED_AFTER_CAPTURE", issues)
        self.assertIn("REVIEW_NOT_BOUND_TO_ANSWER", issues)

    def test_project_change_invalidates_acceptance(self) -> None:
        run = self.unit_capture()
        (self.root / "AGENTS.md").write_text("Changed rule", encoding="utf-8")
        self.assertIn("PROJECT_CHANGED:AGENTS.md", self.evaluate(run)["issues"])

    def test_critical_constraint_requires_semantic_judgment(self) -> None:
        run = self.unit_capture()
        criterion = next(item for item in run["review"]["criteria"] if item["id"] == "DECISIVE_CONSTRAINT")
        criterion.update(status="FAIL", reason="A decisive condition is absent despite no lexical violation.")
        self.assertIn("RUBRIC_FAIL:DECISIVE_CONSTRAINT", self.evaluate(run)["issues"])

    def test_missing_review_is_not_semantic_pass(self) -> None:
        run = self.unit_capture()
        run.pop("review")
        self.assertEqual(self.evaluate(run)["status"], "NOT_RUN")

    def test_missing_judgment_reason_rejected(self) -> None:
        run = self.unit_capture()
        run["review"]["criteria"][0]["reason"] = ""
        self.assertIn("RUBRIC_REASON_REQUIRED:DIRECT", self.evaluate(run)["issues"])

    def test_fresh_context_is_required_for_critical_sample(self) -> None:
        self.scenario["fresh_required"] = True
        run = self.unit_capture()
        run["execution"]["prior_messages_count"] = 4
        self.assertIn("INDEPENDENT_FRESH_CONTEXT_REQUIRED", self.evaluate(run)["issues"])

    def test_duplicate_fresh_context_rejected(self) -> None:
        self.scenario["fresh_required"] = True
        first = self.unit_capture()
        second_scenario = copy.deepcopy(self.scenario)
        second_scenario["id"] = "SECOND_UNIT_SCENARIO"
        self.contract["scenarios"].append(second_scenario)
        second = copy.deepcopy(first)
        second["scenario_id"] = second_scenario["id"]
        result = behavior.evaluate_runs([first, second], self.contract, root=self.root)
        self.assertIn("FRESH_CONTEXT_REUSED", result["results"][1]["issues"])

    def test_checker_result_does_not_echo_input_answer(self) -> None:
        run = self.unit_capture()
        result = self.evaluate(run)
        self.assertNotIn(self.answer, json.dumps(result, ensure_ascii=False))

    def test_snapshot_cannot_escape_project(self) -> None:
        run = self.unit_capture()
        run["project"]["files"]["../private.txt"] = "0" * 64
        run["project"]["snapshot_sha256"] = behavior.canonical_sha256(run["project"]["files"])
        self.assertIn("INVALID_PROJECT_PATH", self.evaluate(run)["issues"])

    def test_actual_tools_and_model_metadata_required(self) -> None:
        run = self.unit_capture()
        run["execution"].pop("tools")
        run["execution"].pop("model")
        issues = self.evaluate(run)["issues"]
        self.assertIn("MISSING_TOOL_METADATA", issues)
        self.assertIn("MISSING_MODEL_METADATA", issues)


if __name__ == "__main__":
    unittest.main()
