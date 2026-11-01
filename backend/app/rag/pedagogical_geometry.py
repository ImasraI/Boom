"""Typed coordinate checks for v2 figures, never a proof of the question."""
import math
from app.rag.authoring_benchmark import validate_figure
from app.rag.pedagogical_authoring import circles
from app.rag.figure_constraints import audit_relations,TOLERANCE
from app.rag.exam_corpus import payload_digest


def audit(figure,relations):
    if not isinstance(figure,dict) or set(figure)!={'points','segments','circles'}:raise ValueError('Typed figure required')
    validate_figure({k:v for k,v in figure.items() if k!='circles'});cs=circles(figure)
    if not isinstance(relations,list) or not 1<=len(relations)<=64:raise ValueError('Bounded claims required')
    pts=figure['points'];coordinates=list(pts.values())
    distances=[math.dist(a,b) for i,a in enumerate(coordinates) for b in coordinates[i+1:]]
    scale=max(distances)
    if min(distances)/scale<1e-10:raise ValueError('Numerically indistinct points')
    def p(label):
        if not isinstance(label,str) or label not in pts:raise ValueError('Unknown point')
        return pts[label]
    def names(value,count=None):
        if (not isinstance(value,list) or not value or any(not isinstance(s,str) or s not in pts for s in value)
                or len(set(value))!=len(value) or (count is not None and len(value)!=count)):
            raise ValueError('Invalid point references')
        return [p(x) for x in value]
    def vector(a,b):return b[0]-a[0],b[1]-a[1]
    def unit(v):
        length=math.hypot(*v)
        if length<=0:raise ValueError('Zero vector')
        return v[0]/length,v[1]/length
    def cross(a,b):return a[0]*b[1]-a[1]*b[0]
    results=[]
    for claim in relations:
        if not isinstance(claim,dict):raise ValueError('Invalid claim')
        kind=claim.get('kind')
        if kind in ('collinear','on_segment','parallel','length_ratio'):
            r=audit_relations({k:v for k,v in figure.items() if k!='circles'},[claim])['results'][0]
            results.append(r);continue
        if kind=='on_circle':
            if set(claim)!={'kind','circle','points'} or type(claim['circle']) is not int or not 0<=claim['circle']<len(cs):
                raise ValueError('Invalid circle incidence')
            points=names(claim['points']);circle=cs[claim['circle']];o=p(circle['center']);r=math.dist(o,p(circle['through']))
            residual=max(abs(math.dist(o,x)/r-1) for x in points)
            passed=residual<=TOLERANCE;metrics={'maximum_relative_radial_error':residual}
        elif kind=='point_circle_position':
            if (set(claim)!={'kind','circle','point','position'} or type(claim['circle']) is not int
                    or not 0<=claim['circle']<len(cs) or claim['position'] not in ('inside','on','outside')):
                raise ValueError('Invalid circle-position claim')
            c=cs[claim['circle']];o=p(c['center']);r=math.dist(o,p(c['through']));ratio=math.dist(o,p(claim['point']))/r
            passed={'inside':ratio<1-TOLERANCE,'on':abs(ratio-1)<=TOLERANCE,'outside':ratio>1+TOLERANCE}[claim['position']]
            metrics={'radius_normalized_distance':ratio}
        elif kind=='tangent':
            if (set(claim)!={'kind','circle','point','line'} or type(claim['circle']) is not int
                    or not 0<=claim['circle']<len(cs)):
                raise ValueError('Invalid tangent claim')
            c=cs[claim['circle']];o=p(c['center']);t=p(claim['point']);a,b=names(claim['line'],2)
            r=math.dist(o,p(c['through']));radial=vector(o,t);u=unit(vector(a,b))
            if math.hypot(*radial)<=0:raise ValueError('Circle center is not a tangency point')
            v=unit(radial);dot=abs(u[0]*v[0]+u[1]*v[1]);incidence=abs(cross(u,vector(a,t)))/scale
            radial_error=abs(math.hypot(*radial)/r-1)
            passed=max(dot,incidence,radial_error)<=TOLERANCE
            metrics={'radial_error':radial_error,'normalized_dot':dot,'normalized_line_incidence':incidence}
        elif kind=='perpendicular':
            if set(claim)!={'kind','segments'} or not isinstance(claim['segments'],list) or len(claim['segments'])!=2:
                raise ValueError('Invalid perpendicular claim')
            a,b=names(claim['segments'][0],2);c,d=names(claim['segments'][1],2)
            u,v=unit(vector(a,b)),unit(vector(c,d));residual=abs(u[0]*v[0]+u[1]*v[1])
            passed=residual<=TOLERANCE;metrics={'normalized_dot':residual}
        elif kind=='reflection':
            if set(claim)!={'kind','source','image','axis'}:raise ValueError('Invalid reflection claim')
            x,y=p(claim['source']),p(claim['image']);a,b=names(claim['axis'],2);u=unit(vector(a,b));v=vector(a,x)
            t=v[0]*u[0]+v[1]*u[1];foot=(a[0]+t*u[0],a[1]+t*u[1])
            expected=(2*foot[0]-x[0],2*foot[1]-x[1]);residual=math.dist(y,expected)/scale
            passed=residual<=TOLERANCE;metrics={'normalized_reflection_error':residual}
        elif kind=='angle_degrees':
            if set(claim)!={'kind','points','value'}:raise ValueError('Invalid angle claim')
            a,o,b=names(claim['points'],3);u,v=unit(vector(o,a)),unit(vector(o,b));expected=claim['value']
            if type(expected) not in (int,float) or not math.isfinite(expected) or not 0<expected<=180:
                raise ValueError('Invalid expected angle')
            actual=math.degrees(math.atan2(abs(cross(u,v)),u[0]*v[0]+u[1]*v[1]))
            passed=abs(actual-expected)<=1e-5;metrics={'actual_degrees':actual,'expected_degrees':expected}
        elif kind=='triangle_area':
            if set(claim)!={'kind','points','value'}:raise ValueError('Invalid area claim')
            a,b,c=names(claim['points'],3);value=claim['value']
            if not isinstance(value,list) or len(value)!=2 or any(type(x) is not int or not 0<x<=1000000 for x in value):
                raise ValueError('Positive rational area required')
            actual=abs(cross(vector(a,b),vector(a,c)))/2;expected=value[0]/value[1]
            passed=math.isclose(actual,expected,rel_tol=TOLERANCE,abs_tol=TOLERANCE)
            metrics={'actual':actual,'expected':expected}
        elif kind=='convex_polygon':
            if set(claim)!={'kind','points'}:raise ValueError('Invalid polygon claim')
            vertices=names(claim['points'])
            if not 3<=len(vertices)<=16:raise ValueError('Bounded polygon required')
            signs=[]
            for i,a in enumerate(vertices):
                b=vertices[(i+1)%len(vertices)];u=unit(vector(a,b))
                for j,c in enumerate(vertices):
                    if j in (i,(i+1)%len(vertices)):continue
                    signs.append(cross(u,unit(vector(a,c))))
            passed=all(s>TOLERANCE for s in signs) or all(s < -TOLERANCE for s in signs)
            metrics={'strict_same_side_edges':passed}
        else:raise ValueError('Unknown coordinate claim')
        results.append({'claim':claim,'passed':passed,'metrics':metrics})
    return {'all_passed':all(x['passed'] for x in results),'results':results,'tolerance':TOLERANCE,
            'meaning':'Coordinates against supplied claims only; claim extraction and mathematics still need review',
            'eligible':False,'human_scientific_review':False}


def bound_audit(candidate,claim_record):
    if (not isinstance(claim_record,dict) or set(claim_record)!=
            {'schema_version','candidate_sha256','figure_sha256','relations'} or claim_record['schema_version']!='0.2'):
        raise ValueError('Malformed claims')
    if (claim_record['candidate_sha256']!=payload_digest(candidate)
            or claim_record['figure_sha256']!=payload_digest(candidate.get('figure'))):
        raise ValueError('Stale geometry claim binding')
    return {'candidate_sha256':claim_record['candidate_sha256'],'claims_sha256':payload_digest(claim_record),
            'audit':audit(candidate.get('figure'),claim_record['relations']),'eligible':False}
