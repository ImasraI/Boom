#!/usr/bin/env python3
"""VM-side pull deployment. Standard library only; no GitHub/SSH secrets required."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request


def command(args,cwd=None,timeout=60):
    p=subprocess.run(args,cwd=cwd,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},
                     capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError('Command failed: '+str(args[0]))
    return p.stdout.strip()


def write_state(folder,**value):
    prior=json.loads((folder/'status.json').read_text()) if (folder/'status.json').exists() else {}
    if value.get('phase')!='deployed' and prior.get('failed_commit') and 'failed_commit' not in value:
        value['failed_commit']=prior['failed_commit']
    value['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    temp=folder/'status.tmp';temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(folder/'status.json')
    print(json.dumps(value),flush=True)


def latest_ci_state(payload,sha):
    rows=[r for r in payload.get('workflow_runs',[]) if r.get('head_sha')==sha
          and r.get('head_branch')=='main' and r.get('event')=='push' and r.get('name')=='Boom checks']
    if not rows:return 'waiting_ci'
    row=max(rows,key=lambda r:r['id'])
    if row.get('status')!='completed':return 'waiting_ci'
    return 'ready' if row.get('conclusion')=='success' else 'ci_failed'


def ci_status(sha):
    url='https://api.github.com/repos/ImasraI/Boom/actions/workflows/ci.yml/runs?'+urllib.parse.urlencode(
        {'head_sha':sha,'branch':'main','event':'push','per_page':5})
    req=urllib.request.Request(url,headers={'User-Agent':'Boom-Oracle-AutoDeploy','Accept':'application/vnd.github+json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req,timeout=25) as response:data=json.loads(response.read(1000000))
    return latest_ci_state(data,sha)


def health():
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                'http://127.0.0.1:8000/api/health',timeout=4) as r:
            return r.status==200 and json.load(r).get('status')=='ok'
    except Exception:return False


def wait_healthy():
    for _ in range(30):
        if health():return True
        time.sleep(2)
    return False


def service(action):command(['sudo','-n','systemctl',action,'boom-backend'],timeout=90)


def backup(repo,destination):
    destination.mkdir(parents=True,exist_ok=False)
    db=repo/'backend/rag_data.db'
    with sqlite3.connect(db) as src,sqlite3.connect(destination/'rag_data.db') as dst:src.backup(dst)
    chroma=repo/'backend/data/chroma_db'
    if chroma.exists():shutil.copytree(chroma,destination/'chroma_db')
    env=repo/'backend/.env'
    if env.exists():
        shutil.copy2(env,destination/'backend.env');os.chmod(destination/'backend.env',0o600)


def deploy(repo,state,backups,target,previous,backend_changed,deps_changed):
    stopped=False;backup_path=None
    python=str(repo/'backend/.venv/bin/python')
    try:
        if backend_changed:
            sources=[repo/'backend/rag_data.db',repo/'backend/data/chroma_db']
            size=sum(f.stat().st_size for p in sources for f in ([p] if p.is_file() else p.rglob('*')) if f.is_file())
            if shutil.disk_usage(backups).free<max(2*1024**3,int(size*1.2)):
                raise RuntimeError('Insufficient free space for automatic backup')
            service('stop');stopped=True
            stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup_path=backups/(stamp+'-'+target[:12]);backup(repo,backup_path)
        command(['git','checkout','main'],cwd=repo)
        command(['git','merge','--ff-only',target],cwd=repo)
        if deps_changed:
            command([python,'-m','pip','install','-r','requirements.txt'],cwd=repo/'backend',timeout=300)
        if backend_changed:
            command([python,'-m','pip','check'],cwd=repo/'backend',timeout=60)
            service('start');stopped=False
            if not wait_healthy():raise RuntimeError('Post-deployment health failed')
        write_state(state,phase='deployed',last_good=target,previous=previous,backup=str(backup_path) if backup_path else None,
                    backend_restarted=backend_changed)
    except Exception as error:
        # Roll back CODE only. Never replace the live account/corpus databases.
        try:
            if backend_changed:
                service('stop');stopped=True
            command(['git','checkout','--detach',previous],cwd=repo)
            if deps_changed:command([python,'-m','pip','install','-r','requirements.txt'],cwd=repo/'backend',timeout=300)
            if backend_changed:
                service('start');stopped=False
            recovered=wait_healthy() if backend_changed else True
            write_state(state,phase='rolled_back' if recovered else 'rollback_unhealthy',last_good=previous,
                failed_commit=target,error=str(error),backup=str(backup_path) if backup_path else None)
        except Exception:
            write_state(state,phase='rollback_failed',failed_commit=target,last_good=previous,
                        error='Manual intervention required; backup retained',backup=str(backup_path) if backup_path else None)
        finally:
            if stopped:
                try:service('start')
                except Exception:pass
        return False
    return True


def update(repo,state,backups):
    old=json.loads((state/'status.json').read_text()) if (state/'status.json').exists() else {}
    current=command(['git','rev-parse','HEAD'],cwd=repo)
    if (state/'PAUSED').exists():write_state(state,phase='paused',last_good=old.get('last_good',current));return
    remote=command(['git','remote','get-url','origin'],cwd=repo)
    if remote.rstrip('/').removesuffix('.git')!='https://github.com/ImasraI/Boom':raise RuntimeError('Unexpected deployment remote')
    if command(['git','status','--porcelain'],cwd=repo):
        write_state(state,phase='local_changes_hold',last_good=old.get('last_good',current));return
    branch=command(['git','branch','--show-current'],cwd=repo)
    if branch!='main' and not (not branch and old.get('last_good')==current and old.get('failed_commit')):
        write_state(state,phase='branch_hold',last_good=old.get('last_good',current));return
    command(['git','fetch','origin','main'],cwd=repo,timeout=45)
    target=command(['git','rev-parse','refs/remotes/origin/main'],cwd=repo)
    if target==old.get('failed_commit'):
        # Keep failure visible; no endless retries of a broken revision.
        print('Failed revision remains quarantined',flush=True);return
    if target==current:
        write_state(state,phase='up_to_date',last_good=current);return
    command(['git','merge-base','--is-ancestor',current,target],cwd=repo)
    gate=ci_status(target)
    if gate!='ready':write_state(state,phase=gate,last_good=current,pending_commit=target);return
    names=command(['git','diff','--name-only',current,target],cwd=repo).splitlines()
    deps='backend/requirements.txt' in names
    backend_changed=deps or any(n.startswith('backend/app/') for n in names)
    deploy(repo,state,backups,target,current,backend_changed,deps)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path('/home/ubuntu/Boom'))
    parser.add_argument('--state',type=Path,default=Path('/home/ubuntu/.local/state/boom-deploy'))
    parser.add_argument('--backups',type=Path,default=Path('/home/ubuntu/backups/automatic'))
    args=parser.parse_args();args.state.mkdir(parents=True,exist_ok=True);args.backups.mkdir(parents=True,exist_ok=True)
    import fcntl
    with (args.state/'deploy.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        try:update(args.repo.resolve(),args.state.resolve(),args.backups.resolve())
        except Exception as error:
            old=json.loads((args.state/'status.json').read_text()) if (args.state/'status.json').exists() else {}
            write_state(args.state,phase='check_failed',last_good=old.get('last_good'),error_type=type(error).__name__)
            # Network errors do not change the running app or erase failure state.


if __name__=='__main__':main()
