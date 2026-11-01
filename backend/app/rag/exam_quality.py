"""Fail-closed evidence review, curriculum suggestions and release checks.

Automatic checks detect problems. They never certify source/scientific accuracy.
"""
import collections,json,re,math
from functools import lru_cache
from pathlib import Path
from app.rag.exam_corpus import payload_digest,digest,safe_path,atomic_json
from app.rag.chunking import chunk_text

VERSION='exam-quality-v1'

def norm(value):
    return re.sub(r'\s+',' ',str(value).translate(str.maketrans('يك۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','یک01234567890123456789'))).strip()

@lru_cache(maxsize=2048)
def _tokens(value):return frozenset(re.findall(r'[\w]+',norm(value).lower()))

def tokens(value):return _tokens(str(value))

@lru_cache(maxsize=512)
def _native(path,stamp):
    from app.rag.exam_corpus import read_json
    return read_json(Path(path),{})

def native_consistency(record,root):
    """Independent text-layer warning, never source-faithfulness approval."""
    from app.rag.exam_corpus import native_path
    path=native_path(Path(root),record['metadata']['document_id'],record['metadata']['pdf_page'])
    if not path.is_file():return {'state':'native_unavailable'}
    native=_native(str(path),path.stat().st_mtime_ns)
    quality=native.get('quality',{})
    text=native.get('literal_text','')
    if quality.get('needs_ocr',True) or len(text.strip())<120:return {'state':'native_unreliable'}
    # Compare only warnings about source quantities; glyph encoding can differ.
    numbers=lambda text:set(re.findall(r'\d+',norm(text)))
    missing=numbers(record['text'])-numbers(text)
    return {'state':'comparison_available','missing_numeric_tokens':sorted(missing),
        'scientific_state':'not_checked','note':'A mismatch is a review flag, not proof of a transcription error.'}

def curriculum_suggestions(record,nodes,limit=3):
    """Only supplied book-backed nodes; suggestions are never verified mappings."""
    text=tokens(record['text']);major=record['metadata'].get('major')
    ranked=[]
    for node in nodes:
        sources=node.get('sources',[])
        if not any(s.get('book') and s.get('page') and s.get('quote') for s in sources):continue
        if major not in ('unknown',None) and major not in node.get('majors',[]):continue
        title=tokens(node.get('title',''))
        if len(title)<2:continue # One generic word cannot establish a lesson.
        overlap=title & text
        if len(overlap)<2:continue
        score=len(overlap)/len(title)
        ranked.append((score,node))
    ranked.sort(key=lambda x:(-x[0],x[1]['id']))
    return [{'curriculum_id':n['id'],'title':n['title'],'subject':n['subject'],'grade':n.get('year'),
             'score':round(s,3),'mapping_state':'suggested_not_verified','source':n['sources'][0]}
            for s,n in ranked[:limit]]

def issue_flags(record,duplicates=()):
    literal=record['literal'];issues=[];stem=literal.get('text','')
    options=literal.get('options',[])
    values=[str(o.get('text','')) if isinstance(o,dict) else str(o) for o in options]
    if len(values)!=4 or any(not v.strip() for v in values):issues.append('missing_options')
    if len(set(map(norm,values)))!=len(values):issues.append('duplicate_option_text_requires_review')
    if '\ufffd' in record['text']:issues.append('replacement_characters')
    if re.search(r'(?:ادامه\s*(?:در|صفحه)|continued|\.\.\.\s*$)',stem,re.I):issues.append('possible_continuation')
    if record['metadata'].get('has_figure'):issues.append('figure_requires_source_check')
    if record['metadata'].get('major')=='unknown':issues.append('major_unresolved')
    if record['id'] in duplicates:issues.append('duplicate_content')
    for left,right in [('(',')'),('[',']'),('{','}')]:
        if stem.count(left)!=stem.count(right):issues.append('unbalanced_math_delimiters');break
    return issues

def parent_children(record,max_chars=6000):
    """Retrieve bounded pieces, display the unchanged complete parent question."""
    pieces=([record['text']] if len(record['text'])<=max_chars
        else chunk_text(record['text'],max_chars,min(150,max_chars-1)))
    return [{'id':record['id'] if len(pieces)==1 else record['id']+f':part:{i+1}',
        'parent_id':record['id'],'text':text,'part':i+1,'parts':len(pieces),
        'content_sha256':payload_digest(text)} for i,text in enumerate(pieces)]

def continuation_proposals(records):
    """Adjacent-page hints only. No heuristic is allowed to join source text."""
    by_doc=collections.defaultdict(list)
    for r in records:
        if 'possible_continuation' in issue_flags(r):by_doc[r['metadata']['document_id']].append(r)
    proposals=[]
    for doc,items in by_doc.items():
        for r in items:
            successors=[q for q in records if q['metadata']['document_id']==doc
                and q['metadata']['pdf_page']==r['metadata']['pdf_page']+1]
            proposals.append({'parent_id':r['id'],'source_sha256':r['content_sha256'],
                'next_page_candidates':[s['id'] for s in successors], 'state':'source_review_required'})
    return proposals

def join_continuation(parts,review):
    expected=[p['content_sha256'] for p in parts]
    if (len(parts)<2 or review.get('source_checked') is not True or review.get('part_sha256')!=expected
        or not review.get('reviewer') or not review.get('source_image_sha256')):
        raise ValueError('Continuation needs explicit source-bound review of every part')
    docs={p['metadata']['document_id'] for p in parts}
    pages=[p['metadata']['pdf_page'] for p in parts]
    if len(docs)!=1 or pages!=list(range(pages[0],pages[0]+len(pages))):
        raise ValueError('Continuation parts must be adjacent pages from one document')
    return {'parent_id':parts[0]['id'],'text':'\n'.join(p['text'] for p in parts),
        'source_parts':[{'id':p['id'],'sha256':p['content_sha256']} for p in parts],
        'pdf_pages':pages,'review':review,'scientific_state':'not_checked'}

