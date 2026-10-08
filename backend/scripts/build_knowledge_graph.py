"""Build/resume the book-sourced shared graph; never re-embed books."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.book_curriculum import rebuild
from app.rag.llm import get_llm_client

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=0,help='Maximum uncached books this run; zero means all')
    parser.add_argument('--no-prerequisites',action='store_true')
    parser.add_argument('--cached-only',action='store_true',help='Rebuild from already extracted books; no new book extraction')
    parser.add_argument('--model',default=None,help='Optional model for this offline job; does not change app settings')
    parser.add_argument('--request-interval',type=float,default=25,help='Minimum seconds between provider requests')
    args=parser.parse_args()
    if args.limit<0 or args.request_interval<0: parser.error('Limit and request interval must be nonnegative')
    class PacedClient:
        def __init__(self): self.client=get_llm_client(model=args.model); self.last_error=''; self.last_request=0
        def generate(self,*a,**kw):
            delay=max(0,args.request_interval-(time.monotonic()-self.last_request))
            if delay: time.sleep(delay)
            self.last_request=time.monotonic()
            raw=self.client.generate(*a,**kw); self.last_error=self.client.last_error
            return raw
    result=rebuild(PacedClient(),limit=args.limit,infer=not args.no_prerequisites,cached_only=args.cached_only,
        on_progress=lambda event:print(json.dumps(event,ensure_ascii=False),flush=True))
    print(json.dumps({'books':len(result['books']),'lessons':len(result['nodes']),
        'prerequisites':len(result['edges']),'complete':result['complete'],'errors':result['errors']},ensure_ascii=False),flush=True)
    sys.exit(0 if result['complete'] else 2)
