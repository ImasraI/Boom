"""Start the loopback review API and Vite without starting scanners or mock pools."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.request import build_opener, ProxyHandler
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / 'backend/data/authoring_work/review-server'
HTTP = build_opener(ProxyHandler({}))  # Local readiness checks never use the VPN.

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.5): return True
    except OSError: return False

def fetch(path, port):
    with HTTP.open(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
        return response.read().decode('utf-8')

def launch(name, command, cwd, env):
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / f'{name}-stdout.log').open('ab') as out, (LOGS / f'{name}-stderr.log').open('ab') as err:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, close_fds=True,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
    return process

def start():
    env = dict(os.environ)
    env['NO_PROXY'] = '127.0.0.1,localhost'
    env['VITE_API_URL'] = 'http://127.0.0.1:8000'
    env['PORT'] = '5948'
    processes = []
    if not listening(8000):
        processes.append(launch('api', [str(ROOT/'backend/.venv/Scripts/python.exe'), '-X', 'utf8',
            'scripts/authoring_review_server.py'], ROOT/'backend', env))
    if not listening(5948):
        node = shutil.which('node')
        if not node: raise RuntimeError('Node.js is unavailable. Install the existing project runtime first.')
        processes.append(launch('frontend', [node, str(ROOT/'frontend/node_modules/vite/bin/vite.js'),
            '--host', '127.0.0.1', '--port', '5948', '--strictPort'], ROOT/'frontend', env))
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            paths = json.loads(fetch('/openapi.json',8000)).get('paths',{})
            html = fetch('/authoring-review.html',5948)
            if '/api/authoring-review/questions' not in paths or '/src/authoringReview/live.tsx' not in html:
                raise RuntimeError('A different service is using a review port; it has been preserved.')
            print('Review site is ready: http://127.0.0.1:5948/authoring-review.html')
            print('Use your existing local admin login. Scanners and mock pools were not started.')
            return
        except (URLError, OSError, ValueError):
            if any(p.poll() is not None for p in processes): break
            time.sleep(.5)
    raise RuntimeError('Review startup failed. See backend/data/authoring_work/review-server/*-stderr.log')

if __name__ == '__main__':
    try: start()
    except Exception as error:
        print(str(error))
        raise SystemExit(1)
