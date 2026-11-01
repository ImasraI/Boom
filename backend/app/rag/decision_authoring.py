"""Draft decision/distractor sidecars. Shape checks never verify model claims."""
import hashlib
import json
import math
from app.rag.exam_corpus import payload_digest
from app.rag.pedagogical_authoring import parse_pedagogical_candidate,exact,prose,circles
from app.rag.pedagogical_policy import prompt_v03

VERSION='decision-authoring-0.1'
METHODS={'bounds','sign_units','option_testing','special_case','symmetry','diagram_measurement','wording_cues'}
OUTCOMES={'valid_shortcut','unintended_leakage','unsupported_guess','unresolved'}


def text(value):
    if not prose(value,6000):raise ValueError('Missing bounded explanation')


def texts(values,minimum=1,maximum=12):
    if not isinstance(values,list) or not minimum<=len(values)<=maximum:raise ValueError('Bounded explanation list required')
    for value in values:text(value)


def validate_proposals(q,p):
    exact(p,['distractors','shortcut_audit','fast_route','figure_checks'],'audit proposals')
    ds=p['distractors']
    if not isinstance(ds,list) or len(ds)!=3:raise ValueError('Exactly three distractor proposals required')
    wrong=set(range(4))-{q['answer_index']};seen=set()
    for d in ds:
        exact(d,['option_index','error_hypothesis','first_invalid_step','derivation_steps','derived_option','why_invalid'],'distractor')
        index=d['option_index']
        if type(index) is not int or index not in wrong or index in seen:raise ValueError('Distractor targets must cover wrong options once')
        seen.add(index)
        for k in ('error_hypothesis','first_invalid_step','why_invalid'):text(d[k])
        texts(d['derivation_steps'])
        if d['derived_option']!=q['options'][index]:raise ValueError('Distractor does not bind its proposed option')
    attacks=p['shortcut_audit']
    if not isinstance(attacks,list) or not 3<=len(attacks)<=len(METHODS):raise ValueError('Three or more shortcut hypotheses required')
    seen=set();step_ids={s['id'] for s in q['pedagogy']['steps']}
    for a in attacks:
        exact(a,['method','outcome','conditions','argument','counterexample','step_ids'],'shortcut')
        if not isinstance(a['method'],str) or a['method'] not in METHODS or a['method'] in seen:raise ValueError('Unknown or repeated attack method')
        seen.add(a['method'])
        if not isinstance(a['outcome'],str) or a['outcome'] not in OUTCOMES:raise ValueError('Unknown shortcut outcome')
        for k in ('conditions','argument'):text(a[k])
        if a['counterexample'] is not None:text(a['counterexample'])
        refs=a['step_ids']
        if not isinstance(refs,list) or len(refs)>30 or any(not isinstance(s,str) or s not in step_ids for s in refs) or len(set(refs))!=len(refs):
            raise ValueError('Stale shortcut step references')
    fast=p['fast_route']
    if fast is not None:
        exact(fast,['conditions','derivation_steps','conclusion','failure_case'],'fast route')
        text(fast['conditions']);texts(fast['derivation_steps']);text(fast['conclusion'])
        if fast['failure_case'] is not None:text(fast['failure_case'])
    fig=p['figure_checks']
    exact(fig,['mode','small_segment_risk','label_plan','preserved_relations','relaxed_metric_relations'],'figure checks')
    if fig['mode'] not in ('none','exact','schematic'):raise ValueError('Unknown figure fidelity mode')
    for k in ('small_segment_risk','label_plan'):
        if fig[k] is not None:text(fig[k])
    texts(fig['preserved_relations'],0);texts(fig['relaxed_metric_relations'],0)
    if q['figure'] is None:
        if fig!={'mode':'none','small_segment_risk':None,'label_plan':None,'preserved_relations':[],'relaxed_metric_relations':[]}:
            raise ValueError('No figure cannot claim geometry checks')
    elif fig['mode']=='none' or not fig['preserved_relations'] or fig['label_plan'] is None:
        raise ValueError('Illustration needs a declared fidelity and label plan')
    if fig['mode']=='exact' and fig['relaxed_metric_relations']:raise ValueError('Exact illustration cannot relax metric claims')
    if fig['mode']=='schematic' and not fig['relaxed_metric_relations']:raise ValueError('Schematic needs explicit metric exceptions')
    return p


