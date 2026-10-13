"""Verify saved reviews without inventing missing independent judgments."""
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_behavior_acceptance import canonical_sha256, evaluate_run, evaluate_answer

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

out = BASE / 'round2'
contract = read(ROOT / 'standards/behavior_acceptance.json')
old_contract = read(BASE / 'before_round2/behavior_acceptance.json')
assert contract['scenarios'] == old_contract['scenarios']
assert contract['common_criteria'] == old_contract['common_criteria']
snapshot = read(out / 'candidate_snapshot.json')['files']
drift = [name for name, digest in snapshot.items() if not (ROOT / name).is_file() or sha(ROOT / name) != digest]
assert not drift, drift
runs = read(out / 'fresh_runs_unreviewed.json')['runs']
transcripts = read(out / 'fresh_transcripts.json')
packet = read(out / 'reviews_sources.json')
assert packet['contract_sha256'] == sha(ROOT / 'standards/behavior_acceptance.json')
assert packet['source_runs_sha256'] == sha(out / 'fresh_runs_unreviewed.json')
assert packet['source_transcripts_sha256'] == sha(out / 'fresh_transcripts.json')
reviews = {r['scenario_id']: r for r in packet['results']}
checks = []
for run in runs:
    ident = run['scenario_id']
    assert hashlib.sha256(run['actual_answer'].encode()).hexdigest() == run['answer_sha256']
    assert canonical_sha256(transcripts[ident]['visible_assistant_messages']) == run['execution']['visible_messages_sha256']
    if ident not in reviews:
        continue
    review = reviews[ident]
    assert review['independent'] is True
    assert review['answer_sha256'] == run['answer_sha256']
    assert review['visible_messages_sha256'] == run['execution']['visible_messages_sha256']
    bound = copy.deepcopy(run)
    bound['review'] = review
    checks.append(evaluate_run(bound, contract, root=ROOT, verify_project=True))
before = read(BASE / 'before_sha256.json')
unchanged = {name: sha(ROOT / name) == before[name] for name in ['AGENTS.md', 'work/register.json', 'context/current.json', 'context/decisions.md']}
assert all(unchanged.values())
state = {
    'saved_at': datetime.now(timezone.utc).isoformat(),
    'round': 2, 'contract_version': contract['version'],
    'candidate_status': 'CANDIDATE',
    'aggregate_acceptance': 'PENDING_INDEPENDENT_REVIEW',
    'actual_responses_saved': len(runs),
    'independently_reviewed_count': len(checks),
    'reviewed_results': checks,
    'pending_review_scenarios': [r['scenario_id'] for r in runs if r['scenario_id'] not in reviews],
    'snapshot_files_verified': len(snapshot),
    'snapshot_drift': drift,
    'scenario_and_professional_criteria_unchanged': True,
    'protected_operational_files_unchanged': unchanged,
    'ui_metadata_rendering': 'UNVERIFIED',
    'blocker': 'Independent review agents stopped at account usage limit. No missing judgment substituted by the primary agent.',
    'resume': 'Review only pending_review_scenarios against saved round2 captures; do not regenerate responses. Save round2/reviews_daily.json, then run finalize_remediation.py --round 2 and native acceptance checker.',
}
(out / 'REVIEW_CHECKPOINT.json').write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(state, ensure_ascii=False))
