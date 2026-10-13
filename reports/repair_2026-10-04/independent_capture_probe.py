"""Check captured answer and encrypted dispatch references against local session logs.

No decryption, answer rewriting, project writes or plaintext input reconstruction.
"""
import hashlib
import json
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
SESSIONS = Path(r'C:/Users/CSS/.codex/sessions/2026/10/04')

def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def canonical(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')))

root_file = SESSIONS / 'rollout-2026-10-04T12-06-01-01a10629-bdcb-70b2-8517-d6d009499fe9.jsonl'
dispatches = {}
for line in root_file.open(encoding='utf-8'):
    row = json.loads(line)
    q = row.get('payload', {})
    if row['type'] == 'response_item' and q.get('type') == 'function_call' and q.get('name') in {'spawn_agent', 'followup_task'}:
        # Parsing the argument envelope is not decrypting the message string.
        args = json.loads(q['arguments'])
        agent = '/root/' + args['task_name'] if q['name'] == 'spawn_agent' else args['target']
        if not agent.startswith('/root/'):
            agent = '/root/' + agent
        dispatches[q['call_id']] = {'agent': agent, 'sha256': sha(args['message']),
                                    'is_encrypted': args['message'].startswith('gAAAAA'),
                                    'timestamp': row['timestamp'], 'method': q['name'],
                                    'fork_turns': args.get('fork_turns')}

sessions = {}
result = {'rounds': {}, 'limits': 'All answer bytes verified against local actual session messages. Dispatch envelope, target and ciphertext hash verified; encrypted prompt plaintext was not available and no decryption was attempted. Operator scenario assignment is not independently verified plaintext.'}
for round_name in ('historical', 'current'):
    runs_path = EVIDENCE / f'{round_name}_behavior_runs_unreviewed.json'
    transcript_path = EVIDENCE / f'{round_name}_behavior_transcripts.json'
    runs = json.loads(runs_path.read_text('utf-8'))['runs']
    transcripts = json.loads(transcript_path.read_text('utf-8'))
    checked = []
    fresh_contexts = []
    for run in runs:
        ident = run['scenario_id']
        transcript = transcripts[ident]
        path = SESSIONS / transcript['session_file']
        if path.name not in sessions:
            session_rows = [json.loads(line) for line in path.read_text('utf-8').splitlines()]
            meta = session_rows[0]['payload']
            turns = {}
            current_turn = None
            ordinal = -1
            for row in session_rows:
                q = row.get('payload', {})
                if row['type'] == 'event_msg' and q.get('type') == 'task_started':
                    ordinal += 1
                    current_turn = {'ordinal': ordinal, 'messages': [], 'users': [], 'completed_at': None}
                    turns[q['turn_id']] = current_turn
                if current_turn is None:
                    continue
                if row['type'] == 'response_item' and q.get('type') == 'message':
                    text = ''.join(v.get('text', '') for v in q.get('content', []) if v.get('type') in {'output_text', 'input_text', 'text'})
                    if text and q.get('role') == 'assistant':
                        current_turn['messages'].append(text)
                    if text and q.get('role') == 'user':
                        current_turn['users'].append(text)
                if row['type'] == 'event_msg' and q.get('type') == 'task_complete':
                    current_turn['completed_at'] = row['timestamp']
            sessions[path.name] = {'meta': meta, 'turns': turns}
        session = sessions[path.name]
        turn = session['turns'][transcript['turn_id']]
        assert session['meta']['id'] == transcript['context_id'] == run['execution']['context_id'], ident
        assert session['meta']['source']['subagent']['thread_spawn']['agent_path'] == transcript['agent_path'], ident
        assert turn['messages'] == transcript['visible_assistant_messages'], ident
        assert turn['users'] == transcript['actual_user_messages'], ident
        assert turn['messages'][-1] == transcript['final_answer'] == run['actual_answer'], ident
        assert sha(run['actual_answer']) == run['answer_sha256'], ident
        assert canonical(turn['messages']) == run['execution']['visible_messages_sha256'], ident
        assert turn['completed_at'] == run['execution']['captured_at'] == transcript['captured_at'], ident
        assert (turn['ordinal'] == 0) == run['execution']['isolated'], ident
        record = transcript['dispatch']
        dispatch = dispatches[record['dispatch_call_id']]
        assert record['root_session_file'] == root_file.name, ident
        assert dispatch['agent'] == transcript['agent_path'], ident
        assert dispatch['method'] == record['method'] and dispatch['timestamp'] == record['timestamp'], ident
        assert dispatch['fork_turns'] == record['fork_turns'], ident
        assert dispatch['is_encrypted'] and record['actual_prompt'] is None, ident
        assert dispatch['sha256'] == record['encrypted_payload_sha256'] == run['execution']['encrypted_input_sha256'], ident
        assert record['prompt_plaintext_status'] == run['execution']['input_plaintext_status'] == 'NOT_AVAILABLE_IN_LOCAL_LOG', ident
        assert record['operator_recorded_scenario_text'] == run['scenario_text'], ident
        if run['execution']['isolated']:
            assert dispatch['method'] == 'spawn_agent' and dispatch['fork_turns'] == 'none', ident
            fresh_contexts.append(run['execution']['context_id'])
        checked.append({'scenario_id': ident, 'answer_sha256': run['answer_sha256'],
                        'visible_message_count': len(turn['messages']), 'session_answer_bytes_verified': True,
                        'dispatch_target_and_ciphertext_verified': True, 'input_plaintext_verified': False})
    assert len(fresh_contexts) == len(set(fresh_contexts)) == 7, round_name
    result['rounds'][round_name] = {'verified_answers': checked, 'fresh_distinct_contexts': len(fresh_contexts),
                                  'runs_sha256': hashlib.sha256(runs_path.read_bytes()).hexdigest(),
                                  'transcripts_sha256': hashlib.sha256(transcript_path.read_bytes()).hexdigest()}
(EVIDENCE / 'independent_capture_probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(json.dumps({'historical_verified': len(result['rounds']['historical']['verified_answers']),
                  'current_verified': len(result['rounds']['current']['verified_answers']),
                  'fresh_distinct_contexts_each_round': 7, 'input_plaintext_verified': False}, indent=2))
