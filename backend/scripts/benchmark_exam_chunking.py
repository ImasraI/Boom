"""Fixed-input character-boundary regression benchmark, not OCR accuracy."""
import sys,json,re,time
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND))
from app.rag.chunking import chunk_text,_split_into_sentences,VERSION
from app.rag.exam_corpus import read_json,atomic_json

def legacy(text,size=800,overlap=150):
    chunks=[];current=''
    for sentence in re.split(r'(?<=[.!?؟۔])\s+',text.strip()):
        candidate=(current+' '+sentence).strip()
        if len(candidate)<=size:current=candidate;continue
        if current:chunks.append(current);current=current[-overlap:]+' '+sentence
        else:
            chunks.extend(sentence[i:i+size] for i in range(0,len(sentence),size));current=''
    if current:chunks.append(current)
    return chunks

def main():
    root=BACKEND/'data/exam_staging/batch-5000-v1'
    rows=read_json(root/'chunks.json')
    metrics={name:{'texts':0,'oversized_chunks':0,'chunks':0} for name in ['legacy','v2']}
    for r in rows:
        for name,fn in [('legacy',legacy),('v2',chunk_text)]:
            chunks=fn(r['text']);metrics[name]['texts']+=1;metrics[name]['chunks']+=len(chunks)
            metrics[name]['oversized_chunks']+=sum(len(c)>800 for c in chunks)
    cases=[('Dr. Smith is here. Next.',2),('1. Solve this. 2. Continue.',2),('اول؟ دوم۔ سوم!',3)]
    boundaries={'legacy':0,'v2':0}
    for text,expected in cases:
        boundaries['legacy']+=len(re.split(r'(?<=[.!?؟۔])\s+',text))==expected
        boundaries['v2']+=len(_split_into_sentences(text))==expected
    report={'created_at':time.time(),'chunker_version':VERSION,'metrics':metrics,
        'synthetic_sentence_cases':len(cases),'synthetic_correct_boundaries':boundaries,
        'notes':['Not a measure of OCR or scientific accuracy.',
        'Question embedding parents stay whole; this benchmarks ordinary text splitting.']}
    atomic_json(root/'chunking-comparison.json',report)
    print(json.dumps(report))

if __name__=='__main__':main()
