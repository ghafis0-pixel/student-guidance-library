"""Run native acceptance CLI against saved independent judgments and retain output."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
out = BASE / 'round2'
command = [sys.executable, '-X', 'utf8', '-B', str(ROOT / 'tools/check_behavior_acceptance.py'), '--runs', str(out / 'fresh_runs_reviewed.json')]
result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
receipt = {'checked_at': datetime.now(timezone.utc).isoformat(), 'command': command, 'exit_code': result.returncode, 'stderr': result.stderr}
if result.stdout:
    value = json.loads(result.stdout)
    (out / 'native_acceptance_result.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    receipt['status'] = value['status']
    receipt['scenario_count'] = len(value['results'])
(out / 'native_acceptance_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
raise SystemExit(result.returncode)
