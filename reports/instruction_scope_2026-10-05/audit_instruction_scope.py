"""Audit and back up instruction consolidation; never alter operational data."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
GLOBAL = Path('C:/Users/CSS/.codex/AGENTS.md')
BACKUP = Path('C:/Users/CSS/.codex/visualizations/2026/10/04/01a108d7-1817-7261-8432-a7e2be564ca1/instruction_scope_2026-10-05')
PRIMARY = ['AGENTS.md', 'guide/workflow.md', 'context/current.json']
PROTECTED = ['context/decisions.md', 'work/register.json', 'standards/behavior_acceptance.json']

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON key: ' + key)
        obj[key] = value
    return obj

parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=['before', 'after'], required=True)
args = parser.parse_args()
texts, hashes, issues, links = {}, {}, [], []
for relative in PRIMARY + PROTECTED:
    raw = (ROOT / relative).read_bytes()
    text = raw.decode('utf-8-sig', errors='strict')
    texts[relative], hashes[relative] = text, sha(raw)
    if '\x00' in text or '\ufffd' in text or re.search(r'^(?:<<<<<<<|=======|>>>>>>>)', text, re.M):
        issues.append('Encoding or merge marker: ' + relative)
    if relative.endswith('.json'):
        json.loads(text, object_pairs_hook=unique_object)
    if relative in PRIMARY:
        for target in re.findall(r'`([^`\r\n]+)`', text):
            if '/' not in target or not target.endswith(('.md', '.json', '.py')) or any(c in target for c in '<>* '):
                continue
            exists = (ROOT / target).is_file()
            links.append({'from': relative, 'target': target, 'exists': exists})
            if not exists:
                issues.append('Missing direct reference: ' + relative + ' -> ' + target)
context = json.loads(texts['context/current.json'])
if context['student_count'] != 130 or context['practical_executor_count'] != 1:
    issues.append('Unexpected operational context')
if not all(s in texts['context/decisions.md'] for s in ['DEC-001', 'العدد المعتمد 130']):
    issues.append('Current count decision missing')
if any(re.search(r'(?<!\d)140(?!\d)', texts[name]) for name in PRIMARY):
    issues.append('Old count in primary operational instructions')
receipt = {'checked_at': datetime.now(timezone.utc).isoformat(), 'stage': args.stage,
           'status': 'PASS' if not issues else 'FAIL', 'issues': issues,
           'files_sha256': hashes, 'direct_references': links,
           'student_count': context['student_count'], 'practical_executor_count': context['practical_executor_count'],
           'limits': 'UTF-8, duplicate-key JSON, marker, direct-path and current-state checks; semantic review is documented separately. No fresh Work session or behavioral acceptance is claimed.'}
assert not issues, issues
if args.stage == 'before':
    assert not (BASE / 'before_audit.json').exists(), 'Preserve existing baseline'
    raw = GLOBAL.read_bytes()
    assert not GLOBAL.is_symlink() and b'140 students' in raw
    baseline = json.loads((ROOT / 'reports/behavior_remediation_2026-10-05/round2/candidate_snapshot.json').read_text(encoding='utf-8'))['files']
    receipt['matches_accepted_primary_files'] = {name: hashes[name] == baseline[name] for name in PRIMARY}
    assert all(receipt['matches_accepted_primary_files'].values())
    BACKUP.mkdir(parents=True, exist_ok=True)
    for name, content in [('global_AGENTS.before.txt', raw)] + [(name.replace('/', '_') + '.before.txt', (ROOT / name).read_bytes()) for name in PRIMARY]:
        destination = BACKUP / name
        with destination.open('xb') as stream:
            stream.write(content)
        assert destination.read_bytes() == content
    receipt['global_before_sha256'] = sha(raw)
    receipt['backup_directory'] = str(BACKUP)
else:
    before = json.loads((BASE / 'before_audit.json').read_text(encoding='utf-8'))
    receipt['unchanged_protected_files'] = {name: hashes[name] == before['files_sha256'][name] for name in PROTECTED + ['context/current.json', 'guide/workflow.md']}
    assert all(receipt['unchanged_protected_files'].values())
    receipt['global_file_absent'] = not GLOBAL.exists()
    receipt['global_override_absent'] = not GLOBAL.with_name('AGENTS.override.md').exists()
    receipt['global_backup_matches'] = sha((BACKUP / 'global_AGENTS.before.txt').read_bytes()) == before['global_before_sha256']
    assert receipt['global_file_absent'] and receipt['global_override_absent'] and receipt['global_backup_matches']
    receipt['changed_primary_files'] = [name for name in PRIMARY if hashes[name] != before['files_sha256'][name]]
    receipt['previous_acceptance_scope'] = '17/17 remains historical for the frozen pre-consolidation bytes. Current AGENTS.md differs; do not reuse those hashes as fresh acceptance.'
(BASE / (args.stage + '_audit.json')).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': receipt['status'], 'stage': args.stage, 'student_count': context['student_count'], 'direct_references_checked': len(links), 'issues': issues, 'global_sha256': receipt.get('global_before_sha256'), 'global_file_absent': receipt.get('global_file_absent')}, ensure_ascii=False))
