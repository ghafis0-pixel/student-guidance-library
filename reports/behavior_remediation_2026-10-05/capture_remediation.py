"""Additive fresh conversation capture; never rewrite historical answers or reviews."""
import hashlib
import json
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
OUT = BASE
SESSIONS = Path(r'C:\Users\CSS\.codex\sessions\2026\10\05')
sys.path.insert(0, str(ROOT))
from tools.check_behavior_acceptance import canonical_sha256, evaluate_answer

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def rows(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    result = []
    for i, line in enumerate(lines):
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
    return result

def plain(payload):
    return ''.join(v.get('text', '') for v in payload.get('content', []) if v.get('type') in {'input_text', 'output_text', 'text'})

def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--round', type=int, default=1)
    args = parser.parse_args()
    if args.round not in {1, 2}:
        raise ValueError('Only named remediation rounds 1 and 2 are supported')
    OUT = BASE if args.round == 1 else BASE / 'round2'
    OUT.mkdir(exist_ok=True)
    contract = json.loads((ROOT / 'standards/behavior_acceptance.json').read_text(encoding='utf-8-sig'))
    old = json.loads((ROOT / 'reports/behavior_acceptance_2026-10-05/project_before.json').read_text(encoding='utf-8'))
    baseline_path = OUT / 'candidate_snapshot.json'
    if not baseline_path.exists():
        files = {n: sha((ROOT / n).read_bytes()) for n in old['files']}
        save('candidate_snapshot.json', {'files': files, 'snapshot_sha256': canonical_sha256(files), 'contract_version': contract['version']})
    snapshot = json.loads(baseline_path.read_text(encoding='utf-8'))
    for name, digest in snapshot['files'].items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise RuntimeError('Candidate drift: ' + name)
    scenarios = {s['id'][:3].lower(): s for s in contract['scenarios']}
    transcripts = {}
    pending = []
    runs = []
    for path in SESSIONS.glob('*.jsonl'):
        with path.open(encoding='utf-8') as stream:
            first = json.loads(next(stream))
        meta = first.get('payload', {})
        source = meta.get('source', {})
        if not isinstance(source, dict):
            continue
        agent_path = source.get('subagent', {}).get('thread_spawn', {}).get('agent_path', '')
        prefix = r'/root/repair_response_' if args.round == 1 else r'/root/repair2_response_'
        match = re.fullmatch(prefix + r'(b\d\d)', agent_path)
        if not match:
            continue
        scenario = scenarios[match[1]]
        records = rows(path)
        complete = [r for r in records if r['type'] == 'event_msg' and r['payload'].get('type') == 'task_complete' and not r['payload'].get('error')]
        if not complete:
            pending.append({'scenario_id': scenario['id'], 'context_id': meta.get('id'), 'status': 'NOT_RUN', 'reason': 'No completed response at capture time'})
            continue
        # Later review roles in this agent must never enter its first response capture.
        end = records.index(complete[0])
        later_records = len(records) - end - 1
        records = records[:end + 1]
        complete = [complete[0]]
        starts = [r for r in records if r['type'] == 'event_msg' and r['payload'].get('type') == 'task_started']
        if len(starts) != 1 or len(complete) != 1:
            raise RuntimeError('Reused test context: ' + agent_path)
        messages = []
        calls = []
        returns = []
        for r in records:
            p = r.get('payload', {})
            if r['type'] != 'response_item':
                continue
            if p.get('type') == 'message' and p.get('role') == 'assistant':
                messages.append({'phase': p.get('phase'), 'text': plain(p), 'timestamp': r['timestamp']})
            if p.get('type') in {'function_call', 'custom_tool_call'}:
                calls.append({'name': p['name'], 'call_id': p['call_id'], 'input': p.get('arguments', p.get('input', '')), 'timestamp': r['timestamp']})
            if p.get('type') in {'function_call_output', 'custom_tool_call_output'}:
                serialized = json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                returns.append({'call_id': p.get('call_id'), 'payload_sha256': sha(serialized.encode()), 'timestamp': r['timestamp'], 'rubric_text_observed': any(token in serialized for token in ['ASK_DECISION_FACT', 'APPROVAL_BEFORE_SAVE', 'VICE_PRINCIPAL_ROLE', 'common_criteria'])})
        finals = [m for m in messages if m['phase'] in {'final', 'final_answer'}]
        if len(finals) != 1:
            raise RuntimeError('Ambiguous final: ' + agent_path)
        final = finals[0]['text']
        inputs = '\n'.join(c['input'] for c in calls)
        exposed = any(token in inputs for token in ['standards/behavior_acceptance.json', 'behavior_acceptance_2026-10-05', 'behavior_remediation_2026-10-05']) or any(r['rubric_text_observed'] for r in returns)
        ctx = next((r['payload'] for r in records if r['type'] == 'turn_context'), {})
        transcript = {'scenario_id': scenario['id'], 'agent_path': agent_path, 'context_id': meta['id'], 'session_file': path.name, 'visible_assistant_messages': [m['text'] for m in messages], 'assistant_message_records': messages, 'tool_calls': calls, 'tool_return_fingerprints': returns, 'final_answer': final, 'rubric_exposure_observed': exposed, 'input': scenario['prompt'], 'capture_cutoff': complete[0]['timestamp'], 'later_journal_records_excluded': later_records, 'input_policy': 'Exact scenario dispatched by parent with fork_turns=none; no rubric or expected answer supplied. Parent call is separately evidenced in task history; encrypted dispatch payload is not plaintext proof.'}
        transcripts[scenario['id']] = transcript
        files = dict(snapshot['files'])
        for candidate in (ROOT / 'extracted_text').rglob('*'):
            if candidate.is_file() and candidate.relative_to(ROOT).as_posix() in inputs.replace('\\', '/'):
                files[candidate.relative_to(ROOT).as_posix()] = sha(candidate.read_bytes())
        ref = (OUT.relative_to(ROOT) / 'fresh_transcripts.json').as_posix() + '#' + scenario['id']
        runs.append({'schema_version': '1.0', 'scenario_id': scenario['id'], 'scenario_text': scenario['prompt'], 'actual_answer': final, 'answer_sha256': sha(final.encode()), 'project': {'head': old['head'], 'files': files, 'snapshot_sha256': canonical_sha256(files)}, 'execution': {'status': 'NOT_RUN' if exposed else 'RUN', 'reason': 'Rubric exposure observed' if exposed else '', 'kind': 'actual_conversation', 'context_id': meta['id'], 'isolated': True, 'prior_messages_count': 0, 'model': {'name': ctx.get('model', 'unavailable'), 'version': 'exact build unavailable'}, 'tools': sorted({c['name'] for c in calls}), 'captured_at': complete[0]['timestamp'], 'transcript_ref': ref, 'visible_messages_sha256': canonical_sha256([m['text'] for m in messages])}, 'text_issues': evaluate_answer(final, scenario)})
        if args.round == 2 and '<oai-mem-citation>' in final:
            memory_calls = [c['call_id'] for c in calls if re.search(r'(?:MEMORY\.md|[./\\]memories[./\\])', c['input'], re.IGNORECASE)]
            if memory_calls:
                runs[-1]['execution']['required_host_metadata'] = {'kind': 'mandatory_memory_citation', 'memory_read_call_ids': memory_calls}
                runs[-1]['text_issues'] = evaluate_answer(final, scenario, required_memory_metadata=True)
    runs.sort(key=lambda r: r['scenario_id'])
    save('fresh_transcripts.json', transcripts)
    save('fresh_runs_unreviewed.json', {'runs': runs})
    save('capture_progress.json', {'completed': len(runs), 'pending': pending, 'scenarios_not_captured': [s['id'] for s in contract['scenarios'] if s['id'] not in transcripts], 'candidate_status': 'CANDIDATE', 'semantic_acceptance': 'NOT_RUN', 'captured_at': datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'completed': len(runs), 'pending': len(pending), 'rubric_exposures': sum(t['rubric_exposure_observed'] for t in transcripts.values())}))

if __name__ == '__main__':
    main()
