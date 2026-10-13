"""Portable full review copies: preserve bytes, validate data and close dependencies.

Privacy review is separate and must resolve findings before distribution. This tool
never rewrites source bytes or suppresses the project's integrity checker.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

VERSION = '2.0.0'
EXCLUDED_PARTS = {'.git', '__pycache__', 'tmp', 'temp', 'private', 'restricted',
                  'sensitive', 'student-data', '.codex', '.agents', '.aws',
                  'node_modules', '.venv', 'extracted_text'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.tmp', '.bak', '.key', '.pem', '.pfx'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(value: str) -> str:
    name = PurePosixPath(value)
    if (not value or '\\' in value or name.is_absolute() or name.as_posix() != value
            or any(p in {'.', '..'} or ':' in p for p in name.parts)):
        raise ValueError('unsafe review member')
    return value


def excluded(value: str) -> bool:
    name = PurePosixPath(value)
    return (any(part.lower() in EXCLUDED_PARTS for part in name.parts)
            or name.suffix.lower() in EXCLUDED_SUFFIXES
            or name.name.startswith(('~$', '.env'))
            or name.name.lower() in {'credentials.json', 'auth.json', 'secrets.json'})


def validate_payload(name: str, data: bytes) -> None:
    """Syntax is a distinct stop gate; malformed JSON cannot be cleared as privacy."""
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in {'.json', '.jsonl', '.py'}:
        text = data.decode('utf-8-sig')
        try:
            if suffix == '.json':
                json.loads(text)
            elif suffix == '.jsonl':
                for number, line in enumerate(text.splitlines(), 1):
                    if line.strip():
                        try:
                            json.loads(line)
                        except ValueError:
                            raise ValueError(f'invalid JSONL line {number}') from None
            else:
                ast.parse(text, filename=name)
        except (ValueError, SyntaxError):
            raise ValueError(f'invalid structured data or code: {name}') from None


def project_payloads(root: Path) -> tuple[dict[str, bytes], list[str]]:
    root = root.resolve()
    payloads, omissions = {}, []
    for source in sorted(root.rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(root).as_posix()
        if excluded(relative):
            omissions.append(relative)
            continue
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError('project file resolves outside root')
        safe_name(relative)
        content = source.read_bytes()
        validate_payload(relative, content)
        payloads['project/' + relative] = content
    return payloads, omissions


def verify_dependencies(payloads: dict[str, bytes]) -> dict:
    manifest = json.loads(payloads['project/catalog/manifest.json'])
    registry = json.loads(payloads['project/catalog/source_registry.json'])
    checked = set()
    for entry in manifest['files']:
        name = 'project/' + safe_name(entry['path'])
        if name not in payloads or sha(payloads[name]) != entry['sha256']:
            raise ValueError('missing or changed manifest dependency: ' + name)
        checked.add(name)
    for entry in registry['sources']:
        name = 'project/' + safe_name(entry['archive_path'])
        if name not in payloads or sha(payloads[name]) != entry['sha256']:
            raise ValueError('missing or changed source dependency: ' + name)
        checked.add(name)
    return {'manifest_files': len(manifest['files']), 'source_records': len(registry['sources']),
            'distinct_dependency_files': len(checked), 'status': 'PASS'}


def build(root: Path, extras: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError('refusing to replace an existing archive')
    payloads, omissions = project_payloads(root)
    dependencies = verify_dependencies(payloads)
    for source in sorted(extras.rglob('*')):
        if not source.is_file():
            continue
        rel = safe_name(source.relative_to(extras).as_posix())
        if excluded(rel) or source.is_symlink():
            raise ValueError('extra evidence is outside share scope')
        if rel == 'REVIEW_MANIFEST.json' or rel.startswith('project/'):
            raise ValueError('evidence cannot replace project or manifest')
        data = source.read_bytes()
        validate_payload(rel, data)
        payloads[rel] = data
    entries = [{'path':name, 'size':len(data), 'source_sha256':sha(data),
                'shared_sha256':sha(data), 'transformation':'NONE_BYTE_EXACT'}
               for name, data in sorted(payloads.items())]
    manifest = {'schema_version':'2.0', 'builder_version':VERSION,
                'copy_policy':'Byte-exact; no regex sanitization of code/data/answers/URLs.',
                'dependency_closure':dependencies, 'excluded_project_files':omissions, 'files':entries}
    payloads['REVIEW_MANIFEST.json'] = (json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for name,data in sorted(payloads.items()):
                z.writestr(name,data)
        result = verify(output)
    except Exception:
        # Only a newly created incomplete output is removed; source is untouched.
        output.unlink(missing_ok=True)
        raise
    return result


def verify(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if z.testzip() is not None or len(names) != len(set(names)):
            raise ValueError('CRC or duplicate failure')
        if any(excluded(safe_name(n)) for n in names):
            raise ValueError('excluded member in archive')
        manifest=json.loads(z.read('REVIEW_MANIFEST.json'))
        paths=[e['path'] for e in manifest['files']]
        if len(paths)!=len(set(paths)) or set(names)!=set(paths)|{'REVIEW_MANIFEST.json'}:
            raise ValueError('membership differs from manifest')
        payloads={}
        for entry in manifest['files']:
            name=entry['path']; data=z.read(name)
            if (entry['shared_sha256']!=sha(data) or entry['source_sha256']!=sha(data)
                    or entry['size']!=len(data) or entry['transformation']!='NONE_BYTE_EXACT'):
                raise ValueError('byte identity or manifest hash mismatch')
            validate_payload(name,data)
            payloads[name]=data
        dependencies=verify_dependencies(payloads)
    return {'status':'STRUCTURE_AND_BYTES_PASS', 'privacy_status':'REQUIRES_SCOPED_REVIEW',
            'zip_sha256':sha(path.read_bytes()), 'size':path.stat().st_size,
            'members':len(names), 'dependencies':dependencies,
            'limits':'CRC, hashes and syntax are not functional, privacy or conversation acceptance.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path)
    parser.add_argument('--extras',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify',type=Path)
    args=parser.parse_args()
    if args.verify:
        result=verify(args.verify)
    else:
        if not args.root or not args.extras or not args.output:
            parser.error('--root --extras --output required')
        result=build(args.root,args.extras,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
