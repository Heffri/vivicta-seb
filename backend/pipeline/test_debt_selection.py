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


if __name__ == '__main__':
    test_selected_borrowings_note()
    test_parent_sections_and_unit_ambiguity()
    print('Debt selection, entity scope, printed nil, and unit declaration regressions passed')
