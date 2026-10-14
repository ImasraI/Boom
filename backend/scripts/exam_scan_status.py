"""Local live terminal/browser monitor. No provider calls or write endpoints."""
import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
from app.rag.exam_corpus import DEFAULT_ROOT
from app.rag.exam_progress import snapshot, stored_counts

PAGE='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Exam OCR · live workers</title><style>
*{box-sizing:border-box}body{margin:0;background:#191413;color:#f1e2da;font:14px system-ui,sans-serif}main{max-width:1240px;margin:auto;padding:32px}h1{font-size:30px;margin:10px 0}h2{font-size:18px;margin-top:32px}small,.muted{color:#b79c8b}header{border-bottom:1px solid #634638;padding-bottom:20px}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px;margin-top:24px}.stat{border:1px solid #432f26;padding:18px;background:#231917}.stat strong{display:block;font-size:26px;margin-top:9px}.status{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:16px}#phase{background:#42261f;color:#ffa594;padding:8px 12px;border:1px solid #804336}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #432f26;vertical-align:top}th{color:#b79c8b}td.doc{min-width:210px;max-width:340px;overflow-wrap:anywhere}progress{width:100%;height:7px;accent-color:#a6473e}.note{line-height:1.8;border-left:2px solid #a6473e;padding-left:14px;margin-top:24px}#error{color:#ffa594} .tag{font-size:11px;border:1px solid #634638;padding:3px 6px;white-space:nowrap}a{color:#ffa594}@media(max-width:600px){main{padding:18px}h1{font-size:24px}}
</style><main><header><small>LOCAL EXAM CORPUS · LIVE CHECKPOINTS</small><h1>Exam scanning workers</h1><div class="status"><span id="phase">Connecting…</span><span id="alive"></span><small id="updated"></small></div><p id="error" role="status"></p></header><section class="stats" id="stats"></section><div class="note" id="job"></div><h2>Worker activity</h2><div class="scroll"><table><thead><tr><th>Worker</th><th>State / stage</th><th>Page</th><th>Source</th><th>Credential / model</th><th>HTTP / age</th></tr></thead><tbody id="workers"></tbody></table></div><h2>Provider availability</h2><div class="scroll"><table><thead><tr><th>Credential label</th><th>Model</th><th>Availability</th><th>Last response</th><th>Retry after</th></tr></thead><tbody id="providers"></tbody></table></div><p class="note">Saved candidates are OCR output awaiting review. Qualified style references are separate; none of these counts certify scientific correctness. This monitor is read-only, uses local files, and sends no requests to AI providers.</p><p class="muted">To resume after closing the laptop, run START-EXAM-WORKERS.cmd again. Saved compatible page and question checkpoints are reused. A sleeping or powered-off laptop cannot scan.</p></main><script>
const $=id=>document.getElementById(id),cell=(row,text,cls)=>{const e=document.createElement('td');e.textContent=String(text??'—');if(cls)e.className=cls;row.append(e)},time=t=>t?new Date(t*1000).toLocaleString('en-GB',{timeZone:'Asia/Tehran'}):'—';
async function update(){try{const r=await fetch('/status',{cache:'no-store'});if(!r.ok)throw new Error('Monitor status unavailable');const s=await r.json();$('error').textContent='';$('phase').textContent=s.phase.replaceAll('_',' ');$('alive').textContent=s.worker_alive?'Coordinator is alive · PID '+s.pid:'No scanner is running';$('updated').textContent='Read at '+time(s.timestamp)+' Tehran';$('stats').replaceChildren();for(const [label,value,detail] of [['Text/layout pages',s.native_pages,s.total_pages+' total pages'],['Full-page OCR',s.full_ocr_pages,'Only complete compatible page candidates'],['Saved question candidates',s.saved_question_candidates,'Unique source/page/question identities'],['Qualified style references',s.qualified_references,s.human_reviewed_references+' human-reviewed'],['Provider requests this run',s.requests_this_run,s.failed_this_run+' failed page attempts']]){const div=document.createElement('div');div.className='stat';const l=document.createElement('small'),n=document.createElement('strong'),d=document.createElement('small');l.textContent=label;n.textContent=Number(value).toLocaleString();d.textContent=detail;div.append(l,n,d);$('stats').append(div)}$('job').textContent=s.selected_pages+' pages selected · '+s.worker_capacity+' parallel worker slots · '+s.active_candidates+' active · '+s.pending_candidates+' pending. '+(s.retry_not_before&&s.retry_not_before>s.timestamp?'Next allowed retry: '+time(s.retry_not_before)+' Tehran ('+Math.ceil((s.retry_not_before-s.timestamp)/60)+' min). Waiting sends no provider requests.':'');$('workers').replaceChildren();for(const w of s.workers){const row=document.createElement('tr');cell(row,w.worker);cell(row,w.phase+' / '+w.stage);cell(row,w.pdf_page);cell(row,w.document_name,'doc');cell(row,w.credential_label+' / '+w.model);cell(row,(w.http_status||'awaiting response')+' / '+(w.request_started_at?Math.max(0,Math.round(((w.finished_at||s.timestamp)-w.request_started_at)))+'s':'—'));$('workers').append(row)}if(!s.workers.length){const row=document.createElement('tr');cell(row,'Worker rows appear when the scanner starts.');$('workers').append(row)}$('providers').replaceChildren();for(const p of s.providers){const row=document.createElement('tr');cell(row,p.label);cell(row,p.model);cell(row,p.busy?'request in flight':p.access_denied?'access denied':p.capacity_blocked?'request too large · needs compatible capacity':p.blocked?'cooldown / saved quota':'ready to attempt');cell(row,(p.http_status||'—')+' '+p.error);cell(row,p.retry_at&&p.retry_at>s.timestamp?time(p.retry_at):'—');$('providers').append(row)}}catch(e){$('error').textContent='Cannot refresh status: '+e.message}finally{setTimeout(update,2000)}}update();
</script></html>'''


class Reader:
    def __init__(self, root): self.root,self.lock,self.cached,self.updated=root,threading.Lock(),None,0
    def get(self):
        with self.lock:
            if time.time()-self.updated>10 or self.cached is None:
                self.cached=stored_counts(self.root);self.updated=time.time()
            return snapshot(self.root,counts=self.cached)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--serve',action='store_true')
    parser.add_argument('--port',type=int,default=8770)
    parser.add_argument('--is-running',action='store_true',help='Exit zero only for a live scanner/coordinator')
    args=parser.parse_args();reader=Reader(args.root)
    if args.is_running: raise SystemExit(0 if reader.get()['worker_alive'] else 1)
    if args.serve:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_GET(self):
                path=self.path.split('?')[0]
                if path not in ('/','/status'):self.send_error(404);return
                try:body=PAGE.encode() if path=='/' else json.dumps(reader.get(),ensure_ascii=False).encode()
                except Exception: self.send_error(503,'Cannot read local progress');return
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8' if path=='/' else 'application/json; charset=utf-8')
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        print(f'Live read-only dashboard: http://127.0.0.1:{args.port}/',flush=True)
    try:
        while True:
            s=reader.get()
            print(f"{s['phase']} | alive={s['worker_alive']} | OCR pages {s['full_ocr_pages']}/{s['total_pages']} | "
                  f"question candidates {s['saved_question_candidates']} | active {s['active_candidates']} | "
                  f"requests {s['requests_this_run']} | references {s['qualified_references']}",flush=True)
            if s['retry_not_before'] and s['retry_not_before']>s['timestamp']:
                date=datetime.fromtimestamp(s['retry_not_before'],timezone(timedelta(hours=3,minutes=30)))
                print(f'Next allowed attempt: {date:%Y-%m-%d %H:%M:%S} Tehran',flush=True)
            if not (args.watch or args.serve):break
            time.sleep(5)
    except KeyboardInterrupt: pass
    finally:
        if args.serve:server.shutdown();server.server_close()


if __name__=='__main__':main()
