"""Refresh retrieval metadata from its existing owners; never rewrite extracted text."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import os
import tempfile

try:
    from .privacy_guard import require_public_bytes
except ImportError:
    from privacy_guard import require_public_bytes

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proposals(root: Path = ROOT) -> dict[Path, bytes]:
    registry_path = root / 'catalog/source_registry.json'
    matrix_path = root / 'catalog/records_noor_decision_matrix.json'
    registry = json.loads(registry_path.read_text('utf-8'))
    sources = {s['source_id']: s for s in registry['sources']}
    templates = {r['record_id']: r for r in json.loads(matrix_path.read_text('utf-8'))['records']}
    registry_hash, matrix_hash = sha(registry_path), sha(matrix_path)
    source_hashes = {}
    output = {}
    for path in sorted((root / 'chunks').glob('*.jsonl')):
        rows = []
        for line in path.read_text('utf-8').splitlines():
            row = json.loads(line)
            ident = row['source_id']
            binding = {'registry_sha256': registry_hash, 'metadata_schema': '1.0'}
            if ident in sources:
                source = sources[ident]
                source_path = source.get('reference_path') or source['archive_path']
                if source_path not in source_hashes:
                    source_hashes[source_path] = sha(root/source_path)
                actual = source_hashes[source_path]
                if actual != source['sha256']:
                    raise ValueError('source hash differs from registry: ' + ident)
                for field in ('status', 'source_type', 'version', 'year', 'issuer', 'authority_level'):
                    if field in source:
                        row[field] = source[field]
                row['source_file'] = source_path
                row['extraction_quality'] = source['text_status']
                binding.update(source_sha256=actual, source_ref=ident)
            else:
                template = templates[ident]  # Unknown IDs fail, never silently retain stale metadata.
                source_path = template['original_path']
                row.update(status=template['decision_code'], source_type='template', source_file=source_path,
                           extraction_quality='legacy_template_extraction_unverified')
                binding.update(source_sha256=sha(root/source_path), source_ref='REF-RECORDS-ZIP',
                               matrix_sha256=matrix_hash, archive_sha256=sources['REF-RECORDS-ZIP']['sha256'])
            binding['text_sha256'] = hashlib.sha256(row['text'].encode('utf-8')).hexdigest()
            row['metadata_binding'] = binding
            row['extraction_verification'] = 'legacy_text_not_revalidated'
            row['page_numbering'] = 'legacy_page_locator_unverified'
            rows.append(json.dumps(row, ensure_ascii=False, separators=(',', ':')))
        output[path] = ('\n'.join(rows) + ('\n' if rows else '')).encode('utf-8')
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--reviews', type=Path, help='Exact-file privacy review map; never a blanket bypass')
    args = parser.parse_args()
    reviews = json.loads(args.reviews.read_text('utf-8')) if args.reviews else {}
    prepared = proposals()
    changed = [p for p, data in prepared.items() if p.read_bytes() != data]
    receipts = {}
    if args.write:
        # All review decisions checked before any derivative is replaced.
        for p in changed:
            receipts[p.relative_to(ROOT).as_posix()] = require_public_bytes(
                prepared[p], p.suffix, reviews.get(p.relative_to(ROOT).as_posix()))
        for p in changed:
            fd, name = tempfile.mkstemp(prefix='.metadata-', dir=p.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(prepared[p])
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, p)
            finally:
                if Path(name).exists():
                    Path(name).unlink()
    print(json.dumps({'status': 'UPDATED' if args.write else ('STALE' if changed else 'CURRENT'),
                      'files': [p.relative_to(ROOT).as_posix() for p in changed],
                      'text_changed': False, 'privacy_receipts': receipts}, ensure_ascii=False, indent=2))
    return int(bool(changed) and not args.write)


if __name__ == '__main__':
    raise SystemExit(main())
