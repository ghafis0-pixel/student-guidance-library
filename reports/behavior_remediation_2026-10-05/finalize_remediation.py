"""Bind independently saved review files to exact captures; report real failures."""
import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT))

def save(out, name, value):
    (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--round', type=int, choices=[1, 2], required=True)
    args = parser.parse_args()
    out = BASE if args.round == 1 else BASE / 'round2'
    checker = BASE / 'before_round2/check_behavior_acceptance.py' if args.round == 1 else ROOT / 'tools/check_behavior_acceptance.py'
    contract_path = BASE / 'before_round2/behavior_acceptance.json' if args.round == 1 else ROOT / 'standards/behavior_acceptance.json'
    spec = importlib.util.spec_from_file_location('bound_checker', checker)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = json.loads(contract_path.read_text(encoding='utf-8-sig'))
    source = json.loads((out / 'fresh_runs_unreviewed.json').read_text(encoding='utf-8'))
    transcripts = json.loads((out / 'fresh_transcripts.json').read_text(encoding='utf-8'))
    reviews = {}
    for name in ['reviews_sources.json', 'reviews_daily.json']:
        packet = json.loads((out / name).read_text(encoding='utf-8'))
        for review in packet['results']:
            ident = review['scenario_id']
            if ident in reviews:
                raise RuntimeError('Duplicate independent review: ' + ident)
            reviews[ident] = review
    expected = {s['id'] for s in contract['scenarios']}
    if set(reviews) != expected or {r['scenario_id'] for r in source['runs']} != expected:
        raise RuntimeError('All seventeen exact captures and independent reviews are required')
    runs = copy.deepcopy(source['runs'])
    professional = []
    for run in runs:
        ident = run['scenario_id']
        review = reviews[ident]
        if review['answer_sha256'] != run['answer_sha256'] or review['visible_messages_sha256'] != run['execution']['visible_messages_sha256']:
            raise RuntimeError('Independent review hash mismatch: ' + ident)
        if module.canonical_sha256(transcripts[ident]['visible_assistant_messages']) != review['visible_messages_sha256']:
            raise RuntimeError('Visible-message mismatch: ' + ident)
        run['review'] = review
        scenario = next(s for s in contract['scenarios'] if s['id'] == ident)
        required = {c['id'] for c in scenario['criteria']}
        status = 'PASS' if all(c['status'] == 'PASS' for c in review['criteria'] if c['id'] in required) else 'FAIL'
        professional.append({'scenario_id': ident, 'status': status})
    result = module.evaluate_runs(runs, contract, root=ROOT, verify_project=args.round == 2)
    result['round'] = args.round
    result['counts'] = dict(Counter(r['status'] for r in result['results']))
    result['professional_counts'] = dict(Counter(r['status'] for r in professional))
    result['professional_results'] = professional
    result['live_project_hash_verification'] = args.round == 2
    result['ui_metadata_rendering'] = 'UNVERIFIED'
    result['old_answers_and_reviews_unchanged'] = True
    result['candidate_status'] = 'CANDIDATE' if result['status'] != 'PASS' else 'BEHAVIOR_ACCEPTANCE_PASS_PENDING_USER_ADOPTION'
    save(out, 'fresh_runs_reviewed.json', {'runs': runs})
    save(out, 'behavior_result.json', result)
    print(json.dumps({'round': args.round, 'status': result['status'], 'counts': result['counts'], 'professional_counts': result['professional_counts'], 'live_project_hash_verification': args.round == 2}))

if __name__ == '__main__':
    main()
