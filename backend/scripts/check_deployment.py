"""Read-only preflight. Run from backend: python scripts/check_deployment.py.

--network probes public HTTPS/CORS and SMS credit (never sends a message).
--probe-embedding checks the configured query vector against uploaded dimensions.
No app/database imports: running this does not migrate or write the databases.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from app.config import get_settings
from app.utils.deployment_checks import configuration_issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network', action='store_true')
    parser.add_argument('--probe-embedding', action='store_true')
    parser.add_argument('--frontend', default='https://boomedu.ir')
    parser.add_argument('--api', default='https://api.boomedu.ir')
    args = parser.parse_args()
    settings = get_settings()
    from app.rag.gemini_embeddings import text_collection_name
    text_collections = [text_collection_name(settings, name) for name in
                        [settings.CHROMA_COLLECTION, settings.CHROMA_QA_COLLECTION]]
    errors, warnings = configuration_issues(settings)
    root = Path(__file__).resolve().parents[1]
    if Path.cwd().resolve() != root:
        errors.append('Run from backend so .env and relative corpus/image paths resolve correctly.')
    dimensions = {}
    for path, vector in [(root / 'rag_data.db', False), (Path(settings.CHROMA_DIR) / 'chroma.sqlite3', True)]:
        if not path.exists():
            errors.append(f'Missing database: {path.name}')
            continue
        try:
            db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
            with db:
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    errors.append(f'Integrity check failed: {path.name}')
                if vector:
                    dimensions = dict(db.execute('SELECT name, dimension FROM collections').fetchall())
            db.close()
        except sqlite3.Error:
            errors.append(f'Unable to inspect database: {path.name}')
    for name in text_collections:
        if not dimensions.get(name):
            errors.append(f'Indexed collection missing or empty: {name}')
    print('Vector dimensions:', json.dumps(dimensions, ensure_ascii=False))
    image_count = sum(1 for path in (root / 'data').rglob('*') if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'})
    print('Processed page images:', image_count)
    if not image_count:
        warnings.append('No processed page images found; figure-based retrieval cannot load book pages.')
    print('Raw PDFs are optional: upload promoted OCR, vector databases and referenced page images.')
    with requests.Session() as session:
        session.trust_env = False
        def probe(label, method, url, expected_status=(200,), **kwargs):
            try:
                response = session.request(method, url, timeout=(5, 15), **kwargs)
                if response.status_code not in expected_status:
                    errors.append(f'{label}: HTTP {response.status_code}')
                    return None
                return response
            except requests.RequestException as exc:
                errors.append(f'{label}: {type(exc).__name__}')
                return None
        if args.network:
            probe('Frontend', 'GET', args.frontend)
            health = probe('API health', 'GET', args.api.rstrip('/') + '/api/health')
            for path in ['/api/profile/calendar', '/api/admin/sms-delivery/1']:
                probe('Protected route ' + path, 'GET', args.api.rstrip('/') + path, expected_status=(401, 403))
            if health is not None:
                try:
                    if health.json().get('status') != 'ok': errors.append('API did not report healthy JSON.')
                except (ValueError, AttributeError): errors.append('API health returned non-JSON content (check routing).')
            cors = probe('CORS', 'OPTIONS', args.api.rstrip('/') + '/api/health', headers={'Origin': args.frontend.rstrip('/'), 'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization'})
            if cors is not None and cors.headers.get('Access-Control-Allow-Origin') != args.frontend.rstrip('/'):
                errors.append('API CORS does not allow the frontend origin.')
            if settings.SMS_API_KEY:
                sms = probe('SMS.ir credit/authentication', 'GET', settings.SMS_BASE_URL.rstrip('/') + '/v1/credit', headers={'x-api-key': settings.SMS_API_KEY}, proxies={'http': settings.SMS_PROXY, 'https': settings.SMS_PROXY} if settings.SMS_PROXY else None)
                if sms is not None:
                    try:
                        data = sms.json()
                        if data.get('status') != 1 or not isinstance(data.get('data'), (int, float)) or data['data'] <= 0:
                            errors.append('SMS.ir rejected credit check or panel credit is empty.')
                    except (ValueError, AttributeError): errors.append('SMS.ir returned invalid credit data.')
        if args.probe_embedding:
            if settings.EMBEDDING_PROVIDER.lower() == 'gemini':
                from app.rag.embeddings import get_embedding_model
                from app.rag.gemini_embeddings import EmbeddingError
                try:
                    model = get_embedding_model()
                    query = model.probe_query('تابع و حد')
                    for name in text_collections:
                        if name in dimensions and len(query) != dimensions[name]:
                            errors.append(f'Query dimension {len(query)} differs from {name}: {dimensions[name]}.')
                    print('Gemini query probe dimensions:', len(query))
                except (EmbeddingError, ValueError) as exc:
                    errors.append(str(exc))
            elif settings.EMBEDDING_PROVIDER.lower() != 'ollama':
                warnings.append('Embedding probe currently supports Ollama; verify other providers with a local retrieval smoke test.')
            else:
                vector = probe('Query embedding', 'POST', settings.EMBEDDING_BASE_URL.rstrip('/').removesuffix('/v1') + '/api/embed', json={'model': settings.EMBEDDING_MODEL_NAME, 'input': 'تابع و حد'})
                if vector is not None:
                    try:
                        length = len(vector.json()['embeddings'][0])
                        for name in text_collections:
                            if name in dimensions and length != dimensions[name]:
                                errors.append(f'Query dimension {length} differs from {name}: {dimensions[name]}. Use the original indexing model.')
                    except (ValueError, KeyError, IndexError, TypeError): errors.append('Embedding provider returned no usable vector.')
    for warning in warnings: print('WARN:', warning)
    for error in errors: print('FAIL:', error)
    print('Preflight failed.' if errors else 'Preflight passed. Verify real login, cited chat, planning and mocks before release.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
