"""Unpublished, spec-first math construction. No config/DB/provider imports.

These eight supported families are an offline constructor trial, not a benchmark
of the production Groq/Gemini generator. No difficulty labels or bank activation.
Only allowlisted numeric parameters are consumed; no model code is executed.
"""
from fractions import Fraction as F
import itertools
import random
import sympy as S

VERSION="sandbox-0.1"
FAMILIES=("absolute_line_intersections","trig_domain_level_set","ordered_cubic_roots",
          "cevian_area_ratio","vector_norm_minimum","coupled_grid_count",
          "digit_reversal_congruence","conditional_third_draw")


def _integer(params,name,default,minimum=1,maximum=100):
    value=params.get(name,default)
    if type(value) is not int or not minimum<=value<=maximum:raise ValueError("Invalid bounded integer parameter")
    return value


def _area(a,b,c):
    return abs(S.det(S.Matrix([[a[0],a[1],1],[b[0],b[1],1],[c[0],c[1],1]])))/2


def solve(family,params):
    """Exact supported-family solution and checks, separate from options/prose."""
    if family not in FAMILIES:raise ValueError("Unsupported family")
    allowed={"absolute_line_intersections":{"a","b"},"cevian_area_ratio":{"width","height"},
             "digit_reversal_congruence":{"difference"}}.get(family,set())
    if set(params)-allowed:raise ValueError("Unexpected parameters; executable expressions are not accepted")
    checks=[];figure=None
    if family=="absolute_line_intersections":
        a=_integer(params,"a",2);b=_integer(params,"b",7)
        if a>=b:raise ValueError("Require0<a<b")
        def count(m):
            roots=set()
            for slope,constant,lo,hi in [(-2-m,0,None,F(a)),(-m,F(-2*a),F(a),F(b)),(2-m,F(-2*(a+b)),F(b),None)]:
                if slope==0:
                    if constant==0:return "infinite"
                    continue
                x=-constant/slope
                if (lo is None or x>=lo) and (hi is None or x<=hi):roots.add(x)
            return len(roots)
        probes={F(n,7) for n in range(-35,36)}|{F(-2),F(2),F(-2*a,b),F(0)}
        assert all((count(m)==2)==(-2<m<2) for m in probes)
        answer=S.Interval.open(-2,2)
        checks=["Piecewise equations retain domain bounds and deduplicate shared endpoints.",
                "m=-2 gives infinitely many left-branch solutions; m=2 gives one.",
                "Exact rational branch-count probes agree with the analytically derived interval."]
        proof=f"On x≤{a}, the equation reduces to (m+2)x=0, giving x=0 except at m=-2. The middle root is -{2*a}/m when admissible; the right root is {2*(a+b)}/(2-m) when admissible. One additional distinct root exists exactly for -2<m<2; the transition at m=-{2*a}/{b} is a single shared breakpoint, not two roots."
    elif family=="trig_domain_level_set":
        x=S.symbols("x",real=True)
        assert S.trigsimp(S.expand_trig(S.sin(3*x)-S.sin(x))-2*S.sin(x)*S.cos(2*x))==0
        holes=[S.pi/4,3*S.pi/4]
        assert all(S.simplify(2*S.sin(h)-S.sqrt(2))==0 for h in holes)
        answer=S.Complement(S.Interval.open(0,2),S.FiniteSet(S.sqrt(2)))
        checks=["Identity verified symbolically without redefining the original domain.","Both removed domain points have level sqrt(2); level2 has only one preimage."]
        proof="The numerator is2sin(x)cos(2x). The original function equals2sin(x) only on(0,π) excluding π/4 and3π/4. Levels in(0,2) ordinarily have two preimages, but both preimages of sqrt(2) are removed. Level2 has one preimage;0 has none in the open interval."
    elif family=="ordered_cubic_roots":
        x,w=S.symbols("x w",real=True)
        poly=x**3-6*x**2+9*x+4
        middle_candidates=S.solve(w*(6-w)+1-9,w)
        survivors=[]
        for mid in middle_candidates:
            k=poly.subs(x,mid);roots=S.real_roots(poly-k)
            if len(set(roots))==3 and roots[1]==mid and S.simplify(roots[0]*roots[2]-1)==0:survivors.append(k)
        assert survivors==[S.Integer(6)]
        answer=survivors[0]
        checks=["All algebraic middle-root candidates tested against the original cubic, distinctness and ordering.","At k=8 the repeated root invalidates the proposed three-distinct-root condition."]
        proof="Coefficient comparison in(x-r1)(x-r2)(x-r3) gives r1+r2+r3=6 and r1r2+r1r3+r2r3=9. With r1r3=1, r2(6-r2)=8, so r2=2 or4. The candidate4 gives k=8 and roots1,1,4, which fail distinctness and ordering. For r2=2, k=6 and roots2−√3,2,2+√3 meet every condition."
    elif family=="cevian_area_ratio":
        width=_integer(params,"width",6);height=_integer(params,"height",6)
        A=S.Point(0,height);B=S.Point(0,0);C=S.Point(width,0);D=S.Point(S.Rational(width,2),0)
        t=S.symbols("t",real=True);P=A+t*(D-A)
        # The area relation gives t/(2(1-t))=2 with0<t<1.
        value=S.solve(t-4*(1-t),t)[0];P=P.subs(t,value)
        E=S.Line(B,P).intersection(S.Line(A,C))[0]
        assert 0<value<1 and S.simplify(_area(P,A,B)-2*_area(P,B,C))==0
        answer=S.simplify(_area(P,D,E)/_area(A,B,C))
        assert answer==S.Rational(1,15)
        figure={name:[str(point.x),str(point.y)] for name,point in dict(A=A,B=B,C=C,D=D,E=E,P=P).items()}
        checks=["Nondegenerate triangle, midpoint, two incidences and given area ratio checked exactly.","Requested area ratio computed independently with a determinant."]
        proof="Because D is the midpoint of BC, [PAB]/[PBC]=AP/(2PD)=2, hence AP:PD=4:1. The same area relation gives AE:EC=2:1. Thus[ADE]/[ABC]=1/3 and[PDE]/[ADE]=PD/AD=1/5. The requested ratio is1/15."
    elif family=="vector_norm_minimum":
        t=S.symbols("t",real=True);dot=S.Rational(5-7,4)
        squared=S.expand((t+1)**2+(t-1)**2+2*(t+1)*(t-1)*dot)
        assert squared==t**2+3 and 1-dot**2>0
        answer=S.sqrt(squared.subs(t,0))
        checks=["Gram determinant positive: the two unit vectors exist and are nonparallel.","Squared norm is t²+3 for all real t; the minimum is attained at t=0."]
        proof="From|2u−v|²=7 and|u|=|v|=1, u·v=−1/2. Also(u+v)·(u−v)=0. The requested vector is t(u+v)+(u−v); its squared norm is t²+3. The minimum norm is√3, attained at t=0."
    elif family=="coupled_grid_count":
        count=0
        for cells in itertools.product(range(3),repeat=6):
            top,bottom=cells[:3],cells[3:]
            if len(set(top))==3 and len(set(bottom))==3 and sum(a==b for a,b in zip(top,bottom))==1:count+=1
        assert count==18
        answer=S.Integer(count)
        checks=["All729 labelled colour assignments enumerated;18 satisfy both row and column conditions.","Independent combinatorial count:6 top rows times3 choices for the unique matching column."]
        proof="The top row has3!=6 colour orders. Choose the unique column whose two cells agree in3 ways. The remaining two bottom colours must be swapped relative to the top row; otherwise more columns agree. Total6×3=18. Row independence cannot be assumed before applying the cross-row condition."
    elif family=="digit_reversal_congruence":
        difference=_integer(params,"difference",27)
        if difference%9:raise ValueError("Digit-reversal difference must be a multiple of9")
        values=[n for n in range(10,100) if n%10 and n-(10*(n%10)+n//10)==difference and n*n%7==2]
        answer=S.Integer(len(values))
        checks=["Every two-digit value with two nonzero digits tested exactly; no floating point or sampling.","For difference27, modular reasoning and enumeration both give52 and74."]
        proof=f"Write n=10a+b with1≤a,b≤9. Reversal changes it by9(a−b), so a−b={difference//9}. For the displayed instance b=a−3 and n=11a−3. The condition n²≡2(mod7) means n≡3 or4(mod7), giving a=5 or7 in the admissible digit range. The numbers are52 and74, so the count is2."
        # The wording/proof currently supports the displayed instance only.
        if difference!=27:raise ValueError("Only the audited difference27 wording is supported")
    else:
        numerator=F(0);denominator=F(0)
        for whites,prior in [(3,F(1,3)),(1,F(2,3))]:
            balls=list(range(4))
            for draws in itertools.permutations(balls,3):
                colors=[d<whites for d in draws]
                if colors[0]!=colors[1]:
                    weight=prior/F(24);denominator+=weight
                    if colors[2]:numerator+=weight
        answer=S.Rational(numerator.numerator,numerator.denominator)/S.Rational(denominator.numerator,denominator.denominator)
        assert answer==S.Rational(1,3) and denominator==F(1,2)
        checks=["All24 ordered three-ball draws per urn weighted by exact priors.","Observation includes both possible first-two colour orders, with no replacement."]
        proof="The first two colours differ with probability1/2 in either urn, so observing this does not change the urn prior. Afterwards urn A has two white balls left and urn B has two black balls left. Therefore the third ball is white exactly when urn A was chosen, with probability1/3."
    return dict(answer=answer,proof=proof,checks=checks,figure=figure)


def construct(family,params=None,seed=0):
    params={} if params is None else dict(params)
    solved=solve(family,params)
    if family=="absolute_line_intersections":
        a=params.get("a",2);b=params.get("b",7)
        stem=fr"تابع $f(x)=|x-{a}|+|x-{b}|$ روی $\mathbb R$ تعریف شده است. برای کدام مقادیر حقیقی $m$، خط $y=mx+{a+b}$ نمودار تابع را دقیقاً در دو نقطهٔ متمایز قطع می‌کند؟"
        options=[S.Interval.open(-2,2),S.Interval(-2,2),S.Interval.Lopen(-2,2),S.Interval.Ropen(-2,2)]
    elif family=="trig_domain_level_set":
        stem=r"تابع $f(x)=\frac{\sin 3x-\sin x}{\cos 2x}$ را برای $0<x<\pi$ و با دامنهٔ ناشی از همین کسر در نظر بگیرید. مجموعهٔ همهٔ اعداد حقیقی $a$ که معادلهٔ $f(x)=a$ دقیقاً دو جواب متمایز دارد، کدام است؟"
        options=[S.Complement(S.Interval.open(0,2),S.FiniteSet(S.sqrt(2))),S.Interval.open(0,2),S.Complement(S.Interval.Lopen(0,2),S.FiniteSet(S.sqrt(2))),S.Complement(S.Interval.Ropen(0,2),S.FiniteSet(S.sqrt(2)))]
    elif family=="ordered_cubic_roots":
        stem=r"معادلهٔ $x^3-6x^2+9x+4=k$ سه ریشهٔ حقیقی متمایز $r_1<r_2<r_3$ دارد. اگر $r_1r_3=1$ باشد، مقدار $k$ کدام است؟"
        options=list(map(S.Integer,[4,6,8,12]))
    elif family=="cevian_area_ratio":
        stem=r"در مثلث $ABC$، نقطهٔ $D$ وسط $BC$ است. نقطهٔ $E$ روی پاره‌خط $AC$ قرار دارد و $AD$ و $BE$ در نقطهٔ داخلی $P$ یکدیگر را قطع می‌کنند. اگر مساحت مثلث $PAB$ دو برابر مساحت مثلث $PBC$ باشد، نسبت مساحت مثلث $PDE$ به مساحت مثلث $ABC$ کدام است؟"
        options=[S.Rational(1,10),S.Rational(1,12),S.Rational(1,15),S.Rational(2,15)]
    elif family=="vector_norm_minimum":
        stem=r"دو بردار $\vec u$ و $\vec v$ به طول واحد داریم و $|2\vec u-\vec v|=\sqrt7$ است. کمترین مقدار $|(t+1)\vec u+(t-1)\vec v|$ به ازای $t\in\mathbb R$ کدام است؟"
        options=[S.Integer(1),S.sqrt(2),S.sqrt(3),S.Integer(2)]
    elif family=="coupled_grid_count":
        stem=r"خانه‌های یک جدول $2\times3$ را با سه رنگ آبی، قرمز و سبز رنگ می‌کنیم؛ هر خانه دقیقاً یک رنگ دارد. در هر سطر هر سه رنگ باید دیده شوند و دقیقاً در یک ستون، دو خانه هم‌رنگ باشند. چند رنگ‌آمیزی متفاوت ممکن است؟"
        options=list(map(S.Integer,[6,12,18,36]))
    elif family=="digit_reversal_congruence":
        stem=r"یک عدد طبیعی دورقمی با دو رقم غیرصفر، پس از جابه‌جایی رقم‌هایش $27$ واحد کوچک‌تر می‌شود. اگر باقی‌ماندهٔ مربع عدد اولیه در تقسیم بر $7$ برابر $2$ باشد، چند عدد اولیهٔ متفاوت ممکن است؟"
        options=list(map(S.Integer,[1,2,3,4]))
    else:
        stem=r"کیسهٔ $A$ شامل سه مهرهٔ سفید و یک مهرهٔ سیاه و کیسهٔ $B$ شامل یک مهرهٔ سفید و سه مهرهٔ سیاه است. کیسهٔ $A$ با احتمال $\frac13$ و کیسهٔ $B$ با احتمال $\frac23$ انتخاب می‌شود. از همان کیسه سه مهره پیاپی و بدون جایگذاری برمی‌داریم. اگر بدانیم دو مهرهٔ اول رنگ‌های متفاوت دارند، احتمال سفیدبودن مهرهٔ سوم کدام است؟"
        options=[S.Rational(1,3),S.Rational(5,12),S.Rational(1,2),S.Rational(2,3)]
    random.Random(seed).shuffle(options)
    if len(set(options))!=4 or sum(v==solved["answer"] for v in options)!=1:raise ValueError("Ambiguous or absent answer")
    return dict(family=family,parameters=params,stem=stem,options=["$"+S.latex(v)+"$" for v in options],
                answer_index=options.index(solved["answer"]),answer_latex=S.latex(solved["answer"]),
                proof=solved["proof"],checks=solved["checks"],figure=solved["figure"],
                difficulty=None,empirical_difficulty=None,eligible=False,verification_kind="exact_supported_family_not_blind_model_review")


def validate_candidate(candidate):
    """Recompute a supported specification and check key/options against it."""
    try:
        solved=solve(candidate["family"],candidate["parameters"])
        if type(candidate.get("answer_index")) is not int or not 0<=candidate["answer_index"]<4:raise ValueError("Invalid key")
        options=candidate["options"]
        if len(options)!=4 or len(set(options))!=4:raise ValueError("Duplicate or missing options")
        expected=construct(candidate["family"],candidate["parameters"],seed=0)
        if set(options)!=set(expected["options"]):raise ValueError("Options outside audited canonical pool")
        if candidate.get("stem")!=expected["stem"]:raise ValueError("Wording/spec mismatch; unreviewed paraphrases must be held")
        if candidate.get("answer_latex")!=expected["answer_latex"]:raise ValueError("Displayed answer mismatch")
        key="$"+S.latex(solved["answer"])+"$"
        if options[candidate["answer_index"]]!=key or options.count(key)!=1:raise ValueError("Key disagrees with exact solver")
        if candidate.get("figure")!=solved["figure"]:raise ValueError("Figure/spec mismatch")
        if candidate.get("eligible") is not False or candidate.get("difficulty") is not None:raise ValueError("Sandbox cannot promote or label difficulty")
        return dict(valid=True,eligible=False,checks=solved["checks"],limitations=["human_exam_likeness_pending","blind_solve_pending","prose_spec_equivalence_review_pending"])
    except (KeyError,TypeError,ValueError,AssertionError) as exc:
        return dict(valid=False,eligible=False,reason=str(exc))
