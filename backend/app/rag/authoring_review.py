"""Private append-only authoring review store. No automatic eligibility promotion."""
import hashlib,json,secrets
from datetime import datetime,timezone
from pathlib import Path
from app.rag.exam_corpus import atomic_json,job_lock,payload_digest

DIMENSIONS={"extraction","answer_association","curriculum","science","editorial","figure_fidelity","intended_difficulty"}
class ReviewError(Exception):
    def __init__(self,status,message):self.status=status;self.message=message

class ReviewStore:
    def __init__(self,root,packet_root,catalogue):
        self.root=Path(root);self.packet_root=Path(packet_root);self.catalogue=Path(catalogue)
        self.candidate_root=self.packet_root.parent/"review-candidates-v1"

    def presentation(self,q):
        """Optional versioned visual transcription, never an approval or raw overwrite."""
        pointer=self.candidate_root/(hashlib.sha256(q["id"].encode()).hexdigest()+".json")
        if not pointer.exists():return None,None
        ref=json.loads(pointer.read_text(encoding="utf-8"))
        if not isinstance(ref,dict):raise ReviewError(409,"Invalid candidate pointer")
        name=ref.get("candidate","")
        if not isinstance(name,str) or Path(name).name!=name or not name.startswith("candidate-"):raise ReviewError(409,"Invalid candidate reference")
        path=(self.candidate_root/name).resolve()
        if not path.is_relative_to(self.candidate_root.resolve()):raise ReviewError(409,"Unsafe candidate reference")
        candidate=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(candidate,dict) or type(candidate.get("candidate_revision")) is not int or candidate["candidate_revision"]<1:raise ReviewError(409,"Malformed candidate")
        if payload_digest({k:v for k,v in candidate.items() if k!="candidate_sha256"})!=candidate.get("candidate_sha256"):raise ReviewError(409,"Candidate integrity failed")
        if candidate.get("question_id")!=q["id"] or candidate.get("parent_content_sha256")!=q["content_sha256"] or candidate.get("parent_image_sha256")!=q["source_image_sha256"] or candidate.get("source_document_sha256")!=q["document_id"]:raise ReviewError(409,"Stale candidate parent")
        if type(candidate.get("question_revision")) is not int or candidate["question_revision"]<=q["revision"]:raise ReviewError(409,"Invalid candidate revision")
        stem=candidate.get("stem");options=candidate.get("options")
        table=candidate.get("table")
        if table is not None:
            if not isinstance(table,dict) or set(table)!={"rows"} or not isinstance(table["rows"],list) or not 1<=len(table["rows"])<=20:raise ReviewError(409,"Invalid source table")
            width=None
            for row in table["rows"]:
                if not isinstance(row,dict) or set(row)!={"label","cells"} or not isinstance(row["label"],str) or not row["label"].strip() or not isinstance(row["cells"],list) or not 1<=len(row["cells"])<=20 or any(not isinstance(cell,str) or not cell.strip() for cell in row["cells"]):raise ReviewError(409,"Invalid table row")
                if width is not None and len(row["cells"])!=width:raise ReviewError(409,"Unequal table rows")
                width=len(row["cells"])
        if not isinstance(stem,list) or not stem or any(not isinstance(s,dict) or s.get("kind") not in ("text","math") or not isinstance(s.get("value"),str) for s in stem):raise ReviewError(409,"Invalid candidate stem")
        if not isinstance(options,list) or len(options)!=4 or any(not isinstance(o,dict) or type(o.get("index")) is not int or o["index"]!=i or not isinstance(o.get("text"),str) for i,o in enumerate(options)):raise ReviewError(409,"Invalid candidate options")
        image=candidate.get("source_image",{})
        if not isinstance(image,dict) or not isinstance(image.get("file"),str):raise ReviewError(409,"Malformed candidate image")
        image_path=(self.candidate_root/image["file"]).resolve()
        if image.get("pdf_page") not in [r["pdf_page"] for r in q["regions"]]:raise ReviewError(409,"Unbound candidate page")
        if not image_path.is_relative_to(self.candidate_root.resolve()) or image_path.suffix!=".png":raise ReviewError(409,"Unsafe candidate image")
        data=image_path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=image.get("sha256"):raise ReviewError(409,"Candidate image changed")
        return candidate,data

    def load(self):
        status=json.loads((self.packet_root/"status.json").read_text(encoding="utf-8"))
        if not isinstance(status,dict) or not isinstance(status.get("packet"),str):raise ReviewError(409,"Malformed packet status")
        name=status.get("packet","")
        if not name.startswith("packet-") or Path(name).name!=name:raise ReviewError(409,"Invalid packet reference")
        path=(self.packet_root/name).resolve()
        if not path.is_relative_to(self.packet_root.resolve()):raise ReviewError(409,"Unsafe packet reference")
        packet=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(packet,dict) or any(not isinstance(packet.get(k),list) for k in ("questions","answers","documents")):raise ReviewError(409,"Malformed packet")
        if payload_digest({k:v for k,v in packet.items() if k!="packet_sha256"})!=packet.get("packet_sha256"):raise ReviewError(409,"Packet integrity failed")
        for collection in ("questions","answers"):
            ids=[]
            for row in packet[collection]:
                if not isinstance(row,dict):raise ReviewError(409,"Malformed record")
                for key in ("id","document_id","exam_id","session","booklet_code","section","content_sha256"):
                    if not isinstance(row.get(key),str) or not row[key]:raise ReviewError(409,"Missing source identity")
                if any(type(row.get(k)) is not int or row[k]<1 for k in ("revision","printed_question_number")):raise ReviewError(409,"Malformed source revision")
                if not isinstance(row.get("literal_native"),str) or not isinstance(row.get("regions"),list):raise ReviewError(409,"Malformed transcription")
                if row.get("answer_index") is not None and (type(row["answer_index"]) is not int or not 0<=row["answer_index"]<=3):raise ReviewError(409,"Malformed answer index")
                if row.get("source_image_sha256")!=[r.get("image_sha256") for r in row["regions"] if isinstance(r,dict)]:raise ReviewError(409,"Unbound image hashes")
                ids.append(row["id"])
            if len(ids)!=len(set(ids)):raise ReviewError(409,"Duplicate record identity")
        return packet

    def image_parts(self,record):
        parts=[]
        if not (self.packet_root/"crops").resolve().is_relative_to(self.packet_root.resolve()):raise ReviewError(409,"Unsafe crop root")
        for region in record.get("regions",[]):
            if not isinstance(region,dict) or not isinstance(region.get("image"),str):raise ReviewError(409,"Malformed image reference")
            rel=region.get("image","");path=(self.packet_root/rel).resolve()
            if not path.is_relative_to((self.packet_root/"crops").resolve()) or path.suffix!=".png":raise ReviewError(409,"Unsafe source reference")
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=region.get("image_sha256"):raise ReviewError(409,"Source image changed")
            parts.append(data)
        if not parts:raise ReviewError(409,"Source image missing")
        return parts

    def current(self,qid):
        packet=self.load()
        q=next((q for q in packet["questions"] if q.get("id")==qid),None)
        if q is None:raise ReviewError(404,"Question not found")
        candidates=[a for a in packet["answers"] if all(a.get(k)==q.get(k) for k in ("exam_id","session","booklet_code","section","printed_question_number"))]
        a=candidates[0] if len(candidates)==1 else None
        if q.get("section")!="math":raise ReviewError(404,"Outside math pilot")
        qparts=self.image_parts(q);aparts=self.image_parts(a) if a else []
        for record in (q,a):
            if record is not None:
                calculated=payload_digest({"native_text":record["literal_native"],"regions":record["regions"]})
                if calculated!=record["content_sha256"]:raise ReviewError(409,"Content integrity failed")
        catalogue=hashlib.sha256(self.catalogue.read_bytes()).hexdigest()
        documents=[d for d in packet["documents"] if isinstance(d,dict) and d.get("document_id")==q["document_id"]]
        if len(documents)!=1 or type(documents[0].get("revision")) is not int:raise ReviewError(409,"Missing document revision")
        binding=dict(questionId=qid,questionRevision=q["revision"],contentHash=q["content_sha256"],documentId=q["document_id"],documentRevision=str(documents[0]["revision"]),pageImageHash=None,cropImageHash=payload_digest(q["source_image_sha256"]),figureImageHash=None,catalogueVersion=catalogue)
        presentation,data=self.presentation(q)
        if presentation:
            content={"stem":presentation["stem"],"options":presentation["options"]}
            if presentation.get("table") is not None:content["table"]=presentation["table"]
            binding.update(questionRevision=presentation["question_revision"],contentHash=payload_digest(content),cropImageHash=presentation["source_image"]["sha256"])
            q={**q,"presentation":presentation};qparts=[data]
        token=payload_digest({"binding":binding,"question":q,"answer":a,"packet":packet["packet_sha256"]})
        binding["evidenceToken"]=token
        return q,a,binding,token,qparts,aparts

    def events(self,qid):
        folder=self.root/hashlib.sha256(qid.encode()).hexdigest()
        events=[json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]
        for event in events:
            if not isinstance(event,dict) or event.get("kind") not in ("decision","blind_solve","answer_exposure") or not isinstance(event.get("reviewer"),str) or not isinstance(event.get("timestamp"),str):raise ReviewError(409,"Malformed review ledger")
            if event["kind"]=="decision":
                receipt=event.get("receipt")
                if not isinstance(receipt,dict) or receipt.get("reviewerKind")!="human" or receipt.get("reviewerIdentifier")!=event["reviewer"] or receipt.get("dimension") not in DIMENSIONS or receipt.get("outcome") not in ("passed","failed","unresolved") or not isinstance(receipt.get("binding"),dict):raise ReviewError(409,"Malformed decision receipt")
        return sorted(events,key=lambda e:e["timestamp"])

    def append(self,qid,event):
        now=datetime.now(timezone.utc).isoformat();id=secrets.token_hex(16)
        event={**event,"id":id,"timestamp":now}
        atomic_json(self.root/hashlib.sha256(qid.encode()).hexdigest()/(id+".json"),event)
        return event

    def packet(self,qid,mode,reviewer):
        if mode not in ("blind","source"):raise ReviewError(400,"Unknown packet mode")
        q,a,binding,token,_,_=self.current(qid)
        if mode=="source":
            with job_lock(self.root):self.append(qid,{"kind":"answer_exposure","reviewer":reviewer,"evidenceToken":token})
        events=self.events(qid)
        receipts=[e["receipt"] for e in events if e.get("kind")=="decision"] if mode=="source" else []
        def public(record):
            if record is None:return None
            pages=[record["presentation"]["source_image"]["pdf_page"]] if record.get("presentation") else [r["pdf_page"] for r in record["regions"]]
            return {k:record.get(k) for k in ("id","revision","document_id","session","booklet_code","section","printed_question_number","literal_native","continuation_state","answer_index") } | {"pages":pages}
        own=[e["solution"] for e in events if e.get("kind")=="blind_solve" and e.get("reviewer")==reviewer and e.get("evidenceToken")==token] if mode=="source" else []
        presentation=q.get("presentation")
        display={"stem":presentation["stem"],"options":presentation["options"],"state":"candidate","revision":presentation["candidate_revision"],"figureInSource":presentation.get("figure_in_source",False)} if presentation else None
        if display is not None and presentation.get("table") is not None:display["table"]=presentation["table"]
        checks=[{k:e["receipt"][k] for k in ("receiptId","outcome","note","evidenceToken","timestamp")} for e in events if e.get("kind")=="decision" and e["reviewer"]==reviewer and e["receipt"]["dimension"]=="extraction"]
        return {"question":public(q),"transcription":display,"sourceChecks":checks,"answer":public(a) if mode=="source" else None,"binding":binding,"evidenceToken":token,"receipts":receipts,"blindSolution":own[-1] if own else None,"mode":mode,"eligible":False}

    def decide(self,qid,body,reviewer):
        if not isinstance(body,dict) or not isinstance(body.get("dimension"),str) or body.get("dimension") not in DIMENSIONS or body.get("decision") not in ("pass","fail","unresolved","hold"):raise ReviewError(422,"Invalid decision")
        if body.get("synthetic") is not False:raise ReviewError(422,"Real record required")
        if body.get("reviewerKind")!="human" or not isinstance(body.get("note"),str) or not 10<=len(body["note"].strip())<=8000:raise ReviewError(422,"Reviewer note required")
        with job_lock(self.root):
            q,a,binding,token,_,_=self.current(qid)
            if payload_digest(body.get("binding"))!=payload_digest(binding) or body.get("evidenceToken")!=token or body.get("questionId")!=qid:raise ReviewError(409,"Evidence changed; reload before deciding")
            if body["dimension"]=="answer_association" and a is None and body["decision"]=="pass":raise ReviewError(409,"Ambiguous or missing answer mapping")
            if body["dimension"]=="extraction" and body["decision"]=="pass" and not q.get("presentation"):raise ReviewError(409,"A structured transcription is required before confirming extraction")
            if body["dimension"]=="science":
                events=self.events(qid)
                blind=[e for e in events if e.get("kind")=="blind_solve" and e.get("reviewer")==reviewer and e.get("evidenceToken")==token]
                if not blind:raise ReviewError(409,"Record a blind solution before scientific review")
            receipt=dict(schema_version="0.1",receiptId=secrets.token_hex(16),dimension=body["dimension"],outcome={"pass":"passed","fail":"failed","hold":"unresolved","unresolved":"unresolved"}[body["decision"]],reviewerKind="human",reviewerIdentifier=reviewer,model=None,promptVersion=None,timestamp=datetime.now(timezone.utc).isoformat(),binding=binding,supersedes=[],synthetic=False,evidenceToken=token,note=body["note"].strip(),scientific_qualification="not_certified_by_system")
            if self.current(qid)[3]!=token:raise ReviewError(409,"Evidence changed during review")
            self.append(qid,{"kind":"decision","reviewer":reviewer,"receipt":receipt,"evidenceToken":token})
            return receipt

    def blind_solve(self,qid,body,reviewer):
        with job_lock(self.root):
            _,_,binding,token,_,_=self.current(qid)
            if body.get("evidenceToken")!=token or payload_digest(body.get("binding"))!=payload_digest(binding):raise ReviewError(409,"Stale blind packet")
            if any(e.get("kind")=="answer_exposure" and e.get("reviewer")==reviewer for e in self.events(qid)):raise ReviewError(409,"Answer already exposed; use another independent reviewer")
            if not isinstance(body.get("solution"),str) or not 10<=len(body["solution"].strip())<=8000:raise ReviewError(422,"Checkable solution required")
            return self.append(qid,{"kind":"blind_solve","reviewer":reviewer,"solution":body["solution"],"binding":binding,"evidenceToken":token})
