"""Offline candidate audit. Flags never imply scientific/source approval."""
import collections,json,sys,time
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND))
from app.rag.exam_corpus import read_json,atomic_json,payload_digest,DEFAULT_ROOT
from app.rag.exam_candidate_index import snapshot
from app.rag.exam_quality import issue_flags,curriculum_suggestions,continuation_proposals,norm,native_consistency
from app.rag.book_curriculum import load_catalog

def main():
    root=BACKEND/'data/exam_staging/batch-5000-v1'
    manifest=snapshot(DEFAULT_ROOT,root);records=read_json(root/'chunks.json');catalog=load_catalog()
    fingerprints=collections.defaultdict(list);counts=collections.Counter()
    for r in records:fingerprints[payload_digest(norm(r['text']))].append(r['id'])
    duplicates={x for ids in fingerprints.values() if len(ids)>1 for x in ids}
    queue=[];suggested=0
    native_counts=collections.Counter()
    for r in records:
        issues=issue_flags(r,duplicates)
        native=native_consistency(r,DEFAULT_ROOT);native_counts[native['state']]+=1
        if native.get('missing_numeric_tokens'):issues.append('numbers_not_found_in_native_text')
        counts.update(issues)
        mappings=curriculum_suggestions(r,catalog['nodes']);suggested+=bool(mappings)
        queue.append({'id':r['id'],'content_sha256':r['content_sha256'],'issues':issues,
            'curriculum_suggestions':mappings,'source_text_crosscheck':native,'source_checked':False,'scientific_state':'not_checked',
            'review_priority':len(issues)+3*bool(r['metadata'].get('has_figure'))})
    queue.sort(key=lambda r:(-r['review_priority'],r['id']))
    report={'version':1,'snapshot_sha256':manifest['chunks_sha256'],'created_at':time.time(),
        'pages':manifest['pages'],'questions':len(records),'automatic_issue_counts':dict(counts),
        'questions_with_issues':sum(bool(r['issues']) for r in queue),'book_backed_mapping_suggestions':suggested,
        'verified_new_mappings':0,'native_comparison_coverage':dict(native_counts),'new_scientifically_approved_questions':0,'release_passed':False,
        'status':'review_and_retrieval_evaluation_required',
        'notes':['Detection counts and coverage do not measure proven OCR accuracy.',
        'No automatic flags does not mean source-checked.']}
    for name,value in [('quality-baseline',report),('review-queue',queue),('continuation-queue',continuation_proposals(records))]:
        atomic_json(root/(name+'.json'),value)
    with (root/'quality-history.jsonl').open('a',encoding='utf8') as h:h.write(json.dumps(report,ensure_ascii=False)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
