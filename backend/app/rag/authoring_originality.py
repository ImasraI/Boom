"""Conservative copy screening; a pass is never an originality approval."""
import re
from difflib import SequenceMatcher

VERSION = 'originality-screen-0.1'


def originality_contract():
    return '''
ORIGINALITY_CONTRACT_V1
Transfer an insight, not an example's construction. Before prose, specify the
givens, unknown, essential constraints, representation and shortest solution.
Changing numbers, names, option order, or merely asking for another quantity in
the same construction is a practice variant, not evidence of a new design.
Change the mathematical relationships and the necessary reasoning path. Explain
what remains invariant and what changes. These explanations are model claims,
not independent novelty verification. Do not claim human review or originality.
Keep originality separate from difficulty. Remain inside the supplied curriculum scope.
'''


def normalized_structure(text):
    """Ignores scalar changes; not a mathematical or semantic equivalence test."""
    text = text.translate(str.maketrans('يك۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩',
                                      'یک01234567890123456789')).lower()
    text = re.sub(r'\d+(?:[.,٫]\d+)?', ' NUMBER ', text)
    return ' '.join(re.findall(r'\w+|[^\w\s]', text))


def screen(text, references):
    """Return reasons and reference IDs only. Never copy private source text."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError('A nonempty question stem is required')
    target = normalized_structure(text)
    matches = []
    for reference in references:
        source = normalized_structure(reference['text'])
        ratio = SequenceMatcher(None, target, source, autojunk=False).ratio()
        if target == source or ratio >= .85:
            matches.append({'reference_id': reference['id'],
                            'reason': 'scalar_normalized_copy' if target == source else 'high_surface_similarity',
                            'similarity': round(ratio, 4)})
    return {'version': VERSION, 'state': 'held_close_variant' if matches else 'pending_semantic_review',
            'matches': matches, 'originality_approved': False,
            'coverage': 'only supplied references; no semantic or corpus-wide guarantee'}
