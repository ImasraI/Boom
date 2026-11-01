"""One bounded unpublished provider trial. Sends synthetic scope, not corpus text."""
import hashlib
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_originality import originality_contract, screen
from app.rag.exam_corpus import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    from app.config import get_settings
    from app.rag.llm import get_llm_client, MockLLMClient
    from app.rag.pool_usage import stage

    settings = get_settings()
    provider = (settings.POOL_LLM_PROVIDER or settings.LLM_PROVIDER).strip().lower()
    # Only the existing free-tier providers; no generic endpoint or paid fallback.
    if provider not in {'groq', 'gemini'}:
        raise ValueError('Trial requires an existing free-tier Groq/Gemini configuration')
    model = settings.POOL_LLM_MODEL_NAME or settings.LLM_MODEL_NAME
    key = settings.POOL_LLM_API_KEY or settings.LLM_API_KEY
    if provider == 'gemini':
        key = settings.POOL_LLM_API_KEY or settings.GEMINI_API_KEY
    client = get_llm_client(provider=provider, api_key=key, model=model)
    if isinstance(client, MockLLMClient):
        raise ValueError('No configured provider credential; no simulated success')
    client.json_mode = True
    prompt = originality_contract() + '''
This is an unpublished Persian grade-12 math-only pilot, not a release.
Write TWO distinct multiple-choice questions: one within conditional probability
and finite counting, another within quadratic functions and real-domain constraints.
Use ordinary Iranian high-school mathematics; avoid advanced theorems.
Do not use urns/bags, digit reversal, triangle cevians, absolute-value graph
intersections, cubic roots, or trigonometric cancellation. Those constructions
were used in a prior trial. Do not merely rename their objects.
Do not assign difficulty labels. Supply checkable short solutions, four distinct
options and an answer_index from 0 to 3. Output JSON only:
{"questions":[{"text":"Persian stem with $LaTeX$","options":["..."],
"answer_index":0,"solution":"checkable solution", "design":{
"givens":"...","unknown":"...","constraints":"...",
"essential_insight":"...","shortest_route":"...",
"structural_change":"..."}}]}
No external retrieval, source claims, human approval or executable code.
'''
    if args.attempt == 2:
        prompt += '''
Previous attempt failed: an unconditional union probability was too routine;
a quadratic minimum silently assumed an unstated integer parameter. Avoid both.
Question 1 MUST require conditioning on an observed event in a finite sampling
experiment WITHOUT urns or bag renaming. State sampling rules explicitly.
Question 2 MUST state all parameter domains and whether any bound is attained.
Use a meaningful interaction of constraints, not a direct formula exercise.
Include a counterexample/shortcut check in each solution. Do not respond with
the earlier class-membership union problem or a coefficient minimum from two values.
'''
    destination = Path(__file__).resolve().parents[1] / f'data/authoring_work/model-authoring-trial-v1/attempt-{args.attempt}'
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / 'status.json').exists():
        raise ValueError('Attempt already exists; preserve its evidence instead of overwriting')
    result = {'provider': provider, 'model': model, 'published': False,
              'eligible_count': 0, 'human_reviewed': False, 'difficulty': None,
              'corpus_text_sent': False, 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
              'status': 'started', 'maximum_generate_calls': 1}
    atomic_json(destination / 'status.json', result)
    try:
        with stage('model_evaluation'):
            raw = client.generate([{'role': 'user', 'content': prompt}], max_tokens=4000, timeout=90)
        if not raw:
            result['status'] = 'held_provider_no_content'
        else:
            digest = hashlib.sha256(raw.encode()).hexdigest()
            (destination / (digest + '.txt')).write_text(raw, encoding='utf8')
            result['response_sha256'] = digest
            data = json.loads(raw)
            questions = data.get('questions')
            if not isinstance(questions, list) or len(questions) != 2:
                raise ValueError('Expected exactly two questions')
            for question in questions:
                if (not isinstance(question, dict) or not isinstance(question.get('text'), str)
                    or not isinstance(question.get('options'), list) or len(question['options']) != 4
                    or any(not isinstance(o, str) or not o.strip() for o in question['options'])
                    or len(set(question['options'])) != 4
                    or type(question.get('answer_index')) is not int
                    or not 0 <= question['answer_index'] <= 3
                    or not isinstance(question.get('solution'), str)):
                    raise ValueError('Malformed model question')
                question['originality_screen'] = screen(question['text'], [])
                question['verification_state'] = 'pending_independent_checks'
                question['eligible'] = False
            atomic_json(destination / ('candidate-' + digest + '.json'), data)
            result.update(status='drafted_pending_checks', count=2)
    except Exception as error:
        # No raw errors: upstream bodies can contain credentials or private URLs.
        result.update(status='held_error', error_type=type(error).__name__)
    atomic_json(destination / 'status.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
