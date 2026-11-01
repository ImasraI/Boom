"""One unpublished textbook-grounded draft with existing independent verification."""
import sys,time,json,argparse
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND))
from app.rag.exam_corpus import atomic_json

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--difficulty',choices=['easy','konkur','hard','extreme'],default='konkur')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    from app.rag.mock_generation import generate_booklet,verify_and_repair_booklet
    from app.rag.exam_style import is_source_copy
    destination=args.output or BACKEND/'data/exam_staging/batch-5000-v1/generation-pilot.json'
    plan=[{'name':'ریاضی','questions':1,'minutes':3,'major':'riazi','majors':['riazi'],
        'curriculum_ids':['lesson:2779c375e5a967bbcb'],'full_mock':False,'book_grounded':True}]
    topics=['روابط مثلثاتی مجموع و تفاضل زوایا'];events=[]
    def report(event,data):
        # No provider response bodies, prompts, keys or raw exception text.
        events.append({'event':event,'timestamp':time.time()})
    result={'started_at':time.time(),'difficulty':args.difficulty,'plan':plan,'topics':topics,'published':False,
        'release_passed':False,'candidate_corpus_used_as_trusted_evidence':False}
    atomic_json(destination,result)
    try:
        drafts=generate_booklet(1,plan,topics,args.difficulty,max_tokens=4000,timeout=150,grade='دوازدهم',report=report)
        copied=[q for q in drafts if is_source_copy(q.get('text',''),plan,topics)]
        eligible=[q for q in drafts if q not in copied and q.get('grounding_status')=='book_ocr'
            and q.get('curriculum_id') and q.get('book') and q.get('page') and q.get('source_quote')]
        result['held_missing_source_provenance']=len(drafts)-len(copied)-len(eligible)
        checked=verify_and_repair_booklet(eligible,1,args.difficulty,max_regens=0,timeout=90,report=report) if eligible else []
        result.update(drafted=len(drafts),source_copies=len(copied),verified=len(checked),
            drafts=drafts,verified_questions=checked,
            status='pilot_completed' if checked else 'held_no_verified_output')
    except Exception as error:
        result.update(status='blocked',error_type=type(error).__name__)
    result.update(events=events,finished_at=time.time(),human_reviewed=False,
        limitation='One math question only; no representative generation-quality claim.')
    atomic_json(destination,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('drafts','verified_questions','events')},ensure_ascii=False))

if __name__=='__main__':main()
