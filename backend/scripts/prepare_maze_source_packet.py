"""Explicit H0 Maze profile. Local native extraction, review crops; no OCR/API/approval."""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import digest, payload_digest, atomic_json
from app.rag.exam_source_packets import packet_revision

EXPECTED_SHA="eabcf50af60e8a6f9db8e641525f3541a2410109fbb19888c5633ceecd6671fb"
TRANSLATE=str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩","01234567890123456789")
MARKER=re.compile(r"(?m)^\s*(\d{1,3})\s*[-ـ]\s*")

def normalize(text):
    return re.sub(r"[^\w]","",unicodedata.normalize("NFKC",text).translate(TRANSLATE)).lower()

def page_lines(page):
    text=""; lines=[]
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines",[]):
            value="".join(s["text"] for s in line["spans"])+"\n"
            lines.append((len(text),len(text)+len(value),line["bbox"]))
            text+=value
    return text.translate(TRANSLATE),lines

def find_headers(pages,start,end):
    headers=[];expected=1
    for page in range(start,end+1):
        text,lines=pages[page]
        for m in MARKER.finditer(text):
            number=int(m.group(1))
            if number!=expected:continue
            offset=m.start(1)
            bbox=next(b for a,z,b in lines if a<=offset<z)
            headers.append((number,page,m.start(),bbox[1]));expected+=1
    if expected!=106:raise ValueError(f"Incomplete sequential profile: found {expected-1}/105 headers")
    return headers

def prepare(source,destination):
    import fitz
    if digest(source)!=EXPECTED_SHA:raise ValueError("This profile only supports the exact H0 PDF; use a separately reviewed profile for other sources")
    destination=Path(destination)
    private=Path(__file__).resolve().parents[1]/"data"/"authoring_work"
    if not destination.resolve().is_relative_to(private.resolve()):raise ValueError("Output must stay under local private authoring_work")
    with fitz.open(source) as pdf:
        pages={i+1:page_lines(p) for i,p in enumerate(pdf)}
        qheads=find_headers(pages,2,21);aheads=find_headers(pages,26,88)
        def records(heads,end,role):
            result=[]
            for index,(number,start,offset,y) in enumerate(heads):
                nxt=heads[index+1] if index+1<len(heads) else None
                last=nxt[1] if nxt else end
                regions=[];texts=[];hashes=[]
                for pn in range(start,last+1):
                    if nxt and pn==last and nxt[3]<y and pn==start:raise ValueError("Nonmonotonic page layout")
                    top=max(0,y-2) if pn==start else 18
                    bottom=max(0,nxt[3]-2) if nxt and pn==last else pdf[pn-1].rect.height-22
                    if bottom<=top:continue
                    page=pdf[pn-1];rect=fitz.Rect(0,top,page.rect.width,bottom)
                    content=page.get_text("text",clip=rect)
                    # Association excerpt bounded by explicit sequential printed headers.
                    t=pages[pn][0];lo=offset if pn==start else 0
                    hi=nxt[2] if nxt and pn==last else len(t)
                    texts.append(t[lo:hi])
                    pix=page.get_pixmap(matrix=fitz.Matrix(1.3,1.3),clip=rect)
                    image=pix.tobytes("png");sha=hashlib.sha256(image).hexdigest()
                    rel=Path("crops")/(sha+".png");path=destination/rel
                    if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(image)
                    hashes.append(sha)
                    regions.append({"pdf_page":pn,"printed_page":None,"bbox":[0,top/page.rect.height,1,bottom/page.rect.height],"image":rel.as_posix(),"image_sha256":sha,"render":{"engine":"PyMuPDF","scale":1.3},"region_state":"native_boundary_candidate"})
                literal="\n".join(texts)
                matches=list(re.finditer(r"[:：]?\s*پاسخ\s*[:：]?\s*گزینه\s*([1-4])",literal)) if role=="answers" else []
                key=int(matches[0].group(1))-1 if len(matches)==1 else None
                label=None
                if len(matches)==1:
                    label=re.search(r"\((.{0,180}?)\)",literal[matches[0].end():],re.S)
                row={"id":f"{EXPECTED_SHA}:{start}:{number}"+(":answer" if role=="answers" else ""),"revision":1,"document_id":EXPECTED_SHA,"exam_id":"maze:1403-04-07:20:math_physics","session":"1403/04/07:stage20","booklet_code":"A","section":"math" if number<=40 else "physics" if number<=75 else "chemistry","printed_question_number":number,"identity_state":"confirmed","identity_basis":"H0 matching cover identity plus sequential printed numbering; per-item source review pending","content_sha256":payload_digest({"native_text":literal,"regions":regions}),"source_image_sha256":hashes,"regions":regions,"literal_native":literal,"continuation_state":"proposed" if len(regions)>1 else "not_needed","scientific_state":"not_checked","human_reviewed":False}
                if role=="answers":row.update(answer_index=key,author_key_match_count=len(matches),publisher_labels_raw=label.group(1).strip() if label else None,publisher_labels_state="native_candidate")
                result.append(row)
            return result
        questions=records(qheads,21,"questions");answers=records(aheads,88,"answers")
        packet=packet_revision([{"document_id":EXPECTED_SHA,"role":"combined","classification":"mock_exam","pages":len(pdf),"source_sha256":EXPECTED_SHA,"schema_version":"0.1","classification_state":"confirmed","publisher":"Maze","year":1403,"session":"1403/04/07:stage20","major":"math_physics","exam_id":"maze:1403-04-07:20:math_physics","booklet_code":"A","revision":1,"aliases":[],"classification_evidence":["H0 source identity","PDF covers 1,8,23"],"question_covers":[1,8],"answer_cover":23,"grade":None}],questions,answers)
        checks=[]
        answer_by_number={a["printed_question_number"]:a for a in answers}
        for q in questions:
            a=answer_by_number[q["printed_question_number"]]
            # Both lists independently resolve the complete printed-number sequence.
            stem=a["literal_native"].split("پاسخ")[0]
            common=len(set(re.findall(r"[\u0600-\u06ff]{3,}",q["literal_native"])) & set(re.findall(r"[\u0600-\u06ff]{3,}",stem)))
            checks.append({"printed_number":q["printed_question_number"],"shared_persian_stem_tokens":common,"key_match_count":a["author_key_match_count"]})
        packet["association_checks"]=checks
        packet["split"].update(development_candidate_document_ids=[EXPECTED_SHA],final_evaluation_candidate_document_ids=[],reason="Already exposed development source; duplicate/compilation/family review pending")
        packet["coverage"]={"questions":len(questions),"answers":len(answers),"unique_author_keys":sum(a["answer_index"] is not None for a in answers),"publisher_label_candidates":sum(bool(a["publisher_labels_raw"]) for a in answers),"source_reviewed_mappings":0,"scientific_reviews":0}
        packet["packet_sha256"]=payload_digest({k:v for k,v in packet.items() if k!="packet_sha256"})
        path=destination/("packet-"+packet["packet_sha256"]+".json")
        if not path.exists():atomic_json(path,packet)
        atomic_json(destination/"status.json",{"packet":path.name,"state":"prepared_for_review","coverage":packet["coverage"],"held_mappings":sum(m["state"]=="held" for m in packet["pairing"]["mappings"]),"eligible":False})
        print(json.dumps(json.loads((destination/"status.json").read_text()),indent=2))

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path);parser.add_argument("destination",type=Path)
    args=parser.parse_args();prepare(args.source,args.destination)
