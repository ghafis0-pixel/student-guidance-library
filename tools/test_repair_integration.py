"""Regression checks for active consumers and derived source metadata (not chat acceptance)."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepairIntegrationTests(unittest.TestCase):
    def test_dec016_active_work_instruction(self):
        item = json.loads((ROOT / 'work/register.json').read_text('utf-8'))['items'][0]
        self.assertNotIn('تسجل أولًا', item['next_action'])
        self.assertIn('DEC-016', item['decision_refs'])
        self.assertEqual(item['execution_status'], 'not_reported')
        self.assertEqual(item['approval']['reference'], 'DEC-014')

    def test_dec016_noor_matrix_both_views(self):
        matrix = json.loads((ROOT / 'catalog/records_noor_decision_matrix.json').read_text('utf-8'))
        row = next(x for x in matrix['records'] if x['record_id'] == 'R-025')
        self.assertNotIn('تسجيل الموقف أولًا', row['operational_rule'])
        view = (ROOT / 'catalog/records_noor_decision_matrix.md').read_text('utf-8')
        self.assertNotIn('يسجل أولًا', view)
        self.assertIn('عند أثر تشغيلي', row['operational_rule'])

    def test_active_procedural_consumers_point_full_source(self):
        rules = json.loads((ROOT / 'standards/weekly_plan_gate_rules.yaml').read_text('utf-8'))
        sources = json.loads((ROOT / 'catalog/source_registry.json').read_text('utf-8'))['sources']
        full = next(x for x in sources if x['source_id'] == 'REF-PROCEDURAL-FULL-1446')
        self.assertEqual(rules['reference_catalog']['PROCEDURAL_GUIDE'], full['reference_path'])
        reading = (ROOT / 'catalog/core_guides_reading_map.md').read_text('utf-8')
        self.assertIn('REF-PROCEDURAL-FULL-1446', reading)
        self.assertIn('تاريخي', reading)

    def test_chunk_metadata_current_and_bound_without_altering_text(self):
        registry_path = ROOT / 'catalog/source_registry.json'
        registry = json.loads(registry_path.read_text('utf-8'))
        sources = {s['source_id']: s for s in registry['sources']}
        registry_hash = hashlib.sha256(registry_path.read_bytes()).hexdigest()
        matrix_path = ROOT / 'catalog/records_noor_decision_matrix.json'
        templates = {v['record_id']: v for v in json.loads(matrix_path.read_text('utf-8'))['records']}
        count = 0
        for path in sorted((ROOT / 'chunks').glob('*.jsonl')):
            for line_number, line in enumerate(path.read_text('utf-8').splitlines(), 1):
                row = json.loads(line)
                if row['source_id'] in sources:
                    source = sources[row['source_id']]
                else:
                    template = templates[row['source_id']]
                    source = {'status': template['decision_code'], 'source_type': 'template',
                              'sha256': hashlib.sha256((ROOT/template['original_path']).read_bytes()).hexdigest(),
                              'text_status': 'legacy_template_extraction_unverified'}
                with self.subTest(file=path.name, line=line_number):
                    self.assertEqual(row['status'], source['status'])
                    self.assertEqual(row['source_type'], source['source_type'])
                    self.assertEqual(row.get('metadata_binding', {}).get('registry_sha256'), registry_hash)
                    self.assertEqual(row.get('metadata_binding', {}).get('source_sha256'), source['sha256'])
                    self.assertEqual(row.get('extraction_quality'), source['text_status'])
                    self.assertTrue(row.get('text'))
                count += 1
        self.assertGreater(count, 0)

    def test_history_and_approved_plan_remain_unchanged(self):
        # Specific already-approved plan and superseded decision text remain evidence.
        path = ROOT / 'outputs/weekly_plans/2026-10-04_to_2026-10-08/weekly_plan_2026-10-04_adhd.docx'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         '3cb29234e362218cb547865cdce856211873ae909d084859a48e2e8070f8c0d0')
        decisions = (ROOT / 'context/decisions.md').read_text('utf-8')
        old = decisions.split('## DEC-009', 1)[1].split('## DEC-010', 1)[0]
        self.assertIn('تسجيله أولًا', old)
        self.assertIn('مستبدل', old)


if __name__ == '__main__':
    unittest.main()
