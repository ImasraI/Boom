"""Refresh selected book headings without rebuilding vectors or raw PDFs.

Run from backend: python scripts/refresh_exam_curriculum.py --book 'book name'
Uses the configured pool verifier and stops on provider refusal. Every lesson
must pass the normal literal OCR quote validator before activation.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from app.rag import book_curriculum as curriculum, pool_usage
from app.rag.llm import get_pool_verifier_client


def refresh(books, client=None):
    root = Path(get_settings().OCR_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[1] / root
    catalog = curriculum.load_catalog()
    client = client or get_pool_verifier_client()
    for book in books:
        if Path(book).name != book or '/' in book or '\\' in book:
            raise ValueError('Book must be a name in the promoted OCR directory')
        paths = {}
        for folder in (root / book, root / (book + '.pdf')):
            for path in [*folder.glob('page_*.txt'), *(folder / 'pages').glob('page_*.json')]:
                page = int(path.stem.split('_')[-1])
                if page not in paths or path.stat().st_size > paths[page].stat().st_size:
                    paths[page] = path
        pages, fingerprint = curriculum.source_pages(dict(sorted(paths.items())))
        if not pages:
            raise ValueError(f'No readable source pages for {book}')
        cache = curriculum.catalog_path().parent / 'books' / (hashlib.sha256(book.encode()).hexdigest()[:20] + '.json')
        try:
            saved = json.loads(cache.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = {}
        if saved.get('fingerprint') == fingerprint and saved.get('nodes'):
            nodes = saved['nodes']
            # Revalidate cached headings when a filename classification is fixed.
            # Reuse the literal OCR evidence instead of spending provider quota.
            if any(n['subject'] != curriculum.subject_for_book(book) for n in nodes):
                nodes = curriculum.reclassify_cached_lessons(book, nodes, pages)
                if not nodes:
                    raise ValueError(f'Cached headings no longer validate for {book}')
                curriculum.save_json(cache, dict(book=book, fingerprint=fingerprint, nodes=nodes))
        else:
            with pool_usage.stage('curriculum'):
                nodes = curriculum.extract_book(client, book, pages)
            if not nodes:
                raise ValueError(f'No source-validated lessons extracted for {book}')
            curriculum.save_json(cache, dict(book=book, fingerprint=fingerprint, nodes=nodes))
        merged = {}
        for node in catalog.get('nodes', []):
            remaining = [s for s in node.get('sources', []) if s['book'] != book]
            if remaining:
                merged[node['id']] = {**node, 'sources': remaining}
        for node in nodes:
            if node['id'] in merged:
                old = merged[node['id']]
                old['sources'].extend(node['sources'])
                old['majors'] = sorted(set(old['majors'] + node['majors']))
            else:
                merged[node['id']] = node
        catalog.update(nodes=list(merged.values()), books=sorted(set(catalog.get('books', []) + [book])),
            updated_at=datetime.now(timezone.utc).isoformat(), complete=False)
        catalog['edges'] = curriculum.valid_edges(catalog.get('edges', []), catalog['nodes'])
        curriculum.save_json(curriculum.catalog_path(), catalog)
        print(json.dumps({'book': book, 'source_validated_lessons': len(nodes)}, ensure_ascii=False), flush=True)
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', action='append', required=True)
    args = parser.parse_args()
    try:
        refresh(args.book)
    except (ValueError, RuntimeError):
        print('Refresh stopped. Existing catalogue and completed books are preserved; check provider health and source OCR.', file=sys.stderr)
        sys.exit(1)
