"""Admin-only local authoring review integration; never grants eligibility."""
from io import BytesIO
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from PIL import Image
from app.auth.deps import require_admin
from app.rag.authoring_review import ReviewStore, ReviewError

router = APIRouter(prefix="/api/authoring-review", tags=["authoring-review"])

def get_store():
    data = Path(__file__).resolve().parents[2] / "data"
    return ReviewStore(data/"authoring_work/review-ledger-v1", data/"authoring_work/s1a-mapped", data/"knowledge_graph/catalog.json")

def invoke(operation):
    try:
        return operation()
    except ReviewError as exc:
        raise HTTPException(exc.status, exc.message) from None
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        raise HTTPException(409, "Review evidence unavailable or malformed") from None

@router.get("/questions")
def questions(response: Response, user=Depends(require_admin), store=Depends(get_store)):
    response.headers["Cache-Control"]="private, no-store"
    return invoke(lambda: [{"id":q["id"], "number":q["printed_question_number"]} for q in store.load()["questions"] if q.get("section")=="math"])

@router.get("/questions/{qid}/packet")
def packet(qid: str, response: Response, mode: str="blind", user=Depends(require_admin), store=Depends(get_store)):
    response.headers["Cache-Control"]="private, no-store"
    return invoke(lambda: store.packet(qid, mode, f"user:{user.id}"))

@router.get("/questions/{qid}/images/{kind}")
def image(qid: str, kind: str, mode: str="blind", evidenceToken: str="", user=Depends(require_admin), store=Depends(get_store)):
    def render():
        if mode not in ("blind","source") or kind not in ("question","answer") or (mode=="blind" and kind=="answer"):
            raise ReviewError(404,"Image unavailable")
        # Logging exposure cannot be bypassed by loading the answer image directly.
        current=store.current(qid)
        if evidenceToken!=current[3]:raise ReviewError(409,"Image evidence changed; reload packet")
        store.packet(qid,mode,f"user:{user.id}")
        parts=current[4 if kind=="question" else 5]
        if not parts:raise ReviewError(404,"Image unavailable")
        if len(parts)==1:return parts[0]
        images=[Image.open(BytesIO(part)).convert("RGB") for part in parts]
        canvas=Image.new("RGB",(max(i.width for i in images),sum(i.height+12 for i in images)),"white")
        y=0
        for im in images:canvas.paste(im,(0,y));y+=im.height+12
        out=BytesIO();canvas.save(out,format="PNG");return out.getvalue()
    return Response(invoke(render),media_type="image/png",headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@router.post("/questions/{qid}/decisions")
def decision(qid: str, body: dict, user=Depends(require_admin), store=Depends(get_store)):
    receipt=invoke(lambda: store.decide(qid,body,f"user:{user.id}"))
    return {"ok":True,"receiptId":receipt["receiptId"],"recordedAt":receipt["timestamp"]}

@router.post("/questions/{qid}/blind-solve")
def blind(qid: str, body: dict, user=Depends(require_admin), store=Depends(get_store)):
    event=invoke(lambda: store.blind_solve(qid,body,f"user:{user.id}"))
    return {"ok":True,"recordedAt":event["timestamp"]}
