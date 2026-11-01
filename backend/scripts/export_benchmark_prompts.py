"""Export exact saved author prompts, never credentials or provider headers."""
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest


def main():
    root=Path(__file__).resolve().parents[1]/'data/authoring_work/development-benchmark-v1'
    read=lambda p: json.loads(p.read_text(encoding='utf8'))
    pointer=read(root/'review-pointer.json')
    if not re.fullmatch(r'review-[0-9a-f]{64}',pointer['folder']): raise ValueError('Invalid review path')
    binding=read(root/pointer['folder']/'binding.json')
    if payload_digest(binding)!=pointer['binding_sha256']: raise ValueError('Changed review binding')
    assignment=read(root/'assignment.json')
    records=[]
    for number,row in enumerate(binding['records'],1):
        item=row['item_id']
        if not re.fullmatch(r'pair-\d{2}-(baseline|design_conditioned)',item): raise ValueError('Invalid item path')
        raw=(root/'items'/item/'prompt.txt').read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        state=read(root/'items'/item/'state.json')
        if digest!=assignment['prompt_sha256'][item] or digest!=state['binding']['prompt_sha256']:
            raise ValueError('Saved prompt differs from executed assignment')
        if state['binding']['assignment_sha256']!=payload_digest(assignment): raise ValueError('Changed assignment')
        if payload_digest(row['candidate'])!=row['candidate_sha256']: raise ValueError('Changed candidate')
        records.append(dict(display_number=number,alias=row['alias'],item_id=item,arm=row['arm'],
                            prompt_sha256=digest,prompt=raw.decode('utf8')))
    export=dict(provider=assignment['provider'],model=assignment['model'],temperature=assignment['temperature'],
                profile=assignment['profile'],messages_role='user',review_binding_sha256=pointer['binding_sha256'],
                prompts=records,hidden_reasoning_exported=False,provider_headers_exported=False)
    target=root/('prompt-export-'+payload_digest(export));target.mkdir(exist_ok=True)
    text=['# Exact saved prompts for the 24 displayed drafts','',
          'The R identifiers match the complete 24-question sheet. This export reveals the prompting groups.',
          'These are the exact user-message bytes decoded as UTF-8; no model hidden reasoning, keys or request headers.',
          '',f"Provider/model: {export['provider']} / {export['model']}; temperature: {export['temperature']}",
          f"Profile: {json.dumps(export['profile'],sort_keys=True)}",'']
    for row in records:
        text.extend([f"## Question {row['display_number']} — {row['alias']} — {row['arm']}",
                     f"Item: `{row['item_id']}`; prompt SHA-256: `{row['prompt_sha256']}`",'',
                     '```text',row['prompt'],'```',''])
    for name,value in [('prompts.json',json.dumps(export,ensure_ascii=False,indent=2)+'\n'),('prompts.md','\n'.join(text))]:
        p=target/name
        if p.exists() and p.read_text(encoding='utf8')!=value: raise ValueError('Frozen export changed')
        p.write_text(value,encoding='utf8')
    print(json.dumps({'folder':str(target),'prompts':len(records),'hashes_verified':True}))


if __name__=='__main__':main()
