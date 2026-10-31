"""Start the prepared local interview demo without loading experimental app changes.

Run: backend/.venv/Scripts/python.exe backend/scripts/run_interview.py
The prepared backend is an ignored snapshot of the deployed revision; its DB
contains shared stock and dedicated test accounts, not production user records.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'tmp/interview-readiness'


def listening(url):
    try:
        with build_opener(ProxyHandler({})).open(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def main():
    backend = DEMO / 'release/backend'
    if not (backend / 'interview_app.py').exists():
        raise SystemExit('Prepared interview snapshot is missing. See docs/INTERVIEW_READINESS.md.')
    processes = {}
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    tunnel_file = DEMO / 'provider-tunnel.private.json'
    if tunnel_file.exists():
        import socket
        tunnel = json.loads(tunnel_file.read_text(encoding='utf-8'))
        with socket.socket() as probe:
            probe.settimeout(1)
            connected = probe.connect_ex(('127.0.0.1', tunnel['port'])) == 0
        if not connected:
            with (DEMO / 'tunnel.stderr.log').open('ab') as err:
                child = subprocess.Popen([tunnel['ssh'], '-i', tunnel['identity'],
                    '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=30',
                    '-D', f"127.0.0.1:{tunnel['port']}", '-N', tunnel['host']],
                    stdout=subprocess.DEVNULL, stderr=err, **options)
                processes['provider_tunnel'] = child.pid
        proxy = f"socks5://127.0.0.1:{tunnel['port']}"
        env.update(HTTPS_PROXY=proxy, ALL_PROXY=proxy, NO_PROXY='localhost,127.0.0.1')
    if not listening('http://127.0.0.1:8000/api/health'):
        with (DEMO / 'backend.stdout.log').open('ab') as out, (DEMO / 'backend.stderr.log').open('ab') as err:
            child = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'interview_app:app',
                '--host', '127.0.0.1', '--port', '8000'], cwd=backend, env=env,
                stdout=out, stderr=err, **options)
            processes['backend'] = child.pid
    if not listening('http://127.0.0.1:8443'):
        import shutil
        node = shutil.which('node')
        if not node:
            raise SystemExit('Node.js is required for the frontend')
        with (DEMO / 'frontend.stdout.log').open('ab') as out, (DEMO / 'frontend.stderr.log').open('ab') as err:
            child = subprocess.Popen([node, 'node_modules/vite/bin/vite.js',
                '--host', '127.0.0.1', '--port', '8443'], cwd=ROOT / 'frontend',
                stdout=out, stderr=err, **options)
            processes['frontend'] = child.pid
    if processes:
        (DEMO / 'processes.json').write_text(json.dumps(processes), encoding='utf-8')
    print('Frontend: http://127.0.0.1:8443')
    print('API documentation: http://127.0.0.1:8000/docs')
    print('Dedicated API-check credentials: backend/data/interview-readiness/account.private.json')
    print('Optional local reranking is disabled; shared verified stock is available.')


if __name__ == '__main__':
    main()
