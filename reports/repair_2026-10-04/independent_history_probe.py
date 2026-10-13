"""Read-only preservation and metadata verification against captured pre-repair snapshot."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(r'C:/Users/CSS/Documents/Codex/2026-09-27/new-chat/student-guidance-library')
SNAPSHOT = ROOT.parent / 'work/repair-2026-10-04/rollback_full_local.zip'
before = json.loads((SNAPSHOT.parent / 'before_manifest.json').read_text('utf-8'))
hashes = {row['path']: row['sha256'] for row in before['files']}
changed = []
missing = []
for relative, checksum in hashes.items():
    if relative.startswith('.git/'):
        continue
    path = ROOT / relative
    if not path.is_file():
        missing.append(relative)
    elif hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        changed.append(relative)
chunk_checks = []
with zipfile.ZipFile(SNAPSHOT) as archive:
    for path in sorted((ROOT / 'chunks').glob('*.jsonl')):
        relative = path.relative_to(ROOT).as_posix()
        old = [json.loads(line) for line in archive.read(relative).decode('utf-8-sig').splitlines() if line.strip()]
        new = [json.loads(line) for line in path.read_text('utf-8').splitlines() if line.strip()]
        same = len(old) == len(new) and all(a.get('text') == b.get('text') and a.get('chunk_id') == b.get('chunk_id') for a, b in zip(old, new))
        chunk_checks.append({'path': relative, 'before_records': len(old), 'after_records': len(new), 'same_text_and_ids': same})
report = {'before_head': before['head'], 'missing_before_files': missing, 'changed_before_files': changed,
          'history_reports_changed': [p for p in changed if p.startswith('reports/')],
          'approved_plan_changed': [p for p in changed if p.startswith('outputs/weekly_plans/2026-10-04_to_2026-10-08/')],
          'context_decisions_changed': 'context/decisions.md' in changed, 'chunks': chunk_checks,
          'source_hashes': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in [
              'tools/check_weekly_plan_gate.py', 'tools/check_work_register.py', 'tools/privacy_guard.py',
              'tools/build_delivery.py', 'tools/check_behavior_acceptance.py', 'AGENTS.md', 'guide/workflow.md',
              'standards/weekly_plan_gate_rules.yaml', 'standards/behavior_acceptance.json',
              'work/register.json', 'reports/repair_2026-10-04/current_design_assessment.json',
              'reports/repair_2026-10-04/current_gate_result.json']}}
serialized = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
Path(__file__).with_suffix('.json').write_text(serialized, encoding='utf-8')
print(serialized)
