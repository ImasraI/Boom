"""Local v2 authoring contract. Structural validation never grants correctness."""
import copy
import html
import json
import math
import re
from app.rag.authoring_benchmark import parse_candidate
from app.rag.reasoning_tags import REGISTRY

VERSION = 'pedagogical-authoring-0.2'
TECHNIQUES = frozenset(x for x in REGISTRY if x.startswith('tech.'))


def prose(value, limit=12000):
    return (isinstance(value,str) and bool(value.strip()) and len(value)<=limit
            and all(ord(c)>=32 or c=='\n' for c in value))


def exact(value, keys, label):
    if not isinstance(value,dict) or set(value)!=set(keys):
        raise ValueError('Unexpected fields: '+label)


def validate_pedagogy(p):
    exact(p,['key_observation','steps','proposed_techniques','boundary_checks',
             'answer_justification','alternative_route'],'pedagogy')
    if not prose(p['key_observation']) or not prose(p['answer_justification']):
        raise ValueError('Missing teaching explanation')
    if not isinstance(p['steps'],list) or not 1<=len(p['steps'])<=30:
        raise ValueError('Missing/bounded solution steps')
    ids=set()
    for step in p['steps']:
        exact(step,['id','explanation','math'],'step')
        if (not isinstance(step['id'],str) or not re.fullmatch(r's[1-9][0-9]?',step['id'])
                or step['id'] in ids or not prose(step['explanation']) or not prose(step['math'])):
            raise ValueError('Invalid or repeated solution step')
        ids.add(step['id'])
    if not isinstance(p['proposed_techniques'],list) or len(p['proposed_techniques'])>12:
        raise ValueError('Invalid technique proposals')
    seen=set()
    for tag in p['proposed_techniques']:
        exact(tag,['id','role','step_ids','evidence','symmetry_witness'],'technique')
        if not isinstance(tag['id'],str) or tag['id'] not in TECHNIQUES or tag['id'] in seen or tag['role'] not in ('primary','supporting','check'):
            raise ValueError('Unknown/repeated technique or role')
        refs=tag['step_ids']
        if (not isinstance(refs,list) or not refs or any(not isinstance(s,str) or s not in ids for s in refs)
                or len(set(refs))!=len(refs) or not prose(tag['evidence'])):
            raise ValueError('Technique needs visible step evidence')
        seen.add(tag['id'])
        witness=tag['symmetry_witness']
        if tag['id']=='tech.symmetry':
            exact(witness,['transformation','preserved','conclusion'],'symmetry witness')
            if any(not prose(v) for v in witness.values()):raise ValueError('Incomplete symmetry witness')
        elif witness is not None:raise ValueError('Unexpected symmetry witness')
    if (not isinstance(p['boundary_checks'],list) or len(p['boundary_checks'])>20
            or any(not prose(v) for v in p['boundary_checks'])):
        raise ValueError('Invalid boundary explanations')
    if p['alternative_route'] is not None and not prose(p['alternative_route']):
        raise ValueError('Invalid alternative route')


def circles(figure):
    result=figure.get('circles',[]) if isinstance(figure,dict) else []
    if not isinstance(result,list) or len(result)>5:raise ValueError('Invalid circles')
    for circle in result:
        exact(circle,['center','through'],'circle')
        if any(not isinstance(circle[k],str) or circle[k] not in figure['points'] for k in circle):
            raise ValueError('Circle references unknown point')
        c,p=(figure['points'][circle[k]] for k in ('center','through'))
        radius=math.hypot(c[0]-p[0],c[1]-p[1])
        if not 1e-9<=radius<=2000000:raise ValueError('Degenerate circle')
    return result


def parse_pedagogical_candidate(raw):
    if not isinstance(raw,str) or len(raw.encode())>128000:raise ValueError('Missing/oversized candidate')
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('Repeated JSON key')
            d[k]=v
        return d
    q=json.loads(raw,object_pairs_hook=unique)
    exact(q,['text','options','answer_index','solution','design','figure','pedagogy','verification_record'],'candidate')
    old={k:copy.deepcopy(v) for k,v in q.items() if k not in ('pedagogy','verification_record')}
    if old['figure'] is not None:
        exact(old['figure'],['points','segments','circles'],'figure')
        old['figure'].pop('circles')
    parse_candidate(json.dumps(old,ensure_ascii=False))
    if q['figure'] is not None:circles(q['figure'])
    validate_pedagogy(q['pedagogy'])
    verify=q['verification_record']
    exact(verify,['method','summary','claimed_by'],'verification')
    if (verify['method'] not in ('analytic','symbolic','finite_enumeration','mixed')
            or not prose(verify['summary']) or verify['claimed_by']!='author_model'):
        raise ValueError('Invalid author verification claim')
    return q


