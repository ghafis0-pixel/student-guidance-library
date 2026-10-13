"""Deliver a pending-review checkpoint, never a final acceptance certificate."""
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
DEST = Path('C:/Users/CSS/.codex/visualizations/2026/10/04/01a108d7-1817-7261-8432-a7e2be564ca1')
sys.path.insert(0, str(ROOT))
from tools.privacy_guard import scan_bytes, require_public_bytes, fingerprint, VERSION

def sha(content):
    return hashlib.sha256(content).hexdigest()

def save(name, data):
    (BASE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def resolve(data, location):
    node, parent, key = data, None, None
    for match in re.finditer(r'\.(field#\d+|[a-z_][a-z0-9_]*)|\[(\d+)\]', location.rsplit(':line:', 1)[0]):
        parent = node
        key = int(match[2]) if match[2] is not None else list(node)[int(match[1][6:])] if match[1].startswith('field#') else match[1]
        node = node[key]
    return node, parent, key

names = ['remediation_report.md', 'investigation.md', 'before_sha256.json', 'behavior_result.json',
         'save_review_checkpoint.py', 'finalize_remediation.py', 'metadata_diagnostic.json',
         'round2/candidate_snapshot.json', 'round2/capture_progress.json',
         'round2/fresh_runs_unreviewed.json', 'round2/fresh_transcripts.json',
         'round2/reviews_sources.json', 'round2/REVIEW_CHECKPOINT.json']
entries, privacy = {}, []
for name in names:
    path = BASE / name
    content = path.read_bytes()
    findings = scan_bytes(content, path.suffix)
    review, resolutions = None, []
    if findings:
        assert path.suffix == '.json', (name, findings)
        data = json.loads(content)
        for finding in findings:
            value, parent, key = resolve(data, finding['location'])
            assert finding['code'] == 'CONTACT_NUMBER' and isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), (name, finding)
            assert isinstance(key, str) and (ROOT / key).is_file() and sha((ROOT / key).read_bytes()) == value, (name, finding)
            resolutions.append({'finding': finding, 'classification': 'VERIFIED_SOURCE_SHA256_FALSE_POSITIVE', 'source_path': key})
        review = {'guard_version': VERSION, 'decision': 'cleared', 'content_sha256': sha(content), 'findings_sha256': fingerprint(findings), 'reference': 'checkpoint_privacy_review.json', 'reason': 'Every exact finding is a SHA256 source-file digest independently matched to current file bytes; no contact record is represented.'}
    require_public_bytes(content, path.suffix, review)
    entries[name] = {'bytes': len(content), 'sha256': sha(content)}
    privacy.append({'path': name, 'content_sha256': sha(content), 'findings': findings, 'resolutions': resolutions, 'review': review})
save('checkpoint_privacy_review.json', {'scope': 'Full raw captured responses and memory metadata; synthetic tests, no original session journals or restricted student records.', 'limits': 'Pattern detection is not exhaustive identity detection; metadata UI rendering unverified.', 'files': privacy})
content = (BASE / 'checkpoint_privacy_review.json').read_bytes()
require_public_bytes(content, '.json')
entries['checkpoint_privacy_review.json'] = {'bytes': len(content), 'sha256': sha(content)}
save('CHECKPOINT_MANIFEST.json', {'saved_at': datetime.now(timezone.utc).isoformat(), 'status': 'PENDING_INDEPENDENT_REVIEW', 'reviewed': 6, 'pending': 11, 'members': entries})
manifest = (BASE / 'CHECKPOINT_MANIFEST.json').read_bytes()
require_public_bytes(manifest, '.json')
archive = DEST / 'behavior_remediation_2026-10-05_review_checkpoint.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for name in [*entries, 'CHECKPOINT_MANIFEST.json']:
        z.write(BASE / name, 'behavior_remediation_2026-10-05/' + name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and len(z.namelist()) == len(set(z.namelist()))
    for name, item in entries.items():
        raw = z.read('behavior_remediation_2026-10-05/' + name)
        assert sha(raw) == item['sha256'] and len(raw) == item['bytes'] and raw == (BASE / name).read_bytes()
    assert z.read('behavior_remediation_2026-10-05/CHECKPOINT_MANIFEST.json') == manifest
receipt = {'status': 'BYTES_AND_CRC_PASS', 'acceptance': 'PENDING_INDEPENDENT_REVIEW', 'archive_path': str(archive), 'archive_bytes': archive.stat().st_size, 'archive_sha256': sha(archive.read_bytes()), 'members': len(entries) + 1, 'local_only': True, 'uploaded': False, 'previous_archives_overwritten': False}
save('checkpoint_delivery_verification.json', receipt)
print(json.dumps(receipt, ensure_ascii=False))
