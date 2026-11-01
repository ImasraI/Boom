"""Private paired-development benchmark: durable outcomes, no promotion or DB.

Provider refusals are not mathematical failures. Failed items are never silently
replaced. Source literals, answer keys and reserved exams are not prompt inputs.
"""
from contextlib import contextmanager
import html
import json
import math
from pathlib import Path
import re
from app.rag.exam_corpus import atomic_json,payload_digest,read_json
from app.rag.grounded_authoring_trial import BRIEFS

VERSION='paired-development-0.1'
FINAL={'drafted','protocol_held','provider_refused','provider_error','interrupted_unknown'}


def saved_json(path,fallback=None):
    # A corrupt checkpoint must not look like a missing one and trigger a retry.
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else fallback


class BenchmarkBusy(RuntimeError):pass


@contextmanager
def execution_lock(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with (folder/'execution.lock').open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            import os
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:raise BenchmarkBusy('Benchmark is already running') from error
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def ordered_items(protocol):
    result=[];seen=set()
    for task in protocol['tasks']:
        match=re.fullmatch(r'dev-pair:(\d{2})',task.get('spec_id',''))
        if not match or task['spec_id'] in seen or task.get('brief_id') not in BRIEFS:
            raise ValueError('Unknown/duplicate task')
        seen.add(task['spec_id'])
        arms=['baseline','design_conditioned'] if task['arm_order']=='baseline_first' else ['design_conditioned','baseline']
        if task['arm_order'] not in ('baseline_first','conditioned_first'):raise ValueError('Unknown arm order')
        for arm in arms:result.append(dict(item_id=f'pair-{match[1]}-{arm}',arm=arm,task=task))
    if len(result)!=40:raise ValueError('Frozen pilot requires20 pairs')
    return result


def authoring_prompt(task,arm):
    if arm not in ('baseline','design_conditioned'):raise ValueError('Unknown arm')
    brief=BRIEFS[task['brief_id']]
    data={'task':task['target'],'facts':brief['facts']}
    if arm=='design_conditioned':data['design_guidance']=brief['pattern']
    return '''Write ONE original Persian high-school mathematics multiple-choice question.
Scope/task data below are abstract mathematical instructions, not exam examples.
Quality: a compact meaningful insight and interacting constraints. Merely changing
numbers, names or options of a standard construction is not a new design. Keep
within the given mathematical scope. Do not assign difficulty labels. State all
domains. Verify real existence, degeneracies, boundary cases and exactly one
correct option; do not choose the closest answer if options are wrong.
Return JSON only with exactly these fields:
{"text":"Persian stem using $LaTeX$ or $$display LaTeX$$",
"options":["$...$","$...$","$...$","$...$"],"answer_index":0,
"solution":"Short checkable derivation; plain Unicode math, no LaTeX commands",
"design":{"givens":"...","unknown":"...","domains":"...",
"essential_insight":"...","structural_departure":"...","tempting_wrong_route":"..."},
"figure":null}
All design prose also uses plain Unicode mathematics, avoiding JSON backslash
escape mistakes. answer_index is zero-based in the supplied order.
For geometry include a fully specified text AND a declarative schematic instead
of null: {"points":{"A":[0,0],"B":[4,0],...},"segments":[["A","B"],...]}
Coordinates are finite numbers, x rightward/y upward. Use only relevant labeled
points, at most16 points/32 segments. Never output SVG, HTML, code or outside URLs.
The figure must satisfy all stated incidence, parallel and ratio relations, but
must not print the answer. Non-geometry figures may be null. Do not claim any
source citation, human/scientific review or release eligibility.
Data:
''' + json.dumps(data,ensure_ascii=True)


def parse_candidate(raw):
    if not isinstance(raw,str) or len(raw.encode('utf8'))>64000:raise ValueError('Oversized/missing response')
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('Duplicate JSON key')
            out[k]=v
        return out
    q=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(q,dict) or set(q)!={'text','options','answer_index','solution','design','figure'}:
        raise ValueError('Wrong candidate fields')
    def prose(s,limit):return isinstance(s,str) and bool(s.strip()) and len(s)<=limit and all(ord(c)>=32 or c=='\n' for c in s)
    if not prose(q['text'],12000) or not prose(q['solution'],10000):raise ValueError('Malformed prose')
    if (not isinstance(q['options'],list) or len(q['options'])!=4
        or any(not prose(x,1500) for x in q['options']) or len({x.strip() for x in q['options']})!=4
        or type(q['answer_index']) is not int or not 0<=q['answer_index']<4):raise ValueError('Malformed options')
    keys={'givens','unknown','domains','essential_insight','structural_departure','tempting_wrong_route'}
    if not isinstance(q['design'],dict) or set(q['design'])!=keys or any(not prose(v,3000) for v in q['design'].values()):
        raise ValueError('Malformed design')
    validate_figure(q['figure'])
    return q


def validate_figure(figure):
    if figure is None:return
    if not isinstance(figure,dict) or set(figure)!={'points','segments'}:raise ValueError('Unsupported diagram')
    points=figure['points'];segments=figure['segments']
    if not isinstance(points,dict) or not 2<=len(points)<=16 or not isinstance(segments,list) or len(segments)>32:
        raise ValueError('Diagram limits exceeded')
    for label,xy in points.items():
        if not re.fullmatch(r'[A-Z][0-9]?',label) or not isinstance(xy,list) or len(xy)!=2:
            raise ValueError('Invalid point')
        if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1000000 for v in xy):
            raise ValueError('Invalid coordinates')
    if len({tuple(xy) for xy in points.values()})!=len(points):raise ValueError('Coincident named points')
    for segment in segments:
        if (not isinstance(segment,list) or len(segment)!=2 or any(not isinstance(p,str) or p not in points for p in segment)
                or segment[0]==segment[1]):raise ValueError('Invalid segment')


