"""Run: python test_collection.py. No network calls or real user data."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import app
from pipeline import kb, collection

assert collection.member('ABB Ltd') and collection.member('Saab (svenska)')
assert collection.identity('Swedish Orphan Biovitrum AB') == collection.identity('Sobi')
assert collection.member('Volvo') is None
assert len(collection.directory([])) == 35
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    library = root / 'reports'
    library.mkdir()
    (library / 'index.json').write_text('[]')
    with patch.dict('os.environ', {'KB_DIR': str(root / 'kb')}), patch.object(app, 'LIBRARY', library), patch.object(app, 'reports', {}), patch.object(app, 'extractions', {}), patch.object(app, 'library_paths', {}):
        for stem, name in [('abb_2025', 'ABB Ltd'), ('outside_2025', 'Volvo')]:
            kb.save_report(stem, {'company': name, 'fiscal_year': 2025, 'pages': 1, 'sha256': 'test'}, ['Revenue 100'])
        saved = {'section': 'income_statement', 'fields': [{'key': 'revenue', 'value': 100, 'review_history': [{'decision': 'confirmed'}]}], 'checks': [], 'warnings': []}
        kb.save_extraction('abb_2025', 'income_statement', saved)
        client = TestClient(app.app)
        with patch.object(app.fetch, 'fetch_report', side_effect=AssertionError('Unexpected PDF download')):
            assert len(client.get('/api/kb?collection_name=wallenberg').json()) == 1
            assert len(client.get('/api/kb').json()) == 2
            assert len(client.get('/api/companies?collection_name=wallenberg').json()) == 35
            assert client.get('/api/library?collection_name=wallenberg').json() == []
            response = client.post('/api/reports/fetch', json={'company': 'ABB', 'year': 2025})
            assert response.status_code == 200, response.text
            assert response.json()['report_id'] == 'lib-abb_2025'
            assert client.post('/api/reports/fetch', json={'company': 'ABB', 'year': 2024}).status_code == 409
            with patch.object(app.extract_mod, 'extract', side_effect=AssertionError('Saved extraction replaced')):
                response = client.post('/api/reports/lib-abb_2025/extract', json={'section': 'income_statement', 'reuse_saved': True})
                assert response.status_code == 200 and response.json()['fields'] == saved['fields']
        entry = {'file': 'new.pdf', 'company': 'ABB', 'fiscal_year': 2024, 'source_url': 'https://example.com/report.pdf'}
        with patch.object(app.fetch, 'fetch_report', return_value=entry) as download, patch.object(app, 'register_library', return_value={'report_id': 'new'}):
            assert client.post('/api/reports/fetch', json={'company': 'ABB', 'year': 2024, 'download_pdf': True}).status_code == 200
            download.assert_called_once()
print('Wallenberg scope, saved-text reuse, review preservation and opt-in downloads passed')
