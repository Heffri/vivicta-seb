"""Regression for AAK's selected borrowings note versus the lease table.

Run: python -m pipeline.test_debt_selection. No model calls or cache writes.
"""
import copy
import json
from pathlib import Path
from unittest.mock import patch

from . import extract as x


def test_selected_borrowings_note():
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / 'backend/schemas/debt_maturity.json').read_text(encoding='utf-8'))
    pages = [json.loads(line) for line in (root / 'data/kb/aak_2025/pages.jsonl').read_text(encoding='utf-8').split('\n') if line.strip()]
    texts = [''] * max(p['page'] for p in pages)
    for page in pages:
        texts[page['page'] - 1] = page['text']
    raw = []
    values = [None, 4088, 0, 390]
    quotes = [None, 'Liabilities to banks and credit institutions 4,088 2,071 531 1,026',
              'Between 1 and 5 years - 791 - 526', 'More than 5 years 390 158 - -']
    for sf, value, quote in zip(schema['fields'], values, quotes):
        raw.append(dict(key=sf['key'], label=sf['label'], value=value, unit=None, period='2025',
                        raw_label=x._row_label(quote) if quote else None,
                        source={'page': 169, 'quote': quote} if quote else None))

    def model(*args, **kwargs):
        return {'pages': [169, 170]} if len(args) > 3 and args[3] == 'page_select' else {'fields': copy.deepcopy(raw)}

    with patch.dict('os.environ', {'EXTRACT_TWO_PASS': '1', 'FEWSHOT': '0'}), patch.object(x, 'call_llm', model):
        result = x.extract(texts, [145, 146, 169, 170], schema, {'company': 'AAK', 'fiscal_year': 2025})
    assert [f['value'] for f in result['fields']] == [4478, 4088, 0, 390], result
    assert all(f['source']['page'] == 169 for f in result['fields']), result
    assert all(f['unit'] == 'SEK million' for f in result['fields']), result
    assert result['checks'][0]['passed'], result
    assert 'value_derived' in result['fields'][0]['evidence']
    assert 'printed_nil' in result['fields'][2]['evidence']

    wrong_total = copy.deepcopy(raw)
    wrong_total[0].update(value=390, raw_label='Total', source={'page': 169, 'quote': 'Total 390 949 - 526'})
    with patch.dict('os.environ', {'EXTRACT_TWO_PASS': '1', 'FEWSHOT': '0'}), \
         patch.object(x, 'call_llm', lambda *args, **kwargs: {'pages': [169, 170]} if len(args) > 3 and args[3] == 'page_select' else {'fields': copy.deepcopy(wrong_total)}):
        corrected = x.extract(texts, [145, 146, 169, 170], schema, {'company': 'AAK', 'fiscal_year': 2025})
    assert corrected['fields'][0]['value'] == 4478 and corrected['checks'][0]['passed'], corrected

    # A bad pass-one choice must widen over locate's original top four, and a
    # same-sized retry with verifiable citations must replace the uncited answer.
    text_by_page = {p['page']: p['text'] for p in pages}
    ranked_texts = ['', '', '', text_by_page[169], '', '']
    good = copy.deepcopy(raw)
    for f in good:
        if f['source']:
            f['source']['page'] = 4
    bad = copy.deepcopy(raw)
    for f in bad:
        if f['value'] is not None:
            f['source'] = {'page': 5, 'quote': 'not printed here'}
    calls = []

    def retry_model(system, user, schema=x.RESPONSE_SCHEMA, name='extraction'):
        calls.append((name, user))
        if name == 'page_select':
            return {'pages': [5, 6]}
        return {'fields': copy.deepcopy(bad if len([c for c in calls if c[0] == 'extraction']) == 1 else good)}

    with patch.dict('os.environ', {'EXTRACT_TWO_PASS': '1', 'FEWSHOT': '0'}), patch.object(x, 'call_llm', retry_model):
        retried = x.extract(ranked_texts, [1, 2, 3, 4, 5, 6], schema,
                            {'company': 'AAK', 'fiscal_year': 2025})
    extraction_calls = [user for name, user in calls if name == 'extraction']
    assert len(extraction_calls) == 2, calls
    assert '=== PAGE 4 ===' in extraction_calls[1] and '=== PAGE 5 ===' not in extraction_calls[1], calls
    assert [f['value'] for f in retried['fields']] == [4478, 4088, 0, 390], retried


def test_parent_sections_and_unit_ambiguity():
    words = ['parent', 'parent company', 'moderbolaget']
    for rows in [
        ['Group', 'Parent', '2025 2024', 'Borrowings 100 90'],
        ['Group', 'Borrowings 100 90', 'Parent', '2025 2024', 'Borrowings 5 4'],
    ]:
        assert x._nearest_entity_section(rows, len(rows) - 1, words) == 'parent'
    rows = ['Group', 'Parent', 'Current 2025 2024 2025 2024', 'Borrowings 100 90 5 4']
    assert x._nearest_entity_section(rows, 3, words) == 'group'
    assert x._row_year_column(rows, 3, 2025) == (0, 4)
    rows = ['Parent', 'Group', 'Current 2025 2024 2025 2024', 'Borrowings 5 4 100 90']
    assert x._row_year_column(rows, 3, 2025) == (2, 4)
    assert x._declared_report_unit(['Revenue SEK million 100']) is None
    assert x._declared_report_unit(['Amounts stated in SEK million unless specified otherwise.']) == ('SEK million', 1)
    assert x._declared_report_unit(['Amounts stated in SEK million unless specified otherwise.',
                                  'Amounts stated in EUR million unless specified otherwise.']) is None


def test_interleaved_year_table():
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / 'backend/schemas/debt_maturity.json').read_text(encoding='utf-8'))
    text = '\n'.join([
        'The maturity structure of Group borrowings follows.',
        'Other table row 100 Maturity Fixed Floating Carrying amount Fair value',
        'Short-term loans 2026 6 337 134 6 471 6 436',
        'Lease liabilities 2027 3 953 2 3 955 3 894',
        'Total current borrowings 2028 2 356 1 2 357 2 314',
        'Closing balance 2029 4 033 – 4 033 3 752',
        'Prose from left column 2030 551 5 129 5 680 5 789',
        'More prose 2031 426 1 976 2 402 2 427',
        'More prose 2032 5 696 – 5 696 5 025',
        'More prose 2033 260 – 260 260',
        'More prose 2034 and after 4 045 – 4 045 4 052',
        'Debt note Total 27 657 7 242 34 899 33 949',
    ])
    table = x.wide_year_table(text, 2025, schema)
    assert table and table['total'] == 34899 and [value for _, value, _ in table['items']] == [6471, 3955, 2357, 4033, 5680, 2402, 5696, 260, 4045]
    fields = [dict(key=sf['key'], value=None, source=None, evidence=[], unit=None) for sf in schema['fields']]
    pick, values = {}, {}
    x._wide_year_table_fill(fields, schema, [text], [1], 2025, 'carrying', pick, [], values, set())
    assert values == dict(total_debt=34899, due_within_1_year=6471, due_1_to_5_years=16025, due_after_5_years=12403)
    assert all(x.quote_on_page(part['quote'], text) for field in fields for part in field.get('components', []))
    assert len(x._buckets_by_year_fill(schema, [text], 2025, pick, values)['years']) == 9


if __name__ == '__main__':
    test_selected_borrowings_note()
    test_parent_sections_and_unit_ambiguity()
    test_interleaved_year_table()
    print('Debt selection, interleaved maturity, entity scope, printed nil, and unit declaration regressions passed')
