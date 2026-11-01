"""Bounded free-tier runner with preserved candidate and design sidecar outputs."""
import argparse
import hashlib
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json
from app.rag.authoring_benchmark import execution_lock
from app.rag.decision_authoring import parse_envelope,readability
from app.rag.pedagogical_policy import language_audit
from scripts import run_pedagogical_pilot as runner
from scripts.prepare_decision_pilot import OUT,ROOT,prepare


def save_return(folder,raw,state,*,recovered=False):
    data=runner.safe_bytes(raw.encode());sha=hashlib.sha256(data).hexdigest();path=folder/(sha+'.txt')
    if not path.exists():path.write_bytes(data)
    result={**state,'response_sha256':sha,'recovered':recovered,'eligible':False}
    try:
        e=parse_envelope(raw);q=e['candidate']
        atomic_json(folder/'candidate.json',q);atomic_json(folder/'audit-proposals.json',e['audit_proposals'])
        atomic_json(folder/'language-audit.json',language_audit(q))
        atomic_json(folder/'readability-audit.json',{'mobile':readability(q['figure'],320),'desktop':readability(q['figure'],480)})
        result.update(state='drafted',proposal_semantics_checked=False)
    except (ValueError,TypeError) as error:result.update(state='protocol_held',format_error=type(error).__name__)
    atomic_json(folder/'state.json',result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--max-items',type=int,default=1);args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT/'backend' or not 1<=args.max_items<=3:raise ValueError('Run bounded local trial from backend')
    OUT.mkdir(exist_ok=True);runner.OUT=OUT;runner.prepare=prepare;runner.save_return=save_return
    with execution_lock(OUT):runner.run(args.max_items)
