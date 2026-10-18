"""Local OCR experiments must stay local and retain incomplete evidence."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location("benchmark_local_ocr", Path(__file__).resolve().parents[1] / "backend/scripts/benchmark_local_ocr.py")
ocr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ocr)


@pytest.mark.parametrize("name", ["deepseek-ocr:cloud", "deepseek-ocr:3b\n", "https://x", "deepseek-ocr:", "other:latest"])
def test_rejects_remote_or_malformed_models(name):
    with pytest.raises(ValueError):
        ocr.local_model(name)


@pytest.mark.parametrize("box", ["nan,0,1,1", "0,0,2,1", "0.5,0,0.4,1", "0,1,2"])
def test_crop_rejects_invalid_coordinates(box):
    with pytest.raises(ocr.argparse.ArgumentTypeError):
        ocr.crop_box(box)


def fake_client(monkeypatch, chunks, *, remote=False):
    real_client = httpx.Client
    seen = []
    def handle(request):
        assert str(request.url).startswith("http://127.0.0.1:11434/")
        seen.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name":ocr.MODEL,"digest":"sha256:pilot"}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"remote_host":"https://cloud.example"} if remote else {"capabilities":["vision"]})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version":"test"})
        if request.url.path == "/api/generate":
            body=json.loads(request.content)
            assert body["keep_alive"] == 0
            assert body["options"]["num_predict"] == 128
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in chunks))
        raise AssertionError(request.url)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs:real_client(**kwargs, transport=httpx.MockTransport(handle)))
    return seen


def run_pilot(tmp_path, report):
    image=tmp_path/"input.png"
    image.write_bytes(b"image")
    ocr.ollama_ocr(image, model=ocr.MODEL, prompt="free", max_tokens=128, deadline=30,
                   report=report, checkpoint=tmp_path/"result.json")


def test_unfinished_stream_keeps_text_and_raises(tmp_path, monkeypatch):
    fake_client(monkeypatch,[{"response":"partial Persian transcription", "done":False}])
    report={"state":"running", "source_faithfulness_approved":False}
    with pytest.raises(RuntimeError, match="without a final"):
        run_pilot(tmp_path,report)
    assert report["text"] == "partial Persian transcription"
    assert report["source_faithfulness_approved"] is False


def test_output_limit_is_not_success(tmp_path, monkeypatch):
    fake_client(monkeypatch,[{"response":"truncated", "done":True, "done_reason":"length"}])
    report={"state":"running"}
    run_pilot(tmp_path,report)
    assert report["state"] == "output_limit"


def test_remote_alias_rejected_before_image_is_sent(tmp_path, monkeypatch):
    seen=fake_client(monkeypatch,[],remote=True)
    with pytest.raises(ValueError, match="Remote model aliases"):
        run_pilot(tmp_path,{"state":"running"})
    assert "/api/generate" not in seen


def test_deadline_preserves_partial_response(tmp_path,monkeypatch):
    fake_client(monkeypatch,[{"response":"partial", "done":False}])
    ticks=iter([0,31,31])
    monkeypatch.setattr(ocr,"time",SimpleNamespace(monotonic=lambda:next(ticks,31)))
    report={"state":"running"}
    with pytest.raises(TimeoutError):
        run_pilot(tmp_path,report)
    assert report["text"] == "partial"


def test_html_never_executes_model_output(tmp_path):
    image=tmp_path/"input.png"
    image.write_bytes(b"image")
    ocr.write_view(tmp_path/"review.html",{
        "engine":"deepseek", "source_sha256":"x", "text":"<script>bad()</script>"},image)
    text=(tmp_path/"review.html").read_text(encoding="utf-8")
    assert "<script>bad()" not in text
    assert "&lt;script&gt;" in text
    assert "default-src 'none'" in text


def test_monitor_binds_candidate_to_checked_source_and_escapes(tmp_path,monkeypatch):
    from app.rag import exam_review
    image=tmp_path/'source.png';image.write_bytes(b'source')
    monkeypatch.setattr(exam_review,'reviewed_page',lambda root:{'image':image})
    for name,sha,content in [('matches',ocr.digest(image),'<script>unsafe</script>'),('different','wrong','WRONG_SOURCE')]:
        path=tmp_path/'model-probe/local-ocr'/name/'result.json'
        ocr.atomic_json(path,{'source_sha256':sha,'text':content,'engine':'pilot','state':'finished'})
    page=exam_review.local_ocr_html(tmp_path)
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in page
    assert '<script>unsafe' not in page
    assert 'WRONG_SOURCE' not in page
    assert 'not approved scans' in page


def test_download_checkpoint_is_numeric_and_error_omits_signed_url(tmp_path,monkeypatch):
    real_client=httpx.Client
    def handle(request):
        assert str(request.url)==ocr.OLLAMA+'/api/pull'
        return httpx.Response(200,content='\n'.join(json.dumps(row) for row in [
            {'status':'pulling','completed':40,'total':100},
            {'error':'Get https://download.example/file?signed=private: no such host'}]))
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:real_client(**kwargs,transport=httpx.MockTransport(handle)))
    report={}
    with pytest.raises(RuntimeError,match='DNS failure') as caught:
        ocr.pull_model(ocr.MODEL,report,tmp_path/'result.json')
    assert 'signed=private' not in str(caught.value)
    assert report['download_bytes']==40 and report['download_total_bytes']==100
    assert 'download.example' not in (tmp_path/'result.json').read_text()


def test_download_checkpoint_or_integrity_failure_is_not_mislabelled_network():
    assert 'checkpoints' in ocr.download_error_reason('remove C:/cache/model-partial-0: The system cannot find the file specified')
    assert 'checksum verification failed' in ocr.download_error_reason('sha256 digest mismatch')