def delta(previous,current):
    old={r['id']:r for r in previous};new={r['id']:r for r in current}
    return {'added':[k for k in new if k not in old],
        'superseded':[{'id':k,'old_sha256':old[k]['content_sha256'],'new_sha256':r['content_sha256']}
                      for k,r in new.items() if k in old and old[k]['content_sha256']!=r['content_sha256']],
        'removed':[k for k in old if k not in new],
        'unchanged':sum(k in old and old[k]['content_sha256']==r['content_sha256'] for k,r in new.items())}

def retrieval_metrics(cases,rankings,k=5):
    if not cases:return {'queries':0,'recall_at_5':None,'mrr':None}
    recall=[];reciprocal=[]
    for case in cases:
        expected=set(case['expected_ids']);hits=rankings.get(case['id'],[])[:k]
        recall.append(len(expected & set(hits))/len(expected))
        reciprocal.append(next((1/(i+1) for i,x in enumerate(hits) if x in expected),0))
    return {'queries':len(cases),'recall_at_5':sum(recall)/len(recall),'mrr':sum(reciprocal)/len(reciprocal)}

def release_eligibility(record,review,embedding,eval_report):
    reasons=[]
    if review.get('record_id')!=record['id'] or review.get('content_sha256')!=record['content_sha256']:reasons.append('stale_or_missing_review')
    if review.get('source_checked') is not True or not review.get('source_image_sha256'):reasons.append('source_not_checked')
    if review.get('curriculum_state')!='verified' or not review.get('curriculum_ids'):reasons.append('curriculum_not_verified')
    if (review.get('scientific_state')!='verified' or not review.get('verification_evidence')
            or type(review.get('answer_index')) is not int or not 0<=review['answer_index']<4):
        reasons.append('scientific_not_verified')
    if review.get('issues'):reasons.append('unresolved_issues')
    if review.get('difficulty_state')!='verified':reasons.append('difficulty_not_calibrated')
    if review.get('novelty_state')!='reviewed':reasons.append('novelty_not_reviewed')
    if embedding.get('content_sha256')!=record['content_sha256'] or not embedding.get('vector'):reasons.append('embedding_missing_or_stale')
    if not eval_report.get('release_passed'):reasons.append('evaluation_not_passed')
    vector=embedding.get('vector',[])
    dimensions=eval_report.get('embedding_dimensions')
    if (not dimensions or len(vector)!=dimensions or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector)
        or embedding.get('model')!=eval_report.get('embedding_model')):
        reasons.append('embedding_contract_mismatch')
    return reasons

def release_evaluation_reasons(report):
    """Explicit initial project policy, not a claim of universal quality thresholds."""
    reasons=[]
    if report.get('embedding_complete') is not True:reasons.append('embedding_snapshot_incomplete')
    if report.get('gold_overlay_count',0):reasons.append('evaluation_used_gold_overlay')
    if report.get('gold_sources',0)<20 or report.get('held_out_documents',0)<3:
        reasons.append('insufficient_independent_sources')
    if not {'ریاضی','فیزیک','شیمی'}.issubset(set(report.get('subject_coverage',[]))):
        reasons.append('subject_coverage_incomplete')
    metrics=report.get('selected_policy_metrics',{})
    if metrics.get('queries',0)<30 or metrics.get('recall_at_5',0)<.9 or metrics.get('mrr',0)<.8:
        reasons.append('retrieval_acceptance_not_met')
    if report.get('verified_generation_questions',0)<20:reasons.append('generation_acceptance_not_met')
    return reasons

def export_bundle(records,reviews,embeddings,evaluation,destination,root):
    """Approved question data only. A report with zero eligible rows is valid."""
    import zipfile
    from app.rag.book_curriculum import load_catalog
    if evaluation.get('snapshot_sha256')!=payload_digest(records):
        raise ValueError('Evaluation targets a different snapshot')
    policy_reasons=release_evaluation_reasons(evaluation)
    catalogue={n['id'] for n in load_catalog().get('nodes',[]) if n.get('sources')}
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    eligible=[];held=collections.Counter();images={}
    for r in records:
        review=reviews.get(r['id'],{});embedding=embeddings.get(r['id'],{})
        reasons=release_eligibility(r,review,embedding,evaluation)
        reasons.extend(policy_reasons)
        if not set(review.get('curriculum_ids',[])).issubset(catalogue):
            reasons.append('curriculum_ids_not_in_supplied_books')
        if reasons:held.update(reasons);continue
        image=safe_path(Path(root),r['metadata']['image'])
        if not image.is_file() or digest(image)!=review['source_image_sha256']:
            held['source_image_changed']+=1;continue
        eligible.append({'record':r,'review':review,'embedding':embedding})
        images[review['source_image_sha256']]=image
    manifest={'version':VERSION,'eligible_questions':len(eligible),'held_reasons':dict(held),
        'automatic_activation':False,'evaluation_sha256':payload_digest(evaluation),
        'records_sha256':payload_digest(eligible),'image_sha256':sorted(images)}
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        z.writestr('records.json',json.dumps(eligible,ensure_ascii=False))
        for sha,path in images.items():z.write(path,'images/'+sha+'.png')
    return manifest
