"""Local read-only evidence report; never exposes credentials or approves data."""
import html,re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote
from app.rag.exam_corpus import read_json,safe_path

STAGE=Path(__file__).resolve().parents[2]/'data/exam_staging/batch-5000-v1'
CSS='body{background:#191413;color:#f1e2da;font:15px/1.7 system-ui;margin:32px auto;max-width:1150px;padding:20px}a{color:#e9ad9d}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #624539}pre{white-space:pre-wrap;overflow-wrap:anywhere}.layout{display:grid;grid-template-columns:1fr 1fr;gap:24px}img{width:100%}@media(max-width:800px){.layout{display:block}}'

@lru_cache(maxsize=2)
def _records(stamp):
    return {r['id']:r for r in read_json(STAGE/'chunks.json',[])}

def item(identity):
    if not re.fullmatch(r'[a-f0-9]{64}:\d+:\d+',identity):return None
    path=STAGE/'chunks.json'
    if not path.exists():return None
    return _records(path.stat().st_mtime_ns).get(identity)

def source_image(root,identity):
    record=item(identity)
    if not record:return None
    try:
        path=safe_path(root,record['metadata']['image'])
        return path if path.is_file() else None
    except (ValueError,KeyError):return None

def render_item(identity):
    record=item(identity)
    if not record:return None
    esc=html.escape
    return f'<html><meta charset="utf-8"><style>{CSS}</style><a href="/corpus-quality">Quality report</a><h1>OCR candidate source comparison</h1><p>Unreviewed OCR. This page does not certify the text, diagram or answer.</p><p>{esc(identity)}</p><div class="layout"><pre dir="rtl">{esc(record["text"])}</pre><img src="/corpus-source?id={quote(identity)}" alt="Original page"></div></html>'

def render_report():
    baseline=read_json(STAGE/'quality-baseline.json',{})
    retrieval=read_json(STAGE/'retrieval-pilot.json',{})
    embedding=read_json(STAGE/'embedding-status.json',{})
    generation=read_json(STAGE/'generation-pilot.json',{})
    chunking=read_json(STAGE/'chunking-comparison.json',{})
    readiness=read_json(STAGE/'release-readiness.json',{})
    run=read_json(STAGE/'retrieval-run-status.json',{})
    queue=read_json(STAGE/'review-queue.json',[])[:30]
    esc=lambda x:html.escape(str(x))
    issues=''.join(f'<tr><td>{esc(k)}</td><td>{v}</td></tr>' for k,v in baseline.get('automatic_issue_counts',{}).items())
    metrics=''.join(f'<tr><td>{esc(k)}</td><td>{v.get("recall_at_5")}</td><td>{v.get("mrr")}</td></tr>' for k,v in retrieval.get('metrics',{}).items())
    links=''.join(f'<li><a href="/corpus-item?id={quote(r["id"])}">{esc(r["id"])}</a> — {esc(", ".join(r["issues"]))}</li>' for r in queue)
    held=''.join(f'<li>{esc(reason)}</li>' for reason in readiness.get('reasons',[]))
    return f'''<html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style>
<a href="/">Worker monitor</a><h1>Exam corpus quality and release readiness</h1>
<p><strong>NOT READY FOR VM RELEASE.</strong> Format checks and embeddings are not scientific approval.</p>
<details><summary>Outstanding release evidence</summary><ul>{held}</ul><p>These describe the latest saved evaluation; a completed embedding job does not update an older retrieval test.</p></details>
<p>Snapshot: {baseline.get('pages',0)} question pages · {baseline.get('questions',0)} questions. Embeddings: {embedding.get('stored_chunks',0)} / {embedding.get('total_chunks',0)} ({esc(embedding.get('phase','unknown'))}).</p>
<h2>Fixed-input chunking comparison</h2><p>Oversized ordinary-text chunks: old {chunking.get('metrics',{}).get('legacy',{}).get('oversized_chunks','not measured')} → new {chunking.get('metrics',{}).get('v2',{}).get('oversized_chunks','not measured')}. This is a boundary check, not OCR accuracy.</p>
<h2>Automatic review flags</h2><p>These are suspected issues requiring source checks, not confirmed error counts.</p><table>{issues}</table>
<h2>Measured retrieval pilot</h2><p>Latest evaluation run: {esc(run.get('phase','not run'))}. Provider failure categories: {esc(run.get('failure_counts',{}))}. Metrics below are from the last completed evaluation.</p><p>{esc('; '.join(retrieval.get('limitations',[])))}</p><table><tr><th>Method</th><th>Recall at 5</th><th>MRR</th></tr>{metrics}</table>
<h2>Generation pilot</h2><p>Status: {esc(generation.get('status','not run'))} · Drafted: {generation.get('drafted',0)} · Verified: {generation.get('verified',0)} · Published: false.</p>
<h2>Priority source review queue</h2><ul>{links}</ul><p>More embeddings do not imply better quality. Only source-bound, curriculum-verified and scientifically verified records can pass the release exporter.</p></html>'''