def parse_envelope(raw):
    if not isinstance(raw,str) or len(raw.encode())>192000:raise ValueError('Missing or oversized envelope')
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('Duplicate envelope key')
            out[k]=v
        return out
    envelope=json.loads(raw,object_pairs_hook=unique)
    exact(envelope,['candidate','audit_proposals'],'decision envelope')
    q=parse_pedagogical_candidate(json.dumps(envelope['candidate'],ensure_ascii=False))
    validate_proposals(q,envelope['audit_proposals'])
    return envelope


def load_candidate(folder,state):
    sha=state['response_sha256']
    if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Unsafe response reference')
    raw=(folder/(sha+'.txt')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Changed response')
    envelope=parse_envelope(raw.decode('utf8'));q=envelope['candidate']
    if json.loads((folder/'candidate.json').read_text(encoding='utf8'))!=q:raise ValueError('Changed candidate projection')
    if json.loads((folder/'audit-proposals.json').read_text(encoding='utf8'))!=envelope['audit_proposals']:raise ValueError('Changed proposal projection')
    return q,None


def readability(figure,width=320,minimum_segment_px=18):
    """Matches current SVG projection; heuristic flags, not visual approval."""
    if type(width) is not int or not 200<=width<=1200:raise ValueError('Bounded display width required')
    if type(minimum_segment_px) not in (int,float) or not math.isfinite(minimum_segment_px) or not 1<=minimum_segment_px<=60:
        raise ValueError('Bounded readable segment threshold required')
    if figure is None:return {'not_applicable':True,'flags':[],'visual_review':None}
    # Reuse full shape validation, including finite points, before arithmetic.
    from app.rag.authoring_benchmark import validate_figure
    validate_figure({k:v for k,v in figure.items() if k!='circles'});cs=circles(figure)
    points=figure['points'];xs=[v[0] for v in points.values()];ys=[v[1] for v in points.values()]
    for c in cs:
        o=points[c['center']];r=math.dist(o,points[c['through']]);xs.extend([o[0]-r,o[0]+r]);ys.extend([o[1]-r,o[1]+r])
    span=max(max(xs)-min(xs),max(ys)-min(ys));scale=width*330/(430*span)
    segments=[{'segment':s,'projected_pixels':round(math.dist(points[s[0]],points[s[1]])*scale,3)} for s in figure['segments']]
    return {'figure_sha256':payload_digest(figure),'display_width':width,'minimum_segment_px':minimum_segment_px,
            'segments':segments,'flags':[{'kind':'short_segment','segment':r['segment']} for r in segments if r['projected_pixels']<minimum_segment_px],
            'visual_review':None,'limitations':['Does not detect all label collisions, apparent tangency or answer-revealing constructions.'],
            'eligible':False}


def prompt_for(spec):
    return prompt_v03(spec)+'''
DECISION_AUTHORING_V1: The earlier candidate top-level keys describe ONLY the
candidate object. Return ONE JSON envelope with exactly candidate,audit_proposals.
candidate follows that unchanged question schema. audit_proposals has exactly:
distractors,shortcut_audit,fast_route,figure_checks. All explanations in Persian.
distractors: exactly three records, one per WRONG option:
{option_index:0..3,error_hypothesis:"...",first_invalid_step:"...",
derivation_steps:["..."],derived_option:"EXACT matching option string",why_invalid:"..."}.
Derive the wrong result through that specific error; do not rationalize arbitrary
numbers. Wrong routes must be plausible hypotheses, never claims about student data.
shortcut_audit: at least three distinct methods among bounds,sign_units,option_testing,
special_case,symmetry,diagram_measurement,wording_cues; each record:
{method:"...",outcome:"valid_shortcut|unintended_leakage|unsupported_guess|unresolved",
conditions:"...",argument:"...",counterexample:null or "...",step_ids:["s1"]}.
Do not hide a valid efficient solution. A lucky example is not a universal proof.
fast_route: null, or {conditions:"...",derivation_steps:["..."],conclusion:"...",
failure_case:null or "..."}. Include only a defensible complete route, not an
unsupported assertion that it is fast. No time/success-rate claims.
figure_checks: {mode:"none|exact|schematic",small_segment_risk:null or "...",
label_plan:null or "...",preserved_relations:["..."],relaxed_metric_relations:["..."]}.
With figure=null use mode=none, both nullable strings=null and both lists empty.
For a figure, list preserved relations and a label plan. Exact figures relax no
metrics. Prefer readable valid parameters; never move a point off its stated line.
Schema compliance does not prove any distractor, shortcut, language or figure claim.
'''