def figure_svg(figure):
    validate_figure(figure)
    if figure is None:return None
    points=figure['points'];xs=[xy[0] for xy in points.values()];ys=[xy[1] for xy in points.values()]
    dx=max(xs)-min(xs);dy=max(ys)-min(ys)
    if max(dx,dy)==0:raise ValueError('Degenerate diagram')
    span=max(dx,dy)
    coords={k:(45+(xy[0]-min(xs))/span*330,375-(xy[1]-min(ys))/span*330) for k,xy in points.items()}
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 430 430" direction="ltr" role="img" aria-label="Question geometry schematic">'
    for a,b in figure['segments']:
        p,q=coords[a],coords[b]
        svg+=f'<line x1="{p[0]:.3f}" y1="{p[1]:.3f}" x2="{q[0]:.3f}" y2="{q[1]:.3f}" stroke="#555" stroke-width="1.6"/>'
    for label,(x,y) in coords.items():
        svg+=f'<circle cx="{x:.3f}" cy="{y:.3f}" r="2" fill="#555"/><text x="{x+5:.3f}" y="{y-7:.3f}" font-size="16">{html.escape(label)}</text>'
    return svg+'</svg>'


class BenchmarkStore:
    def __init__(self,root):self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)

    def folder(self,item_id):
        if not re.fullmatch(r'pair-\d{2}-(baseline|design_conditioned)',item_id):raise ValueError('Invalid item id')
        path=self.root/'items'/item_id;path.mkdir(parents=True,exist_ok=True);return path

    def freeze_assignment(self,assignment):
        path=self.root/'assignment.json'
        old=saved_json(path,None)
        if old is not None and old!=assignment:raise ValueError('Frozen assignment cannot change')
        if old is None:atomic_json(path,assignment)

    def state(self,item_id):return saved_json(self.folder(item_id)/'state.json',None)

    def begin(self,item_id,binding):
        prior=self.state(item_id)
        if prior is not None:
            if prior['binding']!=binding:raise ValueError('Item binding changed')
            return False
        atomic_json(self.folder(item_id)/'state.json',dict(state='in_flight',binding=binding,eligible=False))
        return True

    def finish(self,item_id,outcome):
        prior=self.state(item_id)
        if prior is None:raise ValueError('Item not started')
        if prior['state'] in FINAL:raise ValueError('Final outcomes are immutable')
        if outcome.get('state') not in FINAL or outcome.get('eligible') is not False:
            raise ValueError('Invalid outcome')
        atomic_json(self.folder(item_id)/'state.json',{**outcome,'binding':prior['binding']})

    def recover(self,item_id):
        prior=self.state(item_id)
        if not prior or prior['state']!='in_flight':return
        folder=self.folder(item_id)
        events=saved_json(folder/'transport-events.json',[])
        candidates=[]
        for event in events:
            if event.get('http_status')==200 and event.get('finish_reason')=='stop':
                candidates.extend(f for f in event.get('fragments',[]) if f.get('kind')=='visible_content')
        if candidates:
            digest=candidates[-1]['sha256']
            if not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('Invalid response reference')
            raw=(folder/('fragment-'+digest+'.txt')).read_bytes()
            import hashlib
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Response fragment changed')
            try:
                q=parse_candidate(raw.decode('utf8'));atomic_json(folder/'candidate.json',q)
                self.finish(item_id,dict(state='drafted',response_sha256=digest,recovered=True,eligible=False))
            except (ValueError,TypeError):
                self.finish(item_id,dict(state='protocol_held',response_sha256=digest,recovered=True,eligible=False))
        else:
            self.finish(item_id,dict(state='interrupted_unknown',recovered=True,eligible=False,
                reason='No saved complete response; request consumption unknown, no silent retry'))

    def summary(self,items):
        counts={s:0 for s in sorted(FINAL)};pending=0;arms={a:{s:0 for s in sorted(FINAL)} for a in ('baseline','design_conditioned')}
        for item in items:
            state=self.state(item['item_id'])
            if state and state['state'] in FINAL:
                counts[state['state']]+=1;arms[item['arm']][state['state']]+=1
            else:pending+=1
        return dict(planned=len(items),completed=sum(counts.values()),pending=pending,outcomes=counts,arms=arms,release_eligible=0)
