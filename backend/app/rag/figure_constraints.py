"""Check typed assistant-declared relations against a candidate schematic.

This verifies coordinates against supplied claims, not claims against a source
or question. No expression execution, scientific approval or curriculum inference.
"""
import math
from app.rag.authoring_benchmark import validate_figure
from app.rag.exam_corpus import payload_digest

TOLERANCE=1e-7


def audit_bound_relations(candidate,claims):
    if (not isinstance(claims,dict) or set(claims)!={'schema_version','candidate_sha256','figure_sha256','relations'}
            or claims['schema_version']!='0.1'):
        raise ValueError('Malformed bound claims')
    if claims['candidate_sha256']!=payload_digest(candidate) or claims['figure_sha256']!=payload_digest(candidate.get('figure')):
        raise ValueError('Stale candidate/figure claims')
    result=audit_relations(candidate.get('figure'),claims['relations'])
    return dict(schema_version='0.1',candidate_sha256=claims['candidate_sha256'],
        figure_sha256=claims['figure_sha256'],claims_sha256=payload_digest(claims),audit=result,
        relation_extraction_review='unreviewed_assistant_proposal',human_scientific_review=False,eligible=False)


def audit_relations(figure,relations):
    validate_figure(figure)
    if figure is None:raise ValueError('A diagram is required')
    if not isinstance(relations,list) or not 1<=len(relations)<=64:raise ValueError('Bounded relations required')
    points=figure['points']
    distances=[math.hypot(a[0]-b[0],a[1]-b[1]) for i,a in enumerate(points.values())
        for b in list(points.values())[i+1:]]
    if min(distances)/max(distances)<1e-10:raise ValueError('Numerically indistinct diagram points')
    def point(label):
        if not isinstance(label,str) or label not in points:raise ValueError('Unknown point')
        return points[label]
    def vector(a,b):
        p,q=point(a),point(b);return q[0]-p[0],q[1]-p[1]
    def pair(labels):
        if not isinstance(labels,list) or len(labels)!=2 or labels[0]==labels[1]:raise ValueError('Invalid segment')
        return vector(*labels)
    def length(v):return math.hypot(*v)
    def normalized_cross(u,v):
        a,b=length(u),length(v)
        return abs((u[0]/a)*(v[1]/b)-(u[1]/a)*(v[0]/b))
    results=[]
    for claim in relations:
        if not isinstance(claim,dict):raise ValueError('Invalid relation')
        kind=claim.get('kind')
        if kind in ('collinear','on_segment'):
            if set(claim)!={'kind','points'}:raise ValueError('Unexpected relation fields')
            labels=claim['points']
            if (not isinstance(labels,list) or len(labels)!=3 or any(not isinstance(p,str) for p in labels)
                    or len(set(labels))!=3):raise ValueError('Three distinct points required')
            a,p,b=labels;u=vector(a,b);v=vector(a,p)
            cross=normalized_cross(u,v)
            t=((u[0]/length(u))*v[0]+(u[1]/length(u))*v[1])/length(u)
            passed=cross<=TOLERANCE and (kind=='collinear' or -TOLERANCE<=t<=1+TOLERANCE)
            metric=dict(normalized_cross=cross,segment_parameter=t)
        elif kind in ('parallel','length_ratio'):
            expected={'kind','segments'}|({'value'} if kind=='length_ratio' else set())
            if set(claim)!=expected:raise ValueError('Unexpected relation fields')
            segments=claim['segments']
            if not isinstance(segments,list) or len(segments)!=2:raise ValueError('Two segments required')
            u,v=map(pair,segments)
            if kind=='parallel':
                residual=normalized_cross(u,v)
                metric=dict(normalized_cross=residual);passed=residual<=TOLERANCE
            else:
                value=claim['value']
                if not isinstance(value,list) or len(value)!=2 or any(type(x) is not int or not 0<x<=1000000 for x in value):
                    raise ValueError('Positive rational ratio required')
                actual=length(u)/length(v);expected=value[0]/value[1]
                metric=dict(actual=actual,expected=expected)
                passed=math.isclose(actual,expected,rel_tol=TOLERANCE,abs_tol=TOLERANCE)
        else:raise ValueError('Unknown relation kind')
        results.append(dict(claim=claim,passed=passed,metrics=metric))
    return dict(tolerance=TOLERANCE,results=results,all_passed=all(r['passed'] for r in results),
        meaning='Coordinate/claim consistency only; relation extraction and scientific correctness are unapproved',eligible=False)
