"""Local experimental authoring packets; never grant corpus or pool eligibility.

Only generic mathematical briefs leave the machine. Source summaries, page images,
IDs and receipts remain in the private packet. This is a small experiment, not the
production source-routing interface or a replacement for independent review.
"""
import json
import re

GENERATION_PROFILE = {
    'reasoning_effort': 'high',
    'completion_tokens': 16384,
    'generate_timeout_seconds': 180,
}


def configure_generation_client(client):
    """Generation only: explicit reasoning budget, separate from efficient OCR."""
    client.json_mode = True
    client.reasoning_effort = GENERATION_PROFILE['reasoning_effort']
    client.minimum_completion_tokens = GENERATION_PROFILE['completion_tokens']
    return dict(GENERATION_PROFILE)


BRIEFS = {
    'cubic_identity': {
        'pattern': 'Recognize cubic identities before choosing new variables; exploit relationships between symmetric quantities.',
        'facts': ['(a+b)^3 = a^3+b^3+3ab(a+b).',
                  '(a-b)^3 = a^3-b^3-3ab(a-b).'],
        'avoid': 'Do not give two disguised cubes and ask for their sum or difference. Do not use a radical expression with a prescribed conjugate product.'},
    'parallel_similarity': {
        'pattern': 'Introduce or exploit a parallel segment to transfer ratios through similar triangles.',
        'facts': ['A line parallel to one side of a triangle cuts the other two sides proportionally.',
                  'Parallel sections between two fixed straight transversals have proportional changes.'],
        'avoid': 'Do not use intersecting triangle cevians with given small triangle areas. A trapezoid or another genuinely different incidence structure is welcome.'},
    'residue_cycles': {
        'pattern': 'Reduce a large finite arithmetic task to residue classes or a short cycle, then count accurately.',
        'facts': ['Integers are congruent modulo a positive integer m exactly when their difference is divisible by m.',
                  'If a is congruent to b modulo m, their nonnegative integer powers are also congruent.'],
        'avoid': 'Do not sum tenth powers modulo eleven or merely change that prime and exponent. Do not use digit reversal.'},
}


def proxy_transport_status(provider='gemini'):
    """Credential-free TLS check, never a credential/quota/model availability claim."""
    import httpx
    urls={'gemini':'https://generativelanguage.googleapis.com/v1beta/models',
          'groq':'https://api.groq.com/openai/v1/models'}
    if provider not in urls:
        raise ValueError('Unsupported trial provider')
    try:
        with httpx.Client(proxy='http://127.0.0.1:10809', trust_env=False,
                          timeout=httpx.Timeout(12, connect=8)) as probe:
            response = probe.head(urls[provider])
            return dict(reachable=True, http_status=response.status_code, error_code=None,
                        credentials_sent=False)
    except httpx.HTTPError as error:
        return dict(reachable=False, http_status=None, error_code=type(error).__name__,
                    credentials_sent=False)


def trial_failure_code(code, reason):
    """Classify without storing upstream bodies, URLs or other error details."""
    if code:
        return code
    match=re.search(r'HTTP\s+(\d{3})',reason or '')
    if match:
        status=int(match.group(1))
        if status>=500:return 'provider_unavailable'
        if status in (401,403):return 'provider_access_denied'
        if status==429:return 'provider_rate_limit'
        if status==404:return 'provider_model_unavailable'
        return 'provider_request_rejected'
    if 'timeout' in (reason or '').lower():return 'provider_timeout'
    if any(x in (reason or '').lower() for x in ('ssl','connection','connect')):
        return 'provider_transport_error'
    return 'provider_empty_response'


def response_fragments(payload):
    """Keep visible generation fragments, never request headers or reasoning fields."""
    if not isinstance(payload,dict):return []
    result=[]
    error=payload.get('error')
    if isinstance(error,dict) and isinstance(error.get('failed_generation'),str):
        result.append(('failed_generation',error['failed_generation']))
    choices=payload.get('choices')
    if isinstance(choices,list):
        for choice in choices:
            message=choice.get('message') if isinstance(choice,dict) else None
            if isinstance(message,dict) and isinstance(message.get('content'),str):
                result.append(('visible_content',message['content']))
    return result


