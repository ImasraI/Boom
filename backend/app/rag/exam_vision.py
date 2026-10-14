"""Private local OCR fleet with real image inputs and persistent refusal state."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import dotenv_values
from app.rag.exam_corpus import atomic_json, read_json


def quota_json(path,*,private=False):
    value=read_json(path)
    if value is None and not path.exists():return {}
    if (not isinstance(value,dict) or (private and any(not isinstance(v,dict) for v in value.values()))
        or (not private and not isinstance(value.get('__access',{}),dict))):
        raise RuntimeError('Invalid saved quota state; preserve and repair it before provider calls')
    return value


@dataclass(repr=False)
class Credential:
    provider: str
    key: str = field(repr=False)
    model: str
    base: str
    proxy: str = field(default="", repr=False)

    @property
    def identity(self):
        return hashlib.sha256(f"{self.base.rstrip('/')}\0{self.model}\0{self.key}".encode()).hexdigest()

    @property
    def key_id(self):return hashlib.sha256(self.key.encode()).hexdigest()


def credentials(project: Path) -> list[Credential]:
    backend = dotenv_values(project / "backend/.env")
    files = [(backend, "backend")]
    files.extend((dotenv_values(p), p.parent.name) for p in sorted((project / "ocr-workers").glob("worker*/worker.env")))
    result, seen = [], set()
    for values, _ in files:
        for name, value in values.items():
            if not name.endswith(("API_KEY", "API_KEYS")): continue
            for key in (value or "").split(","):
                key = key.strip()
                provider = "groq" if key.startswith("gsk_") else "gemini" if key.startswith(("AQ.", "AIza")) else None
                if not provider or (provider, key) in seen: continue
                seen.add((provider, key))
                model = ((os.getenv('EXAM_OCR_GEMINI_MODEL') or values.get("GEMINI_MODEL_NAME") or backend.get("GEMINI_MODEL_NAME") or "gemini-3.6-flash") if provider == "gemini"
                         else (backend.get("GROQ_VISION_MODEL") or "qwen/qwen3.8-27b"))
                # Removed Scout/legacy text models must not silently process images.
                if provider == "groq" and "qwen" not in model:
                    model = "qwen/qwen3.8-27b"
                base = ((backend.get("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai")
                        if provider == "gemini" else "https://api.groq.com/openai/v1")
                proxy = os.getenv('EXAM_OCR_PROXY') or backend.get('EXAM_OCR_PROXY') or values.get("GEMINI_PROXY" if provider == "gemini" else "GROQ_PROXY") or backend.get("GEMINI_PROXY" if provider == "gemini" else "LLM_PROXY") or ""
                result.append(Credential(provider, key, model, base, proxy))
    return result


def retry_seconds(response, daily=False, provider="groq"):
    values = []
    try:
        seconds = float(response.headers.get("retry-after", ""))
        if seconds > 0: values.append(seconds)
    except (ValueError, TypeError): pass
    try:
        body = response.json()
        text = json.dumps(body, ensure_ascii=False)
        match = re.search(r"try again in\s+([\d.dhms\s]+)", text, re.I)
        if match:
            values.append(sum(float(n)*{"d":86400,"h":3600,"m":60,"s":1}[u.lower()]
                              for n,u in re.findall(r"(\d+(?:\.\d+)?)\s*([dhms])", match[1], re.I)))
        for value in re.findall(r'"retryDelay"\s*:\s*"([\d.]+)s"', text): values.append(float(value))
    except (ValueError, TypeError): pass
    if daily and provider == "gemini":
        try: pacific = ZoneInfo("America/Los_Angeles")
        except Exception: pacific = timezone(timedelta(hours=-8))
        now = datetime.now(timezone.utc)
        midnight = datetime.combine(now.astimezone(pacific).date()+timedelta(days=1), datetime.min.time(),tzinfo=pacific)
        # A short minute retry hint never authorizes another daily-quota probe.
        return max((midnight-now).total_seconds(), *values)
    return max(60 if daily else 10, max(values, default=86400 if daily else 60))


class VisionFleet:
    def __init__(self, specs, root: Path, *, client_factory=None, minimum_interval=20, groq_output_tokens=None):
        self.specs = specs
        self.root = root
        self.state_path = root / "vision-quota.json"
        self.state = quota_json(self.state_path,private=True)
        self.lock = threading.RLock()
        self.busy = set(); self.next_call = {}; self.cursors = {}
        self.minimum_interval = minimum_interval
        self.groq_output_tokens = int(groq_output_tokens if groq_output_tokens is not None
                                      else os.getenv('EXAM_OCR_GROQ_OUTPUT_TOKENS', '16384'))
        if not 256 <= self.groq_output_tokens <= 32768:
            raise ValueError('Groq OCR output limit must be 256..32768')
        self.jobs = {}
        self.request_count = 0
        self.client_factory = client_factory or (lambda s: httpx.Client(timeout=300, trust_env=False, proxy=s.proxy or None))
        self.shared_path = root.parents[0] / "provider_quota.json"

    def worker_update(self, **values):
        """Visible task metadata only: never prompts, keys or response bodies."""
        allowed = {'document_name', 'document_id', 'pdf_page', 'phase', 'stage',
                   'started_at', 'request_started_at', 'provider', 'model',
                   'credential_label', 'http_status', 'error', 'finished_at'}
        with self.lock:
            name = threading.current_thread().name
            row = self.jobs.setdefault(name, {'worker': name})
            row.update({k: v for k, v in values.items() if k in allowed})
            row['updated_at'] = time.time()

    def worker_status(self):
        with self.lock:
            return [dict(row) for _, row in sorted(self.jobs.items())]

    def _capacity_blocked(self, spec, saved):
        if not saved.get('request_capacity_blocked'): return False
        # A changed, smaller request can fit an observed output ceiling. This
        # never clears a daily quota, access denial or the saved refusal record.
        limit = saved.get('output_token_limit')
        if limit is None:
            match = re.search(r'output tokens per minute.*?Limit\s+(\d+)', saved.get('detail', ''), re.I)
            if match: limit = int(match[1])
        return not (spec.provider == 'groq' and isinstance(limit, int)
                    and self.groq_output_tokens <= limit)

    def _blocked(self, spec, now):
        if any(v.get('http_status')==401 and v.get('key_id')==spec.key_id for v in self.state.values() if isinstance(v,dict)):return True
        saved = self.state.get(spec.identity, {})
        if saved.get("access_denied") or self._capacity_blocked(spec, saved) or saved.get("retry_at", 0) > now: return True
        shared = quota_json(self.shared_path)
        if isinstance(shared.get(spec.identity), (int,float)) and shared[spec.identity] > now: return True
        return bool(shared.get("__access", {}).get(spec.identity))

    def request(self, prompt: str, image: Path, provider="auto"):
        now = time.time()
        with self.lock:
            choices = [s for s in self.specs if provider in ("auto",s.provider)]
            selected = None
            cursor = self.cursors.get(provider, 0)
            for i in range(len(choices)):
                spec = choices[(cursor+i) % len(choices)]
                if spec.identity not in self.busy and self.next_call.get(spec.identity,0) <= now and not self._blocked(spec,now):
                    selected=spec; self.cursors[provider]=(cursor+i+1) % len(choices); self.busy.add(spec.identity); break
        if not selected:
            return {"ok":False,"error":"no_ready_credentials","retryable":True}
        spec = selected
        siblings = [s for s in self.specs if s.provider == spec.provider]
        self.worker_update(phase='requesting', provider=spec.provider, model=spec.model,
                           credential_label=f'{spec.provider} {siblings.index(spec)+1}',
                           request_started_at=time.time(), http_status=None, error=None)
        with self.lock:
            self.request_count += 1
        try:
            image_data = base64.b64encode(image.read_bytes()).decode("ascii")
            payload = {"model":spec.model,"temperature":0,"response_format":{"type":"json_object"},
                "messages":[{"role":"user","content":[{"type":"text","text":prompt},
                {"type":"image_url","image_url":{"url":"data:image/png;base64,"+image_data,"detail":"high"}}]}]}
            if spec.provider == "gemini":
                # Native image endpoint avoids compatibility-layer image failures.
                payload = {"contents":[{"role":"user","parts":[{"text":prompt},
                    {"inlineData":{"mimeType":"image/png","data":image_data}}]}],
                    "generationConfig":{"temperature":0,"maxOutputTokens":32768,
                    "responseMimeType":"application/json",
                    "mediaResolution":"MEDIA_RESOLUTION_HIGH",
                    "thinkingConfig":{"thinkingLevel":"HIGH","includeThoughts":False}}}
                url = spec.base.rstrip('/').removesuffix('/openai')+"/models/"+spec.model+":generateContent"
                headers = {"x-goog-api-key":spec.key}
            else:
                # High-reasoning vision JSON mode can reject otherwise useful
                # transcripts. Strict local parsing/schema checks still apply.
                payload.pop('response_format',None)
                payload.update(max_completion_tokens=self.groq_output_tokens, reasoning_effort="high", reasoning_format="hidden")
                url = spec.base.rstrip("/")+"/chat/completions"
                headers = {"Authorization":"Bearer "+spec.key}
            with self.client_factory(spec) as client:
                response = client.post(url,json=payload,headers=headers)
            self.worker_update(http_status=response.status_code, phase='reading_response')
            if response.status_code >= 400:
                try: body = json.dumps(response.json(),ensure_ascii=False)
                except ValueError: body = ""
                daily = bool(re.search(r"per.?day|daily",body,re.I))
                # Groq JSON mode can reject a complete transcript solely because
                # LaTeX backslashes were not JSON-escaped. Repair serialization
                # only; never infer omitted fields, numbers, keys or answers.
                try:
                    error=response.json().get("error",{})
                    if response.status_code == 400 and error.get("code") == "json_validate_failed":
                        data=parse_transcript(error.get("failed_generation",""))
                        if isinstance(data,dict):
                            return {"ok":True,"data":data,"provider":spec.provider,"model":spec.model,
                                    "serialization_recovered":True,"usage":{},"credential_id":spec.identity[:12]}
                        return {"ok":False,"error":"invalid_json","provider":spec.provider,"model":spec.model}
                except (ValueError,AttributeError): pass
                failure = {"http_status":response.status_code,"key_id":spec.key_id,"error":"provider_daily_quota" if daily else "provider_error"}
                try:
                    error=response.json().get("error",{})
                    message=str(error.get("message", ""))
                    for configured in self.specs: message=message.replace(configured.key,"[redacted]")
                    message=re.sub(r"https?://\S+|\borg_[A-Za-z0-9_-]+", "[redacted]", message)
                    failure.update(provider_code=str(error.get("code") or "")[:60],
                                   detail=" ".join(message.split())[:300])
                except (ValueError,AttributeError): pass
                if response.status_code in (401,403): failure.update(error="provider_access_denied",access_denied=True)
                if response.status_code == 429:
                    failure.update(retry_at=time.time()+retry_seconds(response,daily,spec.provider))
                    if re.search(r'request too large|expected output tokens exceed',body,re.I):
                        # Waiting or another identical request cannot make a
                        # high-reasoning output fit a hard per-request ceiling.
                        failure.update(error='provider_request_too_large',request_capacity_blocked=True)
                        limit = re.search(r'output tokens per minute.*?Limit\s+(\d+)', body, re.I)
                        if limit: failure['output_token_limit'] = int(limit[1])
                        failure.pop('retry_at',None)
                elif response.status_code >= 500 or response.status_code in (400,404):
                    failure.update(retry_at=time.time()+900)
                with self.lock:
                    self.state[spec.identity]=failure; atomic_json(self.state_path,self.state)
                return {"ok":False, **{k:v for k,v in failure.items() if k!="access_denied"},"provider":spec.provider,"model":spec.model}
            result = response.json()
            choice = result["candidates"][0] if spec.provider == "gemini" else result["choices"][0]
            finished = choice.get("finishReason") == "STOP" if spec.provider == "gemini" else choice.get("finish_reason") == "stop"
            if not finished:
                return {"ok":False,"error":"incomplete_transcription","provider":spec.provider,"model":spec.model}
            raw = ("".join(p.get("text","") for p in choice.get("content",{}).get("parts",[]) if not p.get("thought"))
                   if spec.provider == "gemini" else choice["message"].get("content") or "")
            try:
                data = parse_transcript(raw)
            except (ValueError,TypeError):
                return {"ok":False,"error":"invalid_json","provider":spec.provider,"model":spec.model}
            if not isinstance(data,dict):
                return {"ok":False,"error":"invalid_json","provider":spec.provider,"model":spec.model}
            return {"ok":True,"data":data,"provider":spec.provider,"model":spec.model,
                    "usage":result.get("usageMetadata",result.get("usage",{})),"credential_id":spec.identity[:12]}
        except (httpx.HTTPError,OSError,ValueError,KeyError,IndexError,TypeError) as error:
            # Do not log response text, base64, credential-bearing URLs or proxy details.
            with self.lock:
                self.state[spec.identity]={"error":"provider_or_transport_error","retry_at":time.time()+300}
                atomic_json(self.state_path,self.state)
            return {"ok":False,"error":"provider_or_transport_error","error_type":type(error).__name__,"provider":spec.provider,"model":spec.model}
        finally:
            with self.lock:
                self.busy.discard(spec.identity); self.next_call[spec.identity]=time.time()+self.minimum_interval

    def health(self):
        now=time.time()
        with self.lock:
            return [{"provider":s.provider,"model":s.model,"credential_id":s.identity[:12],
                     "blocked":self._blocked(s,now),"busy":s.identity in self.busy,
                     "retry_at":self.state.get(s.identity,{}).get("retry_at"),
                     'request_capacity_blocked':self._capacity_blocked(s, self.state.get(s.identity,{})),
                     "access_denied":bool(self.state.get(s.identity,{}).get("access_denied"))} for s in self.specs]

    def ready_count(self,provider):
        with self.lock:
            now=time.time()
            return sum(s.provider==provider and not self._blocked(s,now) and s.identity not in self.busy
                       and self.next_call.get(s.identity,0)<=now for s in self.specs)

    def next_ready(self,provider):
        now=time.time();values=[]
        shared=quota_json(self.shared_path)
        with self.lock:
            for s in self.specs:
                if s.provider!=provider:continue
                saved=self.state.get(s.identity,{})
                if saved.get('access_denied') or self._capacity_blocked(s, saved) or shared.get('__access',{}).get(s.identity):continue
                if any(v.get('http_status')==401 and v.get('key_id')==s.key_id for v in self.state.values() if isinstance(v,dict)):continue
                values.append(max(now,self.next_call.get(s.identity,0),saved.get('retry_at',0),
                                  shared.get(s.identity,0) if isinstance(shared.get(s.identity),(float,int)) else 0))
        return min(values) if values else None


def parse_transcript(raw):
    if not isinstance(raw,str):return None
    raw=re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    # Valid JSON escapes such as \f, \t and \n can silently corrupt LaTeX.
    # Reject that ambiguous serialization rather than accepting altered math.
    if re.search(r'(?<!\\)\\(?:frac|theta|tan|right|beta|bar|begin|nu|nabla|text|times|neq|not)\b',raw):return None
    try:return json.loads(raw)
    except ValueError:
        escaped=re.sub(r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})|\\',
                       lambda m:'\\\\' if m[0]=='\\' else m[0],raw)
        try:return json.loads(escaped)
        except ValueError:return None
