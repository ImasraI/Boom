import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

spec=importlib.util.spec_from_file_location('boom_auto_update',Path(__file__).resolve().parents[1]/'deploy/auto_update.py')
deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)


def ci_run(**changes):
    r={'id':1,'head_sha':'a'*40,'head_branch':'main','event':'push','name':'Boom checks','status':'completed','conclusion':'success'}
    return {**r,**changes}


@pytest.mark.parametrize('change,expected',[
 ({},'ready'),({'conclusion':'failure'},'ci_failed'),({'status':'in_progress'},'waiting_ci'),
 ({'head_sha':'b'*40},'waiting_ci'),({'event':'pull_request'},'waiting_ci'),
 ({'name':'Other workflow'},'waiting_ci'),({'head_branch':'dev'},'waiting_ci')])
def test_only_exact_main_push_ci_can_authorize_deployment(change,expected):
    assert deploy.latest_ci_state({'workflow_runs':[ci_run(**change)]},'a'*40)==expected


def test_newest_ci_rerun_wins():
    assert deploy.latest_ci_state({'workflow_runs':[ci_run(),ci_run(id=2,conclusion='failure')]},'a'*40)=='ci_failed'


def test_failure_quarantine_survives_waiting_and_pause(tmp_path):
    deploy.write_state(tmp_path,phase='rolled_back',last_good='old',failed_commit='bad')
    deploy.write_state(tmp_path,phase='paused',last_good='old')
    assert json.loads((tmp_path/'status.json').read_text())['failed_commit']=='bad'
    deploy.write_state(tmp_path,phase='deployed',last_good='new')
    assert 'failed_commit' not in json.loads((tmp_path/'status.json').read_text())


def test_dirty_worktree_is_never_updated(tmp_path,monkeypatch):
    calls=[]
    def command(args,**kw):
        calls.append(args)
        if args[1:]==['rev-parse','HEAD']:return 'old'
        if args[1:]==['remote','get-url','origin']:return 'https://github.com/ImasraI/Boom.git'
        if args[1:]==['status','--porcelain']:return ' M app.py'
        raise AssertionError('Dirty tree must not fetch or checkout')
    monkeypatch.setattr(deploy,'command',command)
    deploy.update(tmp_path,tmp_path,tmp_path)
    assert json.loads((tmp_path/'status.json').read_text())['phase']=='local_changes_hold'


def test_unhealthy_release_rolls_back_code_without_restoring_live_databases(tmp_path,monkeypatch):
    calls=[];repo=tmp_path/'repo';repo.mkdir();state=tmp_path/'state';state.mkdir();backups=tmp_path/'backups';backups.mkdir()
    monkeypatch.setattr(deploy,'command',lambda args,**kw:calls.append(args) or '')
    monkeypatch.setattr(deploy,'service',lambda action:calls.append(['service',action]))
    monkeypatch.setattr(deploy,'backup',lambda *args:calls.append(['backup']))
    health=iter([False,True]);monkeypatch.setattr(deploy,'wait_healthy',lambda:next(health))
    monkeypatch.setattr(deploy.shutil,'disk_usage',lambda p:SimpleNamespace(free=10*1024**3))
    assert deploy.deploy(repo,state,backups,'new','old',True,False) is False
    assert ['git','checkout','--detach','old'] in calls
    assert calls.index(['backup'])<calls.index(['git','merge','--ff-only','new'])
    result=json.loads((state/'status.json').read_text())
    assert result['phase']=='rolled_back' and result['failed_commit']=='new'


def test_frontend_only_update_does_not_stop_backend_or_copy_databases(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(deploy,'command',lambda args,**kw:calls.append(args) or '')
    monkeypatch.setattr(deploy,'service',lambda action:pytest.fail('No service change for frontend-only update'))
    monkeypatch.setattr(deploy,'backup',lambda *args:pytest.fail('No data copy for frontend-only update'))
    assert deploy.deploy(tmp_path,tmp_path,tmp_path,'new','old',False,False)
    assert json.loads((tmp_path/'status.json').read_text())['last_good']=='new'
