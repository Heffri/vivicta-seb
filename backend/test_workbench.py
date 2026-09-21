"""Run with python test_workbench.py. Isolated files, no network or PDFs."""
import copy
import csv
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pptx import Presentation
import app
from pipeline import kb, workbench, ppt

def statement(section, year=2025):
    schema = app.load_schema(section)
    values = dict(revenue=100, cost_of_sales=-60, gross_profit=40, operating_profit=30, profit_before_tax=25, income_tax=-5, profit_discontinued=0, net_profit=20, total_debt=100, due_within_1_year=20, due_1_to_5_years=50, due_after_5_years=30)
    fields = [dict(key=f['key'], label=f['label'], value=values.get(f['key'], 10), unit='MSEK', period=str(year), raw_label=f['label'], source={'page': 1, 'quote': f['label']}, confidence=0, evidence=[], human_review={'decision': 'confirmed', 'reviewer': 'Analyst', 'at': 'now', 'note': 'Source checked'}) for f in schema['fields']]
    basis = dict(entity='Atlas Copco AB', consolidation='Group', period=str(year), currency='SEK', scale='Millions', source='Page 1, group statement', restatement='As reported', debt_basis='Carrying amounts', leases='Included', bucket_mapping='Under 1, 1 to 5, over 5')
    return dict(report_id=f'lib-test_{year}', stem=f'test_{year}', company='Atlas Copco AB', fiscal_year=year, section=section, currency='MSEK', fields=fields, checks=[], warnings=[], basis={'values': {k: basis[k] for k in workbench.required(section)}, 'reviewer': 'Analyst', 'note': 'Confirmed against source', 'at': 'now'})

for section in ('income_statement', 'debt_maturity'):
    x = statement(section)
    schema = app.load_schema(section)
    assert workbench.decorate(x, schema)['ready']
    x['fields'][0]['value'] = None
    workbench.decorate(x, schema)
    assert not x['ready'] and any(c['status'] == 'unavailable' for c in x['checks'])
    x = statement(section)
    x['fields'][0]['unit'] = 'EUR'
    assert any(c['status'] == 'unavailable' for c in workbench.checks(x, schema))
    x = statement(section)
    x['fields'][0]['period'] = '2024'
    assert any(c['status'] == 'unavailable' for c in workbench.checks(x, schema))
    current, previous = statement(section), statement(section, 2024)
    current['fields'][0]['value'], previous['fields'][0]['value'] = 20, -10
    row = workbench.compare(current, previous)['rows'][0]
    assert row['delta'] == 30 and row['percent'] == 300 and row['sign_change']
    previous['fields'][0]['value'] = 0
    assert workbench.compare(current, previous)['rows'][0]['percent'] is None
    previous['basis']['values']['scale'] = 'Thousands'
    assert workbench.compare(current, previous)['rows'][0]['delta'] is None
    previous.pop('basis')
    assert workbench.compare(current, previous)['rows'][0]['delta'] is None

