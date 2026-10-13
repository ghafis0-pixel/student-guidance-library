"""Reproduce the metadata false rejection without relabeling historical acceptance."""
import importlib.util
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_behavior_acceptance import evaluate_answer, split_memory_metadata

spec = importlib.util.spec_from_file_location('old_checker', OUT / 'before_round2/check_behavior_acceptance.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
runs = json.loads((OUT / 'fresh_runs_unreviewed.json').read_text(encoding='utf-8'))['runs']
contract = json.loads((OUT / 'before_round2/behavior_acceptance.json').read_text(encoding='utf-8-sig'))
run = next(r for r in runs if r['scenario_id'] == 'B01_PREVIOUS_UNKNOWN')
scenario = next(s for s in contract['scenarios'] if s['id'] == run['scenario_id'])
raw = run['actual_answer']
body, metadata, valid = split_memory_metadata(raw)
before = old.evaluate_answer(raw, scenario)
after = evaluate_answer(raw, scenario, required_memory_metadata=True)
if 'QUESTION_ONLY_REQUIRED' not in before or after or not valid or body + metadata != raw:
    raise RuntimeError('Metadata diagnostic did not reproduce the exact symptom')
diagnostic = {
    'kind': 'TEXT_BOUNDARY_DIAGNOSTIC_NOT_CONVERSATION_ACCEPTANCE',
    'scenario_id': run['scenario_id'], 'unchanged_raw_answer_sha256': run['answer_sha256'],
    'old_surface_issues': before, 'new_surface_issues_with_verified_host_requirement': after,
    'exact_raw_preserved': body + metadata == raw,
    'mandatory_provenance_verified_by_independent_review': 'review_metadata_boundary confirmed actual memory-read calls in all five round1 suffix cases; live acceptance additionally requires bound transcript/read call IDs',
    'ui_rendering': 'UNVERIFIED',
    'historical_scores_changed': False,
    'initial_new_unit_tests': '8 tests errored against absent new API; not the symptom-specific reproduction. This diagnostic is the actual old false-rejection reproduction.',
    'sandbox_unit_temp_error': 'Default temp location denied synthetic AGENTS.md writes; no product test failed for that reason. Tests rerun with temp directory inside workspace.',
    'new_unit_tests_result': '41 tests passed; current unit evidence does not establish model behavior',
}
(OUT / 'metadata_diagnostic.json').write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'before': before, 'after': after, 'raw_preserved': True}))