def teaching_holds(q):
    """These missing-evidence holds supplement, not replace, human/math review."""
    p=q['pedagogy'];result=[]
    if not p['proposed_techniques']:result.append('techniques_unresolved')
    if not p['boundary_checks']:result.append('boundary_checks_unresolved')
    return result


def render_figure(figure):
    if figure is None:return None
    points=figure['points'];cs=circles(figure)
    xs=[p[0] for p in points.values()];ys=[p[1] for p in points.values()]
    for c in cs:
        a,b=(points[c[k]] for k in ('center','through'));r=math.dist(a,b)
        xs.extend([a[0]-r,a[0]+r]);ys.extend([a[1]-r,a[1]+r])
    x0,y0=min(xs),min(ys);span=max(max(xs)-x0,max(ys)-y0)
    if not math.isfinite(span) or span<=0:raise ValueError('Invalid diagram extent')
    xy=lambda p:(45+(p[0]-x0)/span*330,375-(p[1]-y0)/span*330)
    out=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 430 430" direction="ltr" role="img" aria-label="Question geometry schematic">']
    for c in cs:
        a,b=(points[c[k]] for k in ('center','through'));x,y=xy(a);r=math.dist(a,b)/span*330
        out.append(f'<circle cx="{x:.6f}" cy="{y:.6f}" r="{r:.6f}" fill="none" stroke="#777" stroke-width="1.5"/>')
    for a,b in figure['segments']:
        x,y=xy(points[a]);u,v=xy(points[b]);out.append(f'<line x1="{x:.6f}" y1="{y:.6f}" x2="{u:.6f}" y2="{v:.6f}" stroke="#555" stroke-width="1.6"/>')
    for label,p in points.items():
        x,y=xy(p);out.append(f'<circle cx="{x:.6f}" cy="{y:.6f}" r="2.5" fill="#555"/><text x="{x+6:.6f}" y="{y-7:.6f}" fill="#333" font-size="13">{html.escape(label)}</text>')
    return ''.join(out)+'</svg>'


def prompt_for(spec):
    return '''Write ONE original Persian Konkur-style mathematics multiple-choice question.
Use only the generic facts and scope supplied below. No source question is supplied.
Build a compact necessary insight; do not just substitute numbers into a theorem.
The assigned mechanism must actually drive the solution. Merely naming a different
theorem does not make the same similarity chain a new design. Do not imitate the
previous parallel-section tasks. Do not assign difficulty or claim originality approval.
Return JSON only, exact top-level keys: text,options,answer_index,solution,design,
figure,pedagogy,verification_record. Four distinct nonempty options; answer_index 0..3.
text/options may use $LaTeX$. All other prose/math uses plain Unicode, no LaTeX commands.
solution: FULL student-facing derivation, not just an answer or a verification result.
design: {givens,unknown,domains,essential_insight,structural_departure,tempting_wrong_route},
all six values nonempty strings. Design novelty is a proposal, never an approval.
pedagogy: {key_observation,steps,proposed_techniques,boundary_checks,
answer_justification,alternative_route}. Explain WHY the key observation applies.
steps: [{id:"s1",explanation:"...",math:"..."}, ...]; reference existing step IDs.
proposed_techniques: [{id:"tech...",role:"primary|supporting|check",step_ids:["s1"],
evidence:"specific visible application",symmetry_witness:null}]. Use ONLY supplied
technique IDs. For tech.symmetry, symmetry_witness must be an object with nonempty
transformation,preserved,conclusion. Symmetric givens never alone justify a=b.
boundary_checks: array of explanations for relevant domain/sign/degeneracy cases.
answer_justification: why exactly this option follows. alternative_route: string or null.
verification_record: {method:"analytic|symbolic|finite_enumeration|mixed",
summary:"check the mathematics, separate from teaching",claimed_by:"author_model"}.
Prefer a conceptual teaching derivation over avoidable exhaustive listing.
Extrema need a global bound AND an attainable equality case. Respect point order.
figure: null for non-geometry, or {points:{A:[0,0],...},segments:[["A","B"],...],
circles:[{center:"O",through:"A"}]}. All names A..Z optionally followed by one digit.
At most16 distinct finite points,32 segments,5 circles; x right/y up. Specify every
needed geometric relation in the text; the figure must agree and not reveal the answer.
Never emit HTML, SVG, executable code, URLs or a claim of human/scientific approval.
Input:\n'''+json.dumps({'spec':spec,'allowed_proposed_technique_ids':sorted(TECHNIQUES)},ensure_ascii=True)
