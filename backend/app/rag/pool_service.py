"""One persistent, selected pool run inside the single API process.

Quota pauses make no provider calls. Only an explicit admin start enables a
run; the saved selection resumes after a restart. Inventory is never capped.
"""
import json
import os
import threading
from pathlib import Path
from fastapi import HTTPException
from app.config import get_settings
from app.auth.database import SessionLocal
from app.rag import pool_core
from app.rag.provider_quota import pool_quota_status
from app.utils.logger import get_logger

logger = get_logger(__name__)
_LOCK = threading.RLock()
_wake = threading.Event()
_shutdown = threading.Event()
_thread = None


def _path():
    path = Path(get_settings().POOL_RUN_STATE_FILE)
    return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path


def snapshot():
    with _LOCK:
        try:
            return json.loads(_path().read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {'enabled':False, 'status':'idle', 'produced':0}


def _save(state):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    os.chmod(temp, 0o600)
    temp.replace(path)


def _update(**values):
    with _LOCK:
        state = snapshot()
        state.update(values)
        _save(state)
        return state


def start(config):
    global _thread
    with _LOCK:
        if snapshot().get('enabled') or pool_core.progress_snapshot()['active']:
            raise HTTPException(409, 'یک تولید یا انتظار سهمیه در حال اجرا است؛ ابتدا آن را متوقف کن.')
        previous = snapshot()
        _save({'enabled':True, 'status':'starting', 'config':config,
               'produced':0, 'cursor':0, 'last_error':'', 'retry_at':None})
        try:
            resume()
        except Exception:
            _save(previous)
            raise
    return {'ok':True, 'started':True}


def resume():
    global _thread
    with _LOCK:
        if not snapshot().get('enabled') or (_thread and _thread.is_alive()):
            return
        _shutdown.clear()
        _wake.clear()
        _thread = threading.Thread(target=_run, daemon=True, name='selected-pool-worker')
        _thread.start()


def cancel():
    with _LOCK:
        if not snapshot().get('enabled'):
            return False
        _update(enabled=False, status='stopping')
        pool_core.request_cancel()
        _wake.set()
        return True


def shutdown():
    # Preserve enabled/config: this is a server restart, not admin cancellation.
    _shutdown.set()
    _wake.set()


def notify_credentials_changed():
    """Recheck a waiting run without resetting its quota history or selection."""
    _wake.set()


def _run():
    failures = 0
    owned = False
    try:
        while not _shutdown.is_set():
            state = snapshot()
            if not state.get('enabled'):
                break
            config = state['config']
            if config['count'] and state['produced'] >= config['count']:
                _update(enabled=False, status='finished')
                break
            if not owned:
                owned = pool_core.begin_progress('selected:' + config['kind'])
                if not owned:
                    _update(status='waiting_for_worker')
                    _wake.wait(30)
                    _wake.clear()
                    continue
                pool_core.clear_cancel()
            health = pool_quota_status()
            if health['blocked']:
                # Stored verified stock remains usable even while API quotas
                # are blocked. Drain at most one complete booklet per pass.
                shelves = _shelves(config)
                assembled = False
                for offset in range(len(shelves)):
                    if _shutdown.is_set() or not snapshot().get('enabled'):
                        break
                    index = state['cursor'] + offset
                    major, difficulty = shelves[index % len(shelves)]
                    kwargs = {'grade':config['grade'], 'subjects':config.get('subjects'),
                              'topics':config.get('topics')}
                    if difficulty != pool_core.DUEL_DIFFICULTY:
                        kwargs['total_questions'] = config.get('total_questions', 0)
                    with SessionLocal() as db:
                        assembled = pool_core.assemble_stock(db, major, difficulty, **kwargs)
                    if assembled:
                        with _LOCK:
                            current = snapshot()
                            current.update(cursor=index + 1, produced=current['produced'] + 1)
                            _save(current)
                        pool_core.bump_produced()
                        break
                if assembled:
                    failures = 0
                    continue
                if not health.get('retry_at'):
                    _update(enabled=False, status='failed', last_error=health['message'])
                    break  # Access errors need a changed credential, not polling.
                _update(status='waiting_for_quota', retry_at=health['retry_at'], last_error=health['message'])
                pool_core.set_phase('waiting_for_quota')
                _wake.wait(min(60, max(1, health.get('retry_after', 60))))
                _wake.clear()
                failures = 0
                continue
            _update(status='generating', retry_at=None, last_error='')
            shelves = _shelves(config)
            major, difficulty = shelves[state['cursor'] % len(shelves)]
            pool_core.set_current(major, difficulty)
            pool_core.add_planned(1)
            with SessionLocal() as db:
                kwargs = {'grade':config['grade'], 'subjects':config.get('subjects'), 'topics':config.get('topics')}
                if difficulty == pool_core.DUEL_DIFFICULTY:
                    success = pool_core.generate_one_duel(db, major, **kwargs)
                else:
                    success = pool_core.generate_one(db, major, difficulty,
                        total_questions=config.get('total_questions', 0), **kwargs)
            with _LOCK:
                current = snapshot()
                current['cursor'] = state['cursor'] + 1
                if success:
                    current['produced'] += 1
                    pool_core.bump_produced()
                _save(current)  # Preserve a cancellation that arrived during generation.
            failures = 0 if success else failures + 1
            if failures >= pool_core.POOL_MAX_PROVIDER_FAILURES and not pool_quota_status()['blocked']:
                _update(enabled=False, status='failed', last_error='سه تولید متوالی دفترچه معتبر نساخت؛ سوال‌های تاییدشده در بانک نگه داشته شدند.')
                break
    except Exception:
        logger.exception('Selected pool run failed')
        _update(enabled=False, status='failed', last_error='تولید متوقف شد؛ خطای سرور را بررسی کنید.')
    finally:
        if owned:
            pool_core.finish_progress()
        if snapshot().get('status') == 'stopping':
            _update(status='stopped')


def _shelves(config):
    shelves = []
    for major in config['majors']:
        if config['kind'] in ('mock', 'both'):
            shelves.extend((major, difficulty) for difficulty in config['difficulties'])
        if config['kind'] in ('ranked', 'both'):
            shelves.append((major, pool_core.DUEL_DIFFICULTY))
    return shelves
