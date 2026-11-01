"""Bounded local trial using calibrated topics and visually checked book pages.

Prepare is offline. Generate sends only the fixed generic mathematical briefs,
never the private source packet. One attempt per directory; no automatic repeats.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json, payload_digest
from app.rag.grounded_authoring_trial import (BRIEFS, GENERATION_PROFILE,
    configure_generation_client, parse_drafts, prompt_for, proxy_transport_status, trial_failure_code,
    response_fragments)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'backend/data/authoring_work'
OUT = BASE / 'grounded-authoring-trial-v1'
PAGES = [
    ('cubic_identity', 'lesson:e3a4bdc6b850cd2dbe', 'ریاضی 1 خیلی سبز.pdf', 156, 155),
    ('parallel_similarity', 'lesson:a8f6e20ec29f61beb5', 'هندسه 1 خیلی سبز.pdf', 60, 59),
    ('residue_cycles', 'lesson:ff7feb1fb4d5e376db', 'گسسته و آمار و احتمال جامع خیلی سبز.pdf', 48, 46),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_inputs(prompt_revision=1):
    # Read-only audit checks original packets, crop bindings and actual reviews.
    result = subprocess.run([sys.executable, str(ROOT/'backend/scripts/audit_calibrated_summaries.py')],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError('Current summary evidence audit failed')
    folder = BASE/'calibrated-design-summaries-v1'
    status = json.loads((folder/'status.json').read_text(encoding='utf8'))
    if status['retrievable_local_summaries'] != 3 or status['current_evidence_holds']:
        raise ValueError('Calibrated summaries no longer available')
    audit = json.loads((folder/status['latest_audit']).read_text(encoding='utf8'))
    if payload_digest(audit) != status['audit_sha256']:
        raise ValueError('Summary audit digest changed')
    selected = audit['selected_summaries']
    evidence = []
    for brief_id, knowledge_id, book, page, printed in PAGES:
        matches = [s for s in selected if s['knowledge_ids'] == [knowledge_id]]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous scoped summary')
        image = ROOT/'backend/data/1'/book/f'page_{page:04d}.png'
        ocr = ROOT/'backend/data/ocr'/book/f'page_{page:04d}.txt'
        evidence.append(dict(brief_id=brief_id, summary=matches[0],
            image_ref=image.relative_to(ROOT/'backend/data').as_posix(), image_sha256=sha(image),
            ocr_ref=ocr.relative_to(ROOT/'backend/data').as_posix(), ocr_sha256=sha(ocr),
            page_index_1based=page, printed_page=printed, source_role='test_book',
            factual_check=dict(kind='assistant_visual_check', checked_on='2026-10-26',
                scope='Generic facts in fixed brief verified against displayed page image',
                human_review=False, production_factual_eligibility=False)))
        if brief_id == 'residue_cycles':
            power_page = ROOT/'backend/data/1'/book/'page_0051.png'
            evidence[-1]['additional_fact_evidence'] = dict(
                image_ref=power_page.relative_to(ROOT/'backend/data').as_posix(),
                image_sha256=sha(power_page), page_index_1based=51, printed_page=49,
                checked_by='assistant_visual_check', human_review=False,
                scope='Congruences preserved by positive integer powers; exponent zero is immediate')
    return dict(schema_version='0.1', experiment_revision=prompt_revision, evidence=evidence,
        confirmation_sha256=status['sha256'], summary_audit_sha256=status['audit_sha256'],
        prompt_sha256=hashlib.sha256(prompt_for(list(BRIEFS),prompt_revision).encode()).hexdigest(),
        protocol=dict(planned_drafts=3, maximum_generate_calls=1,
            generation_profile=dict(GENERATION_PROFILE),
            purpose='Local design-conditioned pilot; no source literals sent',
            checks=['source_binding_current', 'explicit_domains_and_existence',
                    'independent_math_derivation', 'unique_option_and_correct_key',
                    'design_departure_screen', 'render_check'],
            release_eligibility=False, blind_model_solve=False,
            human_design_judgment='pending_for_new_questions',
            limitations=['Three-example convenience sample; no population quality estimate',
                'Test-book page checks are not official-textbook review receipts',
                'Structural novelty needs human review; string screening is insufficient']))


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'generate'])
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--provider', choices=['groq', 'gemini'])
    parser.add_argument('--prompt-revision',type=int,choices=[1,2],default=1)
    parser.add_argument('--use-local-proxy', action='store_true',
                        help='Use the existing loopback HTTP proxy for this trial client only')
    args = parser.parse_args()
    if not 1 <= args.attempt <= 999:
        raise ValueError('Attempt must be a positive bounded integer')
    if Path.cwd().resolve() != ROOT/'backend':
        raise ValueError('Run from backend so the existing private environment resolves correctly')
    if args.attempt != 1:
        OUT = OUT/f'attempt-{args.attempt}'
    packet = current_inputs(args.prompt_revision)
    OUT.mkdir(parents=True, exist_ok=True)
    name = 'packet-'+payload_digest(packet)+'.json'
    if args.action == 'prepare':
        if not (OUT/name).exists():
            atomic_json(OUT/name, packet)
        atomic_json(OUT/'packet-status.json', dict(packet=name, sha256=payload_digest(packet),
            summaries=3, book_pages=4, provider_calls=0, eligible=False))
        print(json.dumps(dict(status='prepared', summaries=3, book_pages=4, provider_calls=0)))
        return
    saved = json.loads((OUT/'packet-status.json').read_text())
    if saved['packet'] != name or saved['sha256'] != payload_digest(packet):
        raise ValueError('Packet changed; prepare and inspect new evidence first')
    if json.loads((OUT/name).read_text(encoding='utf8')) != packet:
        raise ValueError('Stored packet changed')
    if (OUT/'status.json').exists():
        raise ValueError('Attempt already exists; preserve response and quota state')
    from app.config import get_settings
    from app.rag.llm import get_llm_client, MockLLMClient, GeminiLLMClient
    from app.rag.pool_usage import stage
    from app.rag.provider_quota import groq_keys, pool_gemini_generation_keys, blocked_access, blocked_quota, rate_limited
    settings = get_settings()
    provider = args.provider or (settings.POOL_LLM_PROVIDER or settings.LLM_PROVIDER).lower()
    if provider not in ('groq', 'gemini'):
        raise ValueError('Existing free-tier provider required')
    model = settings.GEMINI_MODEL_NAME if provider == 'gemini' else (settings.POOL_LLM_MODEL_NAME or settings.LLM_MODEL_NAME)
    client = None
    if provider in ('groq', 'gemini'):
        client = None
        # Inspect saved state only. Never probe refused keys or reset their quotas.
        keys = groq_keys(settings, pool=True) if provider == 'groq' else pool_gemini_generation_keys(settings)
        for candidate_key in keys:
            if args.use_local_proxy and provider == 'gemini':
                candidate = GeminiLLMClient(api_key=candidate_key, base_url=settings.GEMINI_BASE_URL,
                    model=model, temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS, proxy='http://127.0.0.1:10809')
            else:
                candidate = get_llm_client(provider=provider, api_key=candidate_key, model=model)
                if args.use_local_proxy:
                    import httpx
                    old_transport=candidate.client
                    candidate.client=httpx.Client(proxy='http://127.0.0.1:10809',trust_env=False,
                        timeout=candidate.timeout,follow_redirects=True,headers=dict(old_transport.headers))
                    old_transport.close()
            identity = candidate._quota_identity
            if not (blocked_access(identity) or blocked_quota(identity) or rate_limited(identity)):
                client = candidate
                break
            candidate.client.close()
        if client is None:
            raise ValueError('No configured free-tier credential currently available')
    if isinstance(client, MockLLMClient):
        raise ValueError('Real configured provider required')
    profile = configure_generation_client(client)
    state = dict(status='started', packet_sha256=payload_digest(packet), provider=provider,
        model=model, maximum_generate_calls=1, corpus_text_sent=False, eligible_count=0,
        transport_retry_policy='existing provider client; terminal quota/access not retried')
    state['network_route'] = 'loopback_http_proxy' if args.use_local_proxy else 'configured_client_route'
    state['generation_profile'] = profile
    state['prompt_revision'] = args.prompt_revision
    atomic_json(OUT/'status.json', state)
    response_count=0
    def capture_response(response):
        nonlocal response_count
        response_count+=1
        response.read()
        try:body=response.json()
        except ValueError:body={}
        entries=[]
        for kind,fragment in response_fragments(body):
            digest=hashlib.sha256(fragment.encode()).hexdigest()
            target=OUT/('fragment-'+digest+'.txt')
            if not target.exists():target.write_bytes(fragment.encode('utf8'))
            entries.append(dict(kind=kind,sha256=digest))
        atomic_json(OUT/f'http-response-{response_count:03d}.json',
            dict(status=response.status_code,fragments=entries,request_headers_saved=False,
                 reasoning_fields_saved=False))
    client.client.event_hooks['response'].append(capture_response)
    started = time.monotonic()
    try:
        if args.use_local_proxy:
            # No auth or model request: detect a dead proxy before spending time
            # in the provider client's transport retries. Any HTTP response means
            # TLS reached the service, not that a credential/model has access.
            transport = proxy_transport_status(provider)
            state['credential_free_transport'] = transport
            if not transport['reachable']:
                state['provider_error_code'] = 'proxy_transport_unavailable'
                raise ValueError('Local proxy cannot complete provider TLS connection')
        with stage('model_evaluation'):
            raw = client.generate([dict(role='user', content=prompt_for(list(BRIEFS),args.prompt_revision))],
                                  max_tokens=profile['completion_tokens'],
                                  timeout=profile['generate_timeout_seconds'])
        if not raw:
            state['provider_error_code'] = trial_failure_code(
                getattr(client, 'last_error_code', ''),getattr(client, 'last_error', ''))
            raise ValueError('No response')
        digest = hashlib.sha256(raw.encode()).hexdigest()
        (OUT/(digest+'.txt')).write_bytes(raw.encode('utf8'))
        state['response_sha256'] = digest
        parsed = parse_drafts(raw)
        atomic_json(OUT/('drafts-'+digest+'.json'), parsed)
        if payload_digest(current_inputs(args.prompt_revision)) != payload_digest(packet):
            raise ValueError('Source evidence changed during generation; preserve draft but hold it')
        state.update(status='drafted_pending_independent_checks', draft_count=3)
    except Exception as error:
        state.update(status='held', error_type=type(error).__name__)
    state['elapsed_seconds'] = round(time.monotonic()-started, 3)
    usage = getattr(client, 'last_usage', None)
    if hasattr(usage, '_asdict'):
        state['token_usage'] = usage._asdict()
    client.client.close()
    atomic_json(OUT/'status.json', state)
    print(json.dumps(state))


if __name__ == '__main__':
    main()
