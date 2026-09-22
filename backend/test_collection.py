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
assert len(collection.NO_STANDALONE) == 13
assert len(collection.members('midcap')) == 132
assert collection.member('Acast', 'midcap')
assert not collection.member('ABB', 'midcap')
assert len(collection.directory(app.COMPANIES, 'midcap')) == 132
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    library = root / 'reports'
    library.mkdir()
    (library / 'index.json').write_text('[]')
    with patch.dict('os.environ', {'KB_DIR': str(root / 'kb')}), patch.object(app, 'LIBRARY', library), patch.object(app, 'reports', {}), patch.object(app, 'extractions', {}), patch.object(app, 'library_paths', {}):
        for stem, name in [('abb_2025', 'ABB Ltd'), ('acast_2025', 'Acast'), ('outside_2025', 'Volvo')]:
            kb.save_report(stem, {'company': name, 'fiscal_year': 2025, 'pages': 1, 'sha256': 'test'}, ['Revenue 100'])
        saved = {'section': 'income_statement', 'fields': [{'key': 'revenue', 'value': 100, 'review_history': [{'decision': 'confirmed'}]}], 'checks': [], 'warnings': []}
        kb.save_extraction('abb_2025', 'income_statement', saved)
        kb.save_extraction('acast_2025', 'income_statement', saved)
        client = TestClient(app.app)
        with patch.object(app.fetch, 'fetch_report', side_effect=AssertionError('Unexpected PDF download')):
            assert len(client.get('/api/kb?collection_name=wallenberg').json()) == 1
            assert len(client.get('/api/kb?collection_name=midcap').json()) == 1
            assert len(client.get('/api/kb').json()) == 3
            assert len(client.get('/api/companies?collection_name=wallenberg').json()) == 35
            # A Patricia Industries subsidiary is present in the Wallenberg directory, but it does
            # not publish a standalone report.  Its directory row must name the Investor report
            # instead of leading the Extract flow into an unrelated PDF search.
            kb.save_report('investor_2025', {'company': 'Investor AB', 'fiscal_year': 2025, 'pages': 2, 'sha256': 'investor'}, [
                'Investor annual report 2025', 'Patricia Industries reports on Sarnova.',
            ])
            sarnova = client.get('/api/companies?q=sarnova&collection_name=wallenberg').json()
            assert sarnova == [
                {
                    'name': 'Sarnova', 'ticker': '', 'sector': None, 'isin': None, 'cached_years': [],
                    'no_standalone_report': True, 'reports_in': 'Investor AB',
                    'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025',
                    'report_page': 2,
                }
            ], sarnova
            investor = next(entry for entry in client.get('/api/kb?collection_name=wallenberg').json()
                            if entry['stem'] == 'investor_2025')
            assert investor['reported_members'] == [
                {'name': 'Atlas Antibodies', 'collection_group': 'Patricia Industries'},
                {'name': 'BraunAbility', 'collection_group': 'Patricia Industries'},
                {'name': 'Laborie', 'collection_group': 'Patricia Industries'},
                {'name': 'Mölnlycke', 'collection_group': 'Patricia Industries'},
                {'name': 'Nova Biomedical', 'collection_group': 'Patricia Industries'},
                {'name': 'Permobil', 'collection_group': 'Patricia Industries'},
                {'name': 'Piab', 'collection_group': 'Patricia Industries'},
                {'name': 'Sarnova', 'collection_group': 'Patricia Industries'},
                {'name': '3 Scandinavia', 'collection_group': 'Patricia Industries'},
                {'name': 'Vectura', 'collection_group': 'Patricia Industries'},
            ], investor
            with patch.object(app.fetch, '_model_discover', side_effect=AssertionError('private holdings must not start AI discovery')), \
                    patch.object(app.fetch, 'fetch_report', side_effect=AssertionError('private holdings must not fetch a standalone PDF')):
                discovered = client.post('/api/reports/discover', json={'company': 'Sarnova', 'year': 2025})
                assert discovered.status_code == 200 and discovered.json() == {
                    'candidates': [], 'note': "Private company — reported inside Investor AB's annual report (Patricia Industries)",
                    'source': 'saved', 'skipped_web_search': True,
                }, discovered.text
                blocked = client.post('/api/reports/fetch', json={'company': 'Sarnova', 'year': 2025,
                                                                   'url': 'https://example.com/investor.pdf'})
                assert blocked.status_code == 409 and blocked.json()['reports_in'] == 'Investor AB', blocked.text
            assert [company['name'] for company in client.get('/api/companies?q=acast&collection_name=midcap').json()] == ['Acast']
            assert client.get('/api/review-queue?collection_name=midcap').status_code == 200
            export = client.get('/api/kb/export.csv?section=income_statement&collection=midcap')
            assert export.status_code == 200 and 'Acast' in export.text and 'ABB' not in export.text
            assert client.get('/api/library?collection_name=wallenberg').json() == []
            # download_pdf defaults to true (the PDF is always wanted); false is the text-only reuse of a saved report
            response = client.post('/api/reports/fetch', json={'company': 'ABB', 'year': 2025, 'download_pdf': False})
            assert response.status_code == 200, response.text
            assert response.json()['report_id'] == 'lib-abb_2025'
            assert client.post('/api/reports/fetch', json={'company': 'ABB', 'year': 2024, 'download_pdf': False}).status_code == 409
            with patch.object(app.extract_mod, 'extract', side_effect=AssertionError('Saved extraction replaced')):
                response = client.post('/api/reports/lib-abb_2025/extract', json={'section': 'income_statement', 'reuse_saved': True})
                assert response.status_code == 200 and response.json()['fields'] == saved['fields']
        entry = {'file': 'new.pdf', 'company': 'ABB', 'fiscal_year': 2024, 'source_url': 'https://example.com/report.pdf'}
        with patch.object(app.fetch, 'fetch_report', return_value=entry) as download, patch.object(app, 'register_library', return_value={'report_id': 'new'}):
            assert client.post('/api/reports/fetch', json={'company': 'ABB', 'year': 2024, 'download_pdf': True}).status_code == 200
            download.assert_called_once()
            # a confirmed /discover candidate: its url reaches fetch_report as the first thing to try
            body = {'company': 'ABB Ltd', 'year': 2024, 'country': 'CH', 'download_pdf': True, 'url': 'https://example.com/abb-annual-report-2024.pdf'}
            assert client.post('/api/reports/fetch', json=body).status_code == 200
            assert download.call_args.args[0] == 'ABB Ltd' and download.call_args.kwargs == {'url': body['url'], 'job_id': None}
            assert client.post('/api/reports/fetch', json=body | {'url': 'javascript:alert(1)'}).status_code == 400
        # the PDF is wanted (default) but unreachable: saved page text still serves; nothing saved is a 404
        with patch.object(app.fetch, 'fetch_report', side_effect=LookupError([], 'offline')):
            assert client.post('/api/reports/fetch', json={'company': 'ABB', 'year': 2025}).json()['report_id'] == 'lib-abb_2025'
            assert client.post('/api/reports/fetch', json={'company': 'ABB', 'year': 2024}).status_code == 404
        # /discover never downloads: it hands the query to fetch.discover and returns its candidates + note as-is
        with patch.object(app.fetch, 'fetch_report', side_effect=AssertionError('Unexpected PDF download')), \
                patch.object(app.fetch, 'discover', return_value={'candidates': [], 'note': 'n'}) as discover:
            response = client.post('/api/reports/discover', json={'company': 'intel', 'year': 2025, 'hint': 'chips', 'force_web': True})
            assert response.status_code == 200 and response.json() == {'candidates': [], 'note': 'n'}, response.text
            assert discover.call_args.args == ('intel', 2025, None, 'chips', library)
            assert discover.call_args.kwargs == {'job_id': None, 'force_web': True}
            assert client.post('/api/reports/discover', json={'company': 'intel', 'year': 1066}).status_code == 400
        # v194 integration: a job_id on a REAL (unmocked) /discover call is recorded end to end through
        # GET /api/jobs/{id}; no LLM_PROVIDER is set anywhere in this test, so this never reaches a model
        job_id = 'job-discover-abb'
        assert client.get(f'/api/jobs/{job_id}').status_code == 404
        response = client.post('/api/reports/discover', json={'company': 'ABB', 'year': 2025, 'job_id': job_id})
        assert response.status_code == 200 and response.json()['candidates'], response.text
        job = client.get(f'/api/jobs/{job_id}').json()
        assert job['job_id'] == job_id and job['done'] is True and job['stage'] == 'done' and job['error'] is None, job
        stages = [e['stage'] for e in job['events']]
        assert stages == ['directory', 'directory', 'done'], stages
        assert 'saved report found, web search skipped' in job['events'][1]['text'], job
print('Wallenberg scope, saved-text reuse, review preservation, discover and always-download passed')