with tempfile.TemporaryDirectory() as tmp, patch('pipeline.fetch.fetch_report', side_effect=AssertionError('PDF download forbidden')):
    os.environ['KB_DIR'] = tmp
    for year in (2025, 2024, 2023):
        stem = f'test_{year}'
        folder = Path(tmp) / stem
        folder.mkdir()
        (folder / 'meta.json').write_text(json.dumps(dict(company='Atlas Copco AB', fiscal_year=year, pages=1, filename=stem+'.pdf')))
        (folder / 'pages.jsonl').write_text(json.dumps({'page': 1, 'text': 'Saved statement text'}) + '\n')
        for section in ('income_statement', 'debt_maturity'):
            kb.save_extraction(stem, section, workbench.decorate(statement(section, year), app.load_schema(section)))
    x = app.kb_extraction('test_2025', 'debt_maturity')
    assert x['ready'] and not x['pdf_available']
    assert app.review_queue() == []
    assert app.comparison('test_2025', 'debt_maturity')['previous_year'] == 2024
    assert app.comparison('test_2025', 'debt_maturity', 'test_2023')['previous_year'] == 2023
    field = copy.deepcopy(x['fields'][0])
    changed = app.review_field(x['report_id'], app.ReviewBody(section=x['section'], key=field['key'], expected=field, decision='corrected', reviewer='Tester', note='Page 1 correction', value=200, unit='MSEK', period='2025'))
    assert changed['checks'][0]['status'] == 'failed' and changed['check_history'][-1]['previous'][0]['passed']
    assert any(i['kind'] == 'check' for i in app.review_queue())
    corrected = app.review_field(x['report_id'], app.ReviewBody(section=x['section'], key=field['key'], expected=changed['fields'][0], decision='corrected', reviewer='Tester', note='Rechecked page 1', value=100, unit='MSEK', period='2025'))
    assert corrected['ready']
    body = app.BasisBody(section=x['section'], expected=x['basis'], values={**x['basis']['values'], 'leases': 'Excluded'}, reviewer='Tester', note='Debt excludes leases, note 12')
    updated = app.review_basis(x['report_id'], body)
    assert updated['basis_history'][-1]['previous']['values']['leases'] == 'Included'
    try:
        app.review_basis(x['report_id'], body)
        raise AssertionError('stale basis accepted')
    except HTTPException as e:
        assert e.status_code == 409
    app.extractions.clear()
    assert app.kb_extraction('test_2025', 'debt_maturity')['basis'] == updated['basis']
    # Exports bind the selected section, regardless of last section opened.
    rows = list(csv.DictReader(io.StringIO(app.extraction_csv(x['report_id'], 'income_statement', 'test_2024').body.decode())))
    assert all(r['section'] == 'income_statement' for r in rows) and 'basis' in rows[0]
    deck = Presentation(io.BytesIO(app.extraction_pptx(x['report_id'], 'debt_maturity', 'test_2024').body))
    assert len(deck.slides) == 1 and 'previous_stem' in deck.slides[0].notes_slide.notes_text_frame.text
    # Duplicates require an explicit source, and gaps never silently become YoY.
    other = Path(tmp) / 'duplicate_2024'
    other.mkdir()
    for name in ('meta.json', 'pages.jsonl'):
        (other / name).write_bytes((Path(tmp) / 'test_2024' / name).read_bytes())
    kb.save_extraction('duplicate_2024', 'debt_maturity', statement('debt_maturity', 2024))
    assert not app.comparison('test_2025', 'debt_maturity')['rows']
    assert not app.comparison('test_2023', 'debt_maturity')['rows']

# Whole-KB exports deliberately read saved extracts, so this test has no PDF or model dependency.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    library = root / 'reports'
    library.mkdir()
    (library / 'index.json').write_text('[]')
    with patch.dict(os.environ, {'KB_DIR': str(root / 'kb')}), patch.object(app, 'LIBRARY', library), patch.object(app, 'reports', {}), patch.object(app, 'extractions', {}), patch.object(app, 'library_paths', {}):
        for stem, company, reviewed in [('abb_2025', 'ABB Ltd', True), ('ericsson_2025', 'Ericsson', False), ('outside_2025', 'Volvo', False)]:
            x = statement('debt_maturity')
            x.update(stem=stem, report_id=f'lib-{stem}', company=company)
            if not reviewed:
                for field in x['fields']:
                    field.pop('human_review', None)
            kb.save_report(stem, {'company': company, 'fiscal_year': 2025, 'pages': 1, 'sha256': 'test'}, ['Saved statement text'])
            kb.save_extraction(stem, 'debt_maturity', workbench.decorate(x, app.load_schema('debt_maturity')))
        client = TestClient(app.app)
        rows = list(csv.DictReader(io.StringIO(client.get('/api/kb/export.csv?section=debt_maturity&collection=wallenberg').text)))
        assert len(rows) == 2 and {row['stem'] for row in rows} == {'abb_2025', 'ericsson_2025'}
        assert {'company', 'stem', 'review_status', 'human_review', 'ready'} <= set(rows[0])
        abb = next(row for row in rows if row['stem'] == 'abb_2025')
        assert abb['review_status'] == 'confirmed' and abb['human_review'] == 'yes'
        filtered = client.get('/api/kb/export.csv?section=debt_maturity&collection=all&q=volvo')
        assert filtered.status_code == 200 and [row['stem'] for row in csv.DictReader(io.StringIO(filtered.text))] == ['outside_2025']
        deck = Presentation(io.BytesIO(client.get('/api/kb/export.pptx?section=debt_maturity&collection=wallenberg').content))
        assert len(deck.slides) == 3
        assert any(shape.has_table and shape.table.cell(0, 0).text == 'Company' for shape in deck.slides[0].shapes)

# Deterministic rendered fixtures for visual review, outside the repository.
for section in ('income_statement', 'debt_maturity'):
    x = statement(section)
    workbench.decorate(x, app.load_schema(section))
    if section == 'income_statement':
        x.pop('basis')
        workbench.decorate(x, app.load_schema(section))
    x['comparison'] = workbench.compare(x, statement(section, 2024))
    Path(tempfile.gettempdir(), f'arp-{section}.pptx').write_bytes(ppt.build_pptx(x))
print('Workbench checks passed: both statements, strict arithmetic, audit history, conflicts, queue, single and whole-KB exports, and no downloads')
