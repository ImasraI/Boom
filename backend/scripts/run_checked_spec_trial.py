"""Single free-tier model call selecting typed specs, followed by local construction."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.model_spec_adapter import build_checked_variant
from app.rag.exam_corpus import atomic_json


def main():
    from app.config import get_settings
    from app.rag.llm import get_llm_client,MockLLMClient
    from app.rag.pool_usage import stage
    root=Path(__file__).resolve().parents[2]
    out=root/'backend/data/authoring_work/checked-spec-trial-v1'
    out.mkdir(parents=True,exist_ok=True)
    if (out/'status.json').exists():raise ValueError('Preserve existing run; no automatic repeat call')
    s=get_settings();provider=(s.POOL_LLM_PROVIDER or s.LLM_PROVIDER).lower()
    if provider not in ('groq','gemini'):raise ValueError('Only configured free-tier provider allowed')
    key=s.POOL_LLM_API_KEY or (s.GEMINI_API_KEY if provider=='gemini' else s.LLM_API_KEY)
    model=s.POOL_LLM_MODEL_NAME or s.LLM_MODEL_NAME
    client=get_llm_client(provider=provider,api_key=key,model=model)
    if isinstance(client,MockLLMClient):raise ValueError('Missing real client')
    client.json_mode=True
    prompt='''Select these two supported specifications exactly once each, in any order.
Return JSON {"specs":[{"family":"...","params":{}},...]}, no other fields.
Allowed families: quadratic_open_interval_count; conditional_dice_divisibility.
Both have no configurable parameters at this revision. Do not supply wording,
answers, code, difficulty or review claims. A local constructor owns the math.
This is supported-template selection, not a claim that you invented the designs.'''
    state={'status':'started','provider':provider,'model':model,'eligible':False,
           'role':'LLM selects typed specs; constructor supplies final questions',
           'corpus_text_sent':False,'maximum_generate_calls':1}
    atomic_json(out/'status.json',state)
    try:
        with stage('model_evaluation'):
            raw=client.generate([{'role':'user','content':prompt}],max_tokens=700,timeout=90)
        if not raw:raise ValueError('No model response')
        digest=hashlib.sha256(raw.encode()).hexdigest()
        (out/(digest+'.txt')).write_text(raw,encoding='utf8')
        def unique(pairs):
            obj={}
            for k,v in pairs:
                if k in obj:raise ValueError('Duplicate JSON key')
                obj[k]=v
            return obj
        data=json.loads(raw,object_pairs_hook=unique)
        if set(data)!={'specs'} or not isinstance(data['specs'],list) or len(data['specs'])!=2:
            raise ValueError('Malformed batch')
        checked=[build_checked_variant(json.dumps(spec)) for spec in data['specs']]
        if {c['candidate']['family'] for c in checked}!={'quadratic_open_interval_count','conditional_dice_divisibility'}:
            raise ValueError('Missing or repeated family')
        atomic_json(out/('checked-'+digest+'.json'),{'items':checked,'human_reviewed':False,'eligible':False})
        questions=[];solutions=[]
        for i,item in enumerate(checked,1):
            c=item['candidate'];c['id']=f'checked-spec:{i}'
            questions.append({k:c[k] for k in ('id','stem','options','svg')})
            solutions.append({k:c[k] for k in ('id','answer_index','answer_latex','proof','checks')})
        node=shutil.which('node')
        if not node:raise ValueError('Existing Node runtime unavailable')
        rendered=subprocess.run([node,str(root/'frontend/tools/render-authoring-trial.cjs'),str(out)],
            input=json.dumps({'questions':questions,'solutions':solutions}),text=True,
            encoding='utf8',capture_output=True,timeout=45)
        if rendered.returncode:raise ValueError('Render failed')
        state.update(status='checked_unpublished',count=2,response_sha256=digest,
                     render=json.loads(rendered.stdout),originality_approved=False)
    except Exception as error:
        state.update(status='held',error_type=type(error).__name__)
    atomic_json(out/'status.json',state)
    print(json.dumps(state))


if __name__=='__main__':main()
