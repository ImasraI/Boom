"""Local full captured-data export. No live calls or credential discovery."""
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest


def main():
    root=Path(__file__).resolve().parents[1]/'data/authoring_work/development-benchmark-v1'
    read=lambda p:json.loads(p.read_text(encoding='utf8'))
    assignment=read(root/'assignment.json');pointer=read(root/'review-pointer.json')
    if not re.fullmatch(r'review-[0-9a-f]{64}',pointer['folder']):raise ValueError('Invalid review path')
    binding=read(root/pointer['folder']/'binding.json')
    if payload_digest(binding)!=pointer['binding_sha256']:raise ValueError('Changed review binding')
    aliases={r['item_id']:dict(alias=r['alias'],display_number=i) for i,r in enumerate(binding['records'],1)}
    records=[];files={}
    for item,expected in assignment['prompt_sha256'].items():
        if not re.fullmatch(r'pair-\d{2}-(baseline|design_conditioned)',item):raise ValueError('Invalid item path')
        folder=root/'items'/item;prompt=(folder/'prompt.txt').read_bytes()
        if hashlib.sha256(prompt).hexdigest()!=expected:raise ValueError('Changed saved prompt')
        state=read(folder/'state.json')
        if state['binding']['assignment_sha256']!=payload_digest(assignment) or state['binding']['prompt_sha256']!=expected:
            raise ValueError('Changed executed assignment')
        request={'model':assignment['model'],'messages':[{'role':'user','content':prompt.decode('utf8')}],
                 'temperature':assignment['temperature'],'max_tokens':assignment['profile']['completion_tokens'],
                 'reasoning_effort':assignment['profile']['reasoning_effort'],'response_format':{'type':'json_object'}}
        events=read(folder/'transport-events.json');visible=[]
        for event in events:
            for fragment in event['fragments']:
                if fragment['kind']!='visible_content':raise ValueError('Non-visible fragment excluded')
                digest=fragment['sha256']
                if not re.fullmatch(r'[a-f0-9]{64}',digest):raise ValueError('Invalid fragment hash')
                raw=(folder/('fragment-'+digest+'.txt')).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Changed visible response')
                visible.append({'kind':fragment['kind'],'sha256':digest,'text':raw.decode('utf8')})
                files[item+'/visible-fragment-'+digest+'.txt']=raw
        response=None
        if state.get('response_sha256'):
            digest=state['response_sha256']
            if not re.fullmatch(r'[a-f0-9]{64}',digest):raise ValueError('Invalid response hash')
            raw=(folder/(digest+'.txt')).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Changed returned content')
            response=raw.decode('utf8');files[item+'/returned-content.txt']=raw
        candidate=read(folder/'candidate.json') if (folder/'candidate.json').is_file() else None
        record={'item_id':item,**aliases.get(item,{'alias':None,'display_number':None}),
                'arm':state['binding']['arm'],'saved_prompt_sha256':expected,
                'initial_request_body_reconstructed_not_wire_capture':request,
                'state':state,'captured_transport_events':events,
                'captured_visible_fragments':visible,'returned_content_exact':response,'parsed_candidate':candidate}
        records.append(record);files[item+'/prompt.txt']=prompt
        for name,data in [('initial-request.reconstructed.json',request),('state.json',state),('transport-events.json',events)]:
            files[item+'/'+name]=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
        if candidate is not None:files[item+'/candidate.json']=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode()
    export={'schema_version':'0.1','model':assignment['model'],'provider':assignment['provider'],
            'protocol_sha256':assignment['protocol_sha256'],'assignment_sha256':payload_digest(assignment),
            'request_transport':{'method':'POST','endpoint_template':'<configured GEMINI_BASE_URL>/chat/completions',
              'standard_adapter_endpoint':'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
              'actual_endpoint_captured':False,'content_type':'application/json','authorization':'REDACTED; not captured',
              'timeout_seconds':assignment['profile']['generate_timeout_seconds']},
            'limits':['Exact prompts and returned visible text are saved; original full request/response HTTP envelopes are not.',
              'Initial request JSON is reconstructed from the frozen assignment and client adapter, not a captured wire request.',
              'The client could raise max_tokens on truncation; exact per-retry request bodies were not captured.',
              'Transport events contain saved HTTP statuses, permitted usage counters and visible fragments, not full provider JSON or headers.',
              'No API keys, authentication headers, private model reasoning or raw source exam files are included.'],
            'run_status':read(root/'run-status.json'),'records':records}
    data=(json.dumps(export,ensure_ascii=False,indent=2)+'\n').encode()
    # Fail closed: never silently export a credential-like value embedded in data.
    for pattern in [rb'gsk_[A-Za-z0-9]{20,}',rb'AQ\.[A-Za-z0-9_-]{35,}',rb'AIza[0-9A-Za-z_-]{30,}',rb'-----BEGIN .*PRIVATE KEY']:
        if re.search(pattern,data):raise ValueError('Credential-pattern check failed; export withheld')
    digest=hashlib.sha256(data).hexdigest();target=root/('api-export-'+digest);target.mkdir(exist_ok=True)
    files['all-api-records.json']=data
    explanation='# Saved Gemini API data\n\n'+'\n'.join('- '+x for x in export['limits'])+'\n\n40 attempts; 24 drafts; 2 protocol holds; 14 provider errors/refusals.\n'
    files['README.md']=explanation.encode()
    cards=[]
    for r in records:
        title=(f"Question {r['display_number']} / {r['alias']}" if r['alias'] else 'No reviewable question')+' — '+r['item_id']
        blocks=[('Initial request JSON — reconstructed',r['initial_request_body_reconstructed_not_wire_capture']),
                ('Exact visible returned content',r['returned_content_exact']),('Parsed candidate',r['parsed_candidate']),
                ('Saved state and captured HTTP events',{'state':r['state'],'events':r['captured_transport_events']}),
                ('All captured visible fragments',r['captured_visible_fragments'])]
        cards.append('<article><h2>'+html.escape(title)+'</h2>'+''.join('<details open><summary>'+html.escape(label)+'</summary><pre>'+html.escape(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2))+'</pre></details>' for label,value in blocks)+'</article>')
    document='<!doctype html><meta charset="utf-8"><title>Gemini saved API records</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem;background:#181818;color:#eee}article{border-top:1px solid #555;padding:2rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#252525;padding:1rem;unicode-bidi:plaintext}summary{cursor:pointer;font-weight:bold;margin-top:1rem}</style><h1>Saved Gemini API records: 40 attempts / 24 drafts</h1><pre>'+html.escape(explanation)+'</pre>'+''.join(cards)
    files['api-records.html']=document.encode()
    for name in ['all-api-records.json','README.md','api-records.html']:
        output=target/name
        if output.exists() and output.read_bytes()!=files[name]:raise ValueError('Existing export changed')
        output.write_bytes(files[name])
    with zipfile.ZipFile(target/'gemini-api-records.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in files.items():archive.writestr(name,raw)
    print(json.dumps({'folder':str(target),'attempts':len(records),'transport_events':sum(len(r['captured_transport_events']) for r in records),'parsed_candidates':sum(r['parsed_candidate'] is not None for r in records),'credential_pattern_scan':'passed'}))


if __name__=='__main__':main()
