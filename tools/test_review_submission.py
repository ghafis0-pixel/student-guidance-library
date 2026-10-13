"""Packaging regressions; these do not count as conversation acceptance."""
import json
from pathlib import Path
import tempfile
import unittest

from tools import build_review_submission as shipping


class ReviewSubmissionTests(unittest.TestCase):
    def test_public_urls_and_xml_and_schema_are_valid_and_unchanged(self):
        payloads={
            'checker.py':b'ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}\n',
            'schema.json':b'{"$schema":"https://json-schema.org/draft/2020-12/schema"}',
            'records.jsonl':b'{"text":"https://example.org/path"}\n',
        }
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,data in payloads.items(): (root/name).write_bytes(data)
            actual,ignored=shipping.project_payloads(root)
            self.assertEqual(actual,{'project/'+n:v for n,v in payloads.items()})
            self.assertEqual(ignored,[])

    def test_invalid_escape_in_jsonl_blocks_before_export(self):
        with self.assertRaises(ValueError):
            shipping.validate_payload('regulatory.jsonl',b'{"text":"bad \\[LOCAL_PATH]"}\n')

    def test_syntax_error_in_python_blocks_before_export(self):
        with self.assertRaises(ValueError): shipping.validate_payload('checker.py',b'ns = {\n')

    def test_archive_is_required_and_not_blanket_excluded(self):
        self.assertFalse(shipping.excluded('archive/original_sources/reference.pdf'))
        payloads={
            'project/catalog/manifest.json':json.dumps({'files':[{'path':'archive/source.pdf','sha256':shipping.sha(b'reference')}]}).encode(),
            'project/catalog/source_registry.json':b'{"sources":[]}',
        }
        with self.assertRaises(ValueError): shipping.verify_dependencies(payloads)
        payloads['project/archive/source.pdf']=b'reference'
        self.assertEqual(shipping.verify_dependencies(payloads)['status'],'PASS')

    def test_changed_dependency_is_not_accepted(self):
        payloads={
            'project/catalog/manifest.json':b'{"files":[]}',
            'project/catalog/source_registry.json':json.dumps({'sources':[{'archive_path':'source.pdf','sha256':shipping.sha(b'before')}]}).encode(),
            'project/source.pdf':b'after',
        }
        with self.assertRaises(ValueError): shipping.verify_dependencies(payloads)

    def test_caches_credentials_and_restricted_homes_are_excluded(self):
        for name in ['tools/__pycache__/x.pyc','.git/config','.env','private/record.json','secrets.json']:
            with self.subTest(name=name): self.assertTrue(shipping.excluded(name))
        for name in ['../outside','C:/Users/local','a\\b']:
            with self.subTest(name=name), self.assertRaises(ValueError): shipping.safe_name(name)

    def test_raw_answer_and_hash_preserved_in_copy(self):
        answer='مرجع عام https://www.srca.gov.sa/en/about/faqs/'
        data=json.dumps({'actual_answer':answer,'answer_sha256':shipping.sha(answer.encode())},ensure_ascii=False).encode()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'runs.json').write_bytes(data)
            copied,_=shipping.project_payloads(root)
            self.assertEqual(copied['project/runs.json'],data)
            run=json.loads(copied['project/runs.json'])
            self.assertEqual(shipping.sha(run['actual_answer'].encode()),run['answer_sha256'])


if __name__=='__main__': unittest.main()
