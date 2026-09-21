"""Run: python test_human_review.py. Uses an isolated temporary KB, no model calls."""
import copy
import io
import json
import os
import tempfile
from pathlib import Path
from fastapi import HTTPException
from pptx import Presentation
import app
from pipeline import kb

with tempfile.TemporaryDirectory() as tmp:
    os.environ['KB_DIR'] = tmp
    f = dict(key='revenue', label='Revenue', value=100, unit='MSEK', period='2025', raw_label='Revenue', source={'page': 1, 'quote': 'Revenue 100'}, confidence=.8, evidence=['arith_ok', 'value_in_quote'])
    x = dict(report_id='lib-review_test', company='Test', fiscal_year=2025, currency='MSEK', section='income_statement', fields=[f], checks=[dict(name='net_profit_arith', passed=True, detail='old calculation')], warnings=[])
    app.reports[x['report_id']] = dict(report_id=x['report_id'], stem='review_test', pages=2)
    app.texts_cache[x['report_id']] = ['Revenue 100', 'Revenue 120\nCurrent debt 40\nNon-current debt 80']
    kb.save_extraction('review_test', 'income_statement', x)
    def save(field, decision, **kwargs):
        return app.review_field(x['report_id'], app.ReviewBody(section='income_statement', key='revenue', expected=field, decision=decision, reviewer='Tester', note='Checked page 1', **kwargs))
    confirmed = save(copy.deepcopy(f), 'confirmed')
    assert confirmed['fields'][0]['human_review']['decision'] == 'confirmed'
    assert 'source_verified' not in confirmed['fields'][0]['human_review']
    try:
        save(f, 'unresolved')
        raise AssertionError('stale write accepted')
    except HTTPException as e:
        assert e.status_code == 409
    corrected = save(copy.deepcopy(confirmed['fields'][0]), 'corrected', value=120, unit='MSEK', period='2025', source_page=2, source_quote='Revenue 120')
    current = corrected['fields'][0]
    assert current['value'] == 120 and current['evidence'] == ['human_reviewed']
    assert current['source'] == {'page': 2, 'quote': 'Revenue 120'}
    assert current['human_review']['source_verified'] is True
    assert current['review_history'][1]['previous']['value'] == 100
    assert current['review_history'][1]['previous']['source'] == {'page': 1, 'quote': 'Revenue 100'}
    assert corrected['checks'][0]['status'] == 'unavailable'
    assert corrected['check_history'][0]['previous'][0]['detail'] == 'old calculation'
    try:
        save(copy.deepcopy(current), 'corrected', value=121, unit='MSEK', period='2025', source_page=2, source_quote='Revenue 121')
        raise AssertionError('citation not on page accepted')
    except HTTPException as e:
        assert e.status_code == 400 and 'page 2' in str(e.detail)
    component_sum = save(copy.deepcopy(current), 'corrected', unit='MSEK', period='2025', components=[
        {'label': 'Current debt', 'value': 40, 'page': 2, 'quote': 'Current debt 40'},
        {'label': 'Non-current debt', 'value': 80, 'page': 2, 'quote': 'Non-current debt 80'},
    ])
    current = component_sum['fields'][0]
    assert current['value'] == 120 and current['evidence'] == ['human_reviewed', 'components_sum']
    assert current['source'] == {'page': 2, 'quote': 'Current debt 40'}
    assert current['components'] == [
        {'label': 'Current debt', 'value': 40.0, 'page': 2, 'quote': 'Current debt 40'},
        {'label': 'Non-current debt', 'value': 80.0, 'page': 2, 'quote': 'Non-current debt 80'},
    ]
    assert current['review_history'][2]['previous']['source'] == {'page': 2, 'quote': 'Revenue 120'}
    csv_text = app.extraction_csv(x['report_id']).body.decode()
    assert 'human_source_page,human_source_quote,components' in csv_text
    assert 'Current debt 40' in csv_text and 'components_sum' not in csv_text
    slide_text = '\n'.join(shape.text for shape in Presentation(io.BytesIO(app.extraction_pptx(x['report_id']).body)).slides[0].shapes if hasattr(shape, 'text'))
    assert "Human review: p.2 'Current debt 40' — components 2" in slide_text
    persisted = json.loads((Path(tmp)/'review_test/extractions/income_statement.json').read_text())
    assert persisted['fields'][0] == current
    app.extractions.clear()
    app.texts_cache.pop(x['report_id'])
    reopened = save(copy.deepcopy(persisted['fields'][0]), 'unresolved')
    assert reopened['fields'][0]['human_review']['decision'] == 'unresolved'
    assert reopened['fields'][0]['source'] == {'page': 2, 'quote': 'Current debt 40'}
    assert len(reopened['fields'][0]['review_history']) == 4
    try:
        app.run_extract(x['report_id'], app.ExtractBody(section='income_statement'))
        raise AssertionError('review overwritten by extraction')
    except HTTPException as e:
        assert e.status_code == 409
    try:
        save(copy.deepcopy(reopened['fields'][0]), 'corrected', value='NaN', unit='MSEK', period='2025')
        raise AssertionError('invalid numeric value accepted')
    except HTTPException as e:
        assert e.status_code == 422
print('Human review persistence, conflict, correction, export and re-extraction checks passed')
