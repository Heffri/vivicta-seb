"""Run: python test_human_review.py. Uses an isolated temporary KB, no model calls."""
import copy
import json
import os
import tempfile
from pathlib import Path
from fastapi import HTTPException
import app
from pipeline import kb

with tempfile.TemporaryDirectory() as tmp:
    os.environ['KB_DIR'] = tmp
    f = dict(key='revenue', label='Revenue', value=100, unit='MSEK', period='2025', raw_label='Revenue', source={'page': 1, 'quote': 'Revenue 100'}, confidence=.8, evidence=['arith_ok', 'value_in_quote'])
    x = dict(report_id='lib-review_test', company='Test', fiscal_year=2025, section='income_statement', fields=[f], checks=[dict(name='net_profit_arith', passed=True, detail='old calculation')], warnings=[])
    app.reports[x['report_id']] = dict(report_id=x['report_id'], stem='review_test', pages=1)
    kb.save_extraction('review_test', 'income_statement', x)
    def save(field, decision, **kwargs):
        return app.review_field(x['report_id'], app.ReviewBody(section='income_statement', key='revenue', expected=field, decision=decision, reviewer='Tester', note='Checked page 1', **kwargs))
    confirmed = save(copy.deepcopy(f), 'confirmed')
    assert confirmed['fields'][0]['human_review']['decision'] == 'confirmed'
    try:
        save(f, 'unresolved')
        raise AssertionError('stale write accepted')
    except HTTPException as e:
        assert e.status_code == 409
    corrected = save(copy.deepcopy(confirmed['fields'][0]), 'corrected', value=120, unit='MSEK', period='2025')
    current = corrected['fields'][0]
    assert current['value'] == 120 and current['evidence'] == []
    assert current['review_history'][1]['previous']['value'] == 100
    assert corrected['checks'][0]['status'] == 'unavailable'
    assert corrected['check_history'][0]['previous'][0]['detail'] == 'old calculation'
    assert 'corrected' in app.extraction_csv(x['report_id']).body.decode()
    persisted = json.loads((Path(tmp)/'review_test/extractions/income_statement.json').read_text())
    assert persisted['fields'][0] == current
    app.extractions.clear()
    reopened = save(copy.deepcopy(persisted['fields'][0]), 'unresolved')
    assert reopened['fields'][0]['human_review']['decision'] == 'unresolved'
    assert len(reopened['fields'][0]['review_history']) == 3
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