def prompt_for(brief_ids, revision=1):
    if len(brief_ids) != 3 or set(brief_ids) != set(BRIEFS):
        raise ValueError('This predeclared pilot needs each of the three briefs once')
    if revision not in (1,2):
        raise ValueError('Unsupported prompt revision')
    # Deliberately does not accept arbitrary source text, source IDs or credentials.
    prompt = '''Create three unpublished Persian high-school multiple-choice mathematics questions,
one for each brief below. These are mathematical design briefs, NOT source questions.
Invent new setups; do not just substitute numbers in a familiar example. No difficulty labels.
Quality matters more than length: each question needs a real decision, with at least two
interacting constraints, but no obscure theorem, gratuitous calculation or vague wording.
Use standard Iranian high-school notation, explicit domains, and exactly four distinct options.
Check existence, degeneracies, endpoint inclusion, attainability and exactly one correct option.
Solutions must derive the answer actually present among the options; never choose the closest.
Geometry must be fully specified in words even if a schematic is later added. Do not output SVG/code.
Output JSON only, with exactly {"questions": [ ... ]}. Each of three records must contain:
{"brief_id":"...", "text":"Persian with $LaTeX$", "options":["$...$","$...$","$...$","$...$"],
 "answer_index":0, "solution":"Short checkable solution in English, including boundary checks",
 "design":{"givens":"...","unknown":"...","domains":"...","essential_insight":"...",
 "structural_departure":"...","tempting_wrong_route":"..."}}
Answer index is zero-based. Do not claim review, originality certification, source provenance or publication.
Briefs:
''' + json.dumps([dict(brief_id=k, **BRIEFS[k]) for k in brief_ids], ensure_ascii=True)
    if revision==2:
        prompt+='''
Revision2 incorporates independent checks of a previous synthetic trial:
* A sum/product-of-two-reals identity followed by solving for their sum was correct
  but too routine. Algebra MUST instead require deciding feasibility, admissible
  parameter values or a constrained count using identities. Check REAL existence,
  not just formal algebra. Do not merely ask for a+b from ab and a^3+b^3.
* Geometry failed: with D on AB and DE parallel AC meeting BC at E, the correct
  similar pair is BDE/BAC, and DE/BC is not determined by AD/DB alone.
  Use a DIFFERENT incidence structure, e.g. a trapezoid with an intersection and
  parallel sections. Require at least two linked ratio deductions. Verify actual
  vertex correspondence and prove the target is fixed under allowed shape changes.
  Every point and needed relation must be specified in words; no missing figure.
* Counting integers in two fixed residue classes was correct but too routine.
  Modular question MUST combine a nontrivial short power cycle or polynomial
  remainder with a second admissibility/counting constraint. Do not just count
  an arithmetic progression from two linear congruences or invoke CRT by name.
For every item, first construct a consistent instance and independently recover
the requested answer. Include one explicit counterexample to the tempting wrong
route. All four options must be feasible output types and exactly one must be right.
Do not call changing variables, avoiding coordinates or reducing a large search
to one progression a structural departure by itself. State what relationships
and necessary decisions actually changed. Prefer a compact insightful problem
over contrived wording or huge calculations. Stay within the three brief topics.
'''
    return prompt


def parse_drafts(raw):
    if not isinstance(raw, str) or len(raw.encode('utf8')) > 64000:
        raise ValueError('Response is missing or too large')
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate JSON key')
            obj[key] = value
        return obj
    data = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(data, dict) or set(data) != {'questions'}:
        raise ValueError('Unexpected batch fields')
    questions = data['questions']
    if not isinstance(questions, list) or len(questions) != 3:
        raise ValueError('Exactly three drafts required')
    seen = set()
    def clean(value):
        # Mis-escaped LaTeX such as JSON "\frac" becomes a form-feed and
        # silently corrupts math. Newlines are the only permitted C0 controls.
        return isinstance(value,str) and all(ord(c)>=32 or c=='\n' for c in value)
    for q in questions:
        if not isinstance(q, dict) or set(q) != {'brief_id', 'text', 'options', 'answer_index', 'solution', 'design'}:
            raise ValueError('Unexpected question fields')
        if not isinstance(q['brief_id'], str) or q['brief_id'] not in BRIEFS or q['brief_id'] in seen:
            raise ValueError('Missing/repeated brief')
        seen.add(q['brief_id'])
        for field in ('text', 'solution'):
            if not clean(q[field]) or not q[field].strip() or len(q[field]) > 10000:
                raise ValueError('Invalid prose')
        if (not isinstance(q['options'], list) or len(q['options']) != 4
                or any(not clean(x) or not x.strip() or len(x) > 1000 for x in q['options'])
                or len({x.strip() for x in q['options']}) != 4
                or type(q['answer_index']) is not int or not 0 <= q['answer_index'] <= 3):
            raise ValueError('Invalid options or index')
        keys = {'givens', 'unknown', 'domains', 'essential_insight', 'structural_departure', 'tempting_wrong_route'}
        if not isinstance(q['design'], dict) or set(q['design']) != keys or any(
                not clean(v) or not v.strip() or len(v) > 3000 for v in q['design'].values()):
            raise ValueError('Incomplete design')
    return data  # Syntactic validity is not mathematical validity.
