"""Bounded, local-only OCR pilot. Never promotes output into the exam corpus.

Run from the repository root with backend/.venv/Scripts/python.exe.
Ollama is optional; Tesseract uses an already installed local executable.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.rag.exam_corpus import atomic_json, digest

OLLAMA = "http://127.0.0.1:11434"
MODEL = "deepseek-ocr:3b-bf16"
PROMPTS = {
    "free": "Free OCR.",
    "markdown": "<|grounding|>Convert the document to markdown.",
    "extract": "Extract the text in the image.",
    "figure": "Parse the figure.",
}


def local_model(name):
    # No remote/cloud models, custom hosts, URLs, or API credentials.
    if not re.fullmatch(r"deepseek-ocr:[A-Za-z0-9_.-]+", name) or "cloud" in name.lower():
        raise ValueError("Use a locally installed deepseek-ocr:<tag> model")
    return name


def crop_box(value):
    try:
        box = tuple(float(x) for x in value.split(","))
        if len(box) != 4 or not all(0 <= x <= 1 for x in box) or box[0] >= box[2] or box[1] >= box[3]:
            raise ValueError
        return box
    except ValueError as error:
        raise argparse.ArgumentTypeError("Crop must be normalized x0,y0,x1,y1 inside 0..1") from error


def installed_model(client, name):
    response = client.get(OLLAMA + "/api/tags")
    response.raise_for_status()
    for row in response.json().get("models", []):
        if row.get("name") == name or row.get("model") == name:
            return row
    raise RuntimeError(f"Model is not installed. Run ollama pull {name} first.")


def download_error_reason(message):
    """Keep useful failure categories without signed URLs or machine paths."""
    message=str(message).lower()
    if 'no such host' in message:return 'DNS failure'
    if '-partial-' in message and ('cannot find' in message or 'no such file' in message):
        return 'inconsistent local download checkpoints; repair the cache before retrying'
    if 'digest' in message or 'sha256' in message:
        return 'model checksum verification failed; do not use this download'
    if 'permission' in message or 'access is denied' in message:
        return 'local download cache file is locked or inaccessible'
    if 'no space' in message or 'disk full' in message:return 'insufficient disk space'
    return 'network/download failure'


def pull_model(model, report, checkpoint):
    """Ollama resumes its own partial download; save only numeric/status metadata."""
    import httpx
    local_model(model)
    started=time.monotonic();saved=-20
    report['state']='downloading'
    with httpx.Client(trust_env=False,timeout=httpx.Timeout(10,read=120)) as client:
        with client.stream('POST',OLLAMA+'/api/pull',json={'model':model,'stream':True}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:continue
                item=json.loads(line)
                if item.get('error'):
                    # Signed download URLs sometimes appear in server errors.
                    # Do not copy them into public-facing logs or reports.
                    reason=download_error_reason(item['error'])
                    raise RuntimeError(f'Ollama model download stopped: {reason}. Rerun --pull to resume.')
                elapsed=time.monotonic()-started
                if item.get('total'):
                    report.update(download_bytes=item.get('completed',0),download_total_bytes=item['total'])
                report['download_elapsed_seconds']=round(elapsed,1)
                if elapsed-saved>=10 or item.get('status')=='success':
                    atomic_json(checkpoint,report)
                    print(f"Model download: {report.get('download_bytes',0)/1e9:.2f} / {report.get('download_total_bytes',0)/1e9:.2f} GB",flush=True)
                    saved=elapsed
                if item.get('status')=='success':
                    report['state']='running'
                    atomic_json(checkpoint,report)
                    return
    raise RuntimeError('Model download stream ended without success; rerun --pull to resume')


def ollama_ocr(image, *, model, prompt, max_tokens, deadline, report, checkpoint):
    import httpx
    local_model(model)
    # This client deliberately ignores HTTP_PROXY, .env keys and cloud settings.
    with httpx.Client(trust_env=False, timeout=httpx.Timeout(10, read=60)) as client:
        report["model_installation"] = installed_model(client, model)
        details = client.post(OLLAMA + "/api/show", json={"model": model})
        details.raise_for_status()
        details = details.json()
        if details.get("remote_host") or details.get("remote_model"):
            raise ValueError("Remote model aliases cannot be used for this local-only test")
        report["model_details"] = {k:details[k] for k in ("details", "model_info", "capabilities", "parameters") if k in details}
        version = client.get(OLLAMA + "/api/version")
        version.raise_for_status()
        report["ollama_version"] = version.json().get("version")
        body = {
            "model": model, "prompt": PROMPTS[prompt],
            "images": [base64.b64encode(image.read_bytes()).decode("ascii")],
            "stream": True, "keep_alive": 0,
            "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": max_tokens},
        }
        report["prompt"] = body["prompt"]
        report["options"] = body["options"]
        chunks = []
        started = time.monotonic()
        saved = started
        try:
            with client.stream("POST", OLLAMA + "/api/generate", json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get("error"):
                        raise RuntimeError(str(item["error"]))
                    chunks.append(item.get("response", ""))
                    now = time.monotonic()
                    if now - saved > 10:
                        report.update(text="".join(chunks), elapsed_seconds=round(now-started, 3))
                        atomic_json(checkpoint, report)
                        print(f"OCR running: {now-started:.0f}s, {len(report['text'])} characters", flush=True)
                        saved = now
                    if item.get("done"):
                        report["metrics"] = {k: item[k] for k in (
                            "done", "done_reason", "total_duration", "load_duration", "prompt_eval_count",
                            "prompt_eval_duration", "eval_count", "eval_duration") if k in item}
                        report["state"] = "finished" if item.get("done_reason") != "length" else "output_limit"
                        break
                    if now - started > deadline:
                        raise TimeoutError("Local OCR pilot wall-clock deadline reached")
        finally:
            report.update(text="".join(chunks), elapsed_seconds=round(time.monotonic()-started, 3))
        if report.get("state") == "running":
            raise RuntimeError("Ollama stream ended without a final completion record")


def tesseract_ocr(image, *, psm, deadline, executable, report, tessdata=None, languages="fas+eng"):
    if not executable:
        executable = shutil.which("tesseract")
    if not executable and os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR/tesseract.exe"
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        raise RuntimeError("Tesseract is not installed or --tesseract-exe is missing")
    version = subprocess.run([executable, "--version"], capture_output=True, timeout=10, check=True)
    report.update(tesseract_version=version.stdout.decode(errors="replace").splitlines()[0], languages=languages, psm=psm)
    data_dir = Path(tessdata) if tessdata else Path(executable).parent / "tessdata"
    report["language_models"] = {lang:digest(data_dir / f"{lang}.traineddata") for lang in languages.split('+') if (data_dir / f"{lang}.traineddata").is_file()}
    command = [executable, str(image), "stdout", "-l", languages, "--psm", str(psm)]
    if tessdata:
        command.extend(["--tessdata-dir", str(Path(tessdata).resolve(strict=True))])
    started = time.monotonic()
    process = subprocess.run(command, capture_output=True, timeout=deadline, check=False)
    report.update(text=process.stdout.decode("utf-8", errors="replace"),
                  stderr=process.stderr.decode("utf-8", errors="replace"),
                  elapsed_seconds=round(time.monotonic()-started, 3), returncode=process.returncode,
                  state="finished" if process.returncode == 0 else "failed")


def write_view(path, report, image):
    # Model content is inert escaped text; never execute returned HTML/coordinates.
    esc = lambda text: html.escape(str(text), quote=True)
    data = base64.b64encode(image.read_bytes()).decode("ascii")
    suffix = image.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    path.write_text(f'''<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>Local OCR pilot</title><style>body{{background:#191513;color:#e8ded3;font:17px system-ui;margin:30px}}main{{display:grid;grid-template-columns:1fr 1fr;gap:25px}}img{{width:100%}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#241d19;padding:22px;line-height:1.8}}p{{color:#d0bca7}}@media(max-width:900px){{main{{display:block}}}}</style>
<h1>{esc(report['engine'])} OCR pilot</h1><p>{esc(report.get('state'))} · {esc(report.get('elapsed_seconds'))} seconds · source SHA256 {esc(report['source_sha256'])}</p>
<p>Unreviewed output. No scientific or human approval. This is a selected single-page/crop test, not corpus-wide accuracy. Figures remain in the original image.</p>
<main><pre dir="auto">{esc(report.get('text', report.get('error','')))}</pre><img src="data:{mime};base64,{data}" alt="Actual OCR input"></main>''', encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("deepseek", "tesseract"), default="deepseek")
    parser.add_argument("--image", type=Path, help="Default: the preserved source-checked physics pilot image")
    parser.add_argument("--output", type=Path, help="New result directory; refuses to overwrite an existing result")
    parser.add_argument("--crop", type=crop_box, help="Optional manually selected normalized bbox, disclosed in result")
    parser.add_argument("--model", type=local_model, default=MODEL)
    parser.add_argument("--pull", action="store_true", help="Resume/download the free local Ollama model before testing")
    parser.add_argument("--prompt", choices=tuple(PROMPTS), default="free")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--psm", type=int, choices=(3, 6, 11), default=3)
    parser.add_argument("--tesseract-exe")
    parser.add_argument("--tessdata", type=Path, help="Optional local language-model directory")
    parser.add_argument("--languages", choices=("fas+eng", "fas", "eng"), default="fas+eng")
    args = parser.parse_args()
    if not 128 <= args.max_tokens <= 8192 or not 30 <= args.timeout <= 1800:
        parser.error("Use 128..8192 tokens and a 30..1800 second deadline")
    if args.pull and args.engine!='deepseek':parser.error('--pull applies only to the local DeepSeek model')
    if args.image is None:
        from app.rag.exam_review import reviewed_page
        saved = reviewed_page(BACKEND / "data/exam_examples")
        if not saved:
            parser.error("The source-checked pilot is unavailable; pass --image")
        args.image = saved["image"]
    image = args.image.resolve(strict=True)
    output = args.output or BACKEND / "data/exam_examples/model-probe/local-ocr" / time.strftime("%Y%m%dT%H%M%S")
    output = output.resolve()
    # Private local source data must stay in ignored model-probe storage.
    allowed = (BACKEND / "data/exam_examples/model-probe").resolve()
    if not output.is_relative_to(allowed):
        parser.error("Results must stay under backend/data/exam_examples/model-probe")
    output.mkdir(parents=True, exist_ok=False)
    report = {"engine": args.engine, "model": args.model if args.engine == "deepseek" else None,
              "source": str(image), "source_sha256": digest(image), "crop": args.crop,
              "local_only": True, "human_reviewed": False, "scientific_state": "not_checked",
              "source_faithfulness_approved": False, "state": "running", "created_at": time.time()}
    if args.crop:
        from PIL import Image
        with Image.open(image) as original:
            w, h = original.size
            region = original.crop(tuple(round(v*(w if i%2 == 0 else h)) for i,v in enumerate(args.crop)))
            image = output / "input.png"
            region.save(image)
    report["input_sha256"] = digest(image)
    atomic_json(output / "result.json", report)
    try:
        if args.engine == "deepseek":
            if args.pull:pull_model(args.model,report,output / "result.json")
            ollama_ocr(image, model=args.model, prompt=args.prompt, max_tokens=args.max_tokens,
                       deadline=args.timeout, report=report, checkpoint=output / "result.json")
        else:
            tesseract_ocr(image, psm=args.psm, deadline=args.timeout, executable=args.tesseract_exe, report=report, tessdata=args.tessdata, languages=args.languages)
    except (Exception, KeyboardInterrupt) as error:
        report.update(state="failed", error=f"{type(error).__name__}: {error}")
    finally:
        report["finished_at"] = time.time()
        atomic_json(output / "result.json", report)
        (output / "transcript.txt").write_text(report.get("text", ""), encoding="utf-8")
        write_view(output / "review.html", report, image)
    print(json.dumps({k:report.get(k) for k in ("engine","state","elapsed_seconds","error")}), flush=True)
    print(f"Saved local evidence: {output}", flush=True)
    return 0 if report["state"] == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
