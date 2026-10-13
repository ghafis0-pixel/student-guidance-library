"""Read-only audit of actual Gate binding; mutations only in temporary copies."""
import copy
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(r'C:/Users/CSS/Documents/Codex/2026-09-27/new-chat/student-guidance-library')
sys.path.insert(0, str(ROOT / 'tools'))
import check_weekly_plan_gate as gate
import check_work_register as work

assessment = gate.load_json(ROOT / 'reports/repair_2026-10-04/current_design_assessment.json')
saved = gate.load_json(ROOT / 'reports/repair_2026-10-04/current_gate_result.json')
register = work.load(ROOT / 'work/register.json')
plan_ref = register['items'][0]['gate']['plan_ref']
unbound = ['context/decisions.md', 'catalog/records_noor_decision_matrix.json',
           'work/planning/term1/noor_action_mapping_review_2026-09-30.md']
bound_paths = {entry['path'] for entry in saved['input_fingerprints']}
report = {'original_gate_errors': gate.verify_current_result(assessment, ROOT / plan_ref, saved, root=ROOT),
          'original_register_errors': work.validate_register(register),
          'probe_paths_in_binding': {p: p in bound_paths for p in unbound}, 'probes': []}
with tempfile.TemporaryDirectory(prefix='independent-binding-') as tmp:
    mirror = Path(tmp)
    paths = bound_paths | set(unbound) | {plan_ref}
    for relative in paths:
        target = mirror / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for relative in unbound:
        target = mirror / relative
        original = target.read_bytes()
        if relative == 'context/decisions.md':
            text = original.decode('utf-8')
            old = 'وليس مقدمة تلقائية لكل موقف'
            assert old in text
            modified = text.replace(old, 'وهو مقدمة تلقائية لكل موقف', 1).encode('utf-8')
        elif relative.endswith('.json'):
            data = json.loads(original)
            row = next(r for r in data['records'] if r['record_id'] == 'R-025')
            row['operational_rule'] = 'Synthetic changed governing rule for public mapping audit'
            modified = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        else:
            text = original.decode('utf-8')
            lines = text.splitlines()
            index = next(i for i, line in enumerate(lines) if line.startswith('| S040 |'))
            lines[index] = '| S040 | Synthetic changed program | Synthetic changed action | Synthetic changed Noor program | Synthetic changed Noor action | Synthetic review | Synthetic changed mapping |'
            modified = ('\n'.join(lines) + '\n').encode('utf-8')
        target.write_bytes(modified)
        errors = gate.verify_current_result(assessment, mirror / plan_ref, saved, root=mirror)
        report['probes'].append({'path': relative, 'source_sha256': hashlib.sha256(original).hexdigest(),
                                'changed_sha256': hashlib.sha256(modified).hexdigest(),
                                'current_result_errors': errors,
                                'fresh_status': gate.evaluate(assessment, mirror / plan_ref, root=mirror)['gate_status']})
        target.write_bytes(original)
serialized = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
Path(__file__).with_suffix('.json').write_text(serialized, encoding='utf-8')
print(serialized)
