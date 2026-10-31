"""Exercise a real API with a dedicated non-admin account; never prints credentials.

Run from backend. --provision creates only the named interview account in this
environment's database. External SMS delivery is deliberately not triggered.
"""
import argparse
from datetime import date, timedelta
import json
import logging
from pathlib import Path
import secrets
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--provision', action='store_true')
    parser.add_argument('--chat', action='store_true')
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--full-mock', action='store_true')
    parser.add_argument('--report', default='data/interview-readiness/smoke.json')
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    directory = Path(args.report).resolve().parent
    directory.mkdir(parents=True, exist_ok=True)
    credentials = directory / 'account.private.json'
    if args.provision:
        from app.auth.database import SessionLocal, User
        from app.auth.security import get_password_hash
        with SessionLocal() as db:
            if credentials.exists():
                account = json.loads(credentials.read_text(encoding='utf-8'))
                if not db.query(User).filter_by(username=account['username']).first():
                    raise RuntimeError('Saved smoke account is missing; choose a fresh report directory')
            else:
                account = {'username': 'interview-check-' + secrets.token_hex(5),
                           'password': secrets.token_urlsafe(24)}
                db.add(User(username=account['username'],
                            hashed_password=get_password_hash(account['password']),
                            is_admin=False, phone_verified=False))
                db.commit()
                credentials.write_text(json.dumps(account), encoding='utf-8')
                try:
                    credentials.chmod(0o600)
                except OSError:
                    pass
    if not credentials.exists():
        raise RuntimeError('Provision the dedicated smoke account first')
    account = json.loads(credentials.read_text(encoding='utf-8'))
    session = requests.Session()
    session.trust_env = False
    checks = []
    def call(label, method, path, **kwargs):
        started = time.monotonic()
        try:
            response = session.request(method, args.api.rstrip('/') + path,
                                       timeout=(10, 180), **kwargs)
            try:
                data = response.json()
            except ValueError:
                data = {}
            entry = {'check': label, 'status': response.status_code,
                     'seconds': round(time.monotonic() - started, 2),
                     'passed': response.status_code == 200}
            if response.status_code != 200:
                entry['detail'] = str(data.get('detail', 'non-JSON response'))[:400]
            checks.append(entry)
            return data, entry
        except requests.RequestException as exc:
            entry = {'check': label, 'passed': False, 'error': type(exc).__name__,
                     'seconds': round(time.monotonic() - started, 2)}
            checks.append(entry)
            return {}, entry
    call('health', 'GET', '/api/health')
    data, login = call('password_login', 'POST', '/api/auth/login', data=account)
    if login['passed'] and data.get('access_token'):
        session.headers['Authorization'] = 'Bearer ' + data['access_token']
        call('identity', 'GET', '/api/auth/me')
        data, _ = call('profile_read', 'GET', '/api/profile')
        profile = data.get('profile', {})
        student = {'name': 'Interview test', 'major': 'ریاضی فیزیک',
                   'grade': 'دوازدهم', 'studyHours': '4', 'testExams': ['ماز']}
        call('onboarding_profile', 'PATCH', '/api/profile', json={
            'version': profile.get('version'), 'name': 'Interview test',
            'major': student['major'], 'grade': student['grade'],
            'study_hours': '4', 'test_exams': ['ماز']})
        today = date.today()
        saturday = today - timedelta(days=(today.weekday() + 2) % 7)
        week, entry = call('weekly_plan', 'POST', '/api/boom/weekly-plan', json={
            'student': student, 'daily_hours': 4, 'week_start': saturday.isoformat()})
        blocks = week.get('blocks', [])
        entry['blocks'] = len(blocks)
        entry['passed'] = entry['passed'] and bool(blocks)
        calendar, persisted = call('calendar_persistence', 'GET', '/api/profile/calendar')
        persisted['has_saved_week'] = saturday.isoformat() in json.dumps(calendar)
        persisted['passed'] = persisted['passed'] and persisted['has_saved_week']
        call('ranked_availability', 'GET', '/api/arena/status')
        filters, entry = call('ranked_filters', 'GET', '/api/arena/filters')
        entry['response_fields'] = sorted(filters) if isinstance(filters, dict) else []
        if args.chat:
            for label, question in [('chat_greeting', 'سلام'), ('chat_grounded',
                    'مشتق تابع x^2 چیست؟ بر اساس کتاب درسی توضیح بده و منبع را مشخص کن.')]:
                result, entry = call(label, 'POST', '/api/boom/chat', json={
                    'question': question, 'student': student,
                    'conversation_id': 'interview-smoke', 'top_k': 4})
                answer = str(result.get('answer') or '')
                entry['answer_characters'] = len(answer)
                entry['sources'] = len(result.get('sources') or [])
                entry['passed'] = entry['passed'] and bool(answer) and not any(
                    phrase in answer for phrase in ['متاسفانه مدل نتوانست', 'متأسفانه مدل نتوانست'])
                if label == 'chat_grounded':
                    entry['passed'] = entry['passed'] and entry['sources'] > 0
        if args.mock:
            result, entry = call('verified_practice', 'POST', '/api/mocks/generate',
                json={'subjects': ['ریاضی'], 'total_questions': 3,
                      'difficulty': 'konkur', 'mode': 'practice', 'stock_only': True,
                      'student': student})
            entry['question_count'] = result.get('total_questions', 0)
            entry['passed'] = entry['passed'] and entry['question_count'] == 3
            if result.get('mock_id'):
                paper, read = call('practice_read', 'GET', f"/api/mocks/{result['mock_id']}")
                read['question_count'] = len(paper.get('questions') or [])
                read['passed'] = read['passed'] and read['question_count'] == 3
        if args.full_mock:
            result, entry = call('full_booklet', 'POST', '/api/mocks/generate',
                json={'difficulty': 'konkur', 'stock_only': True, 'student': student})
            entry['question_count'] = result.get('total_questions', 0)
            entry['passed'] = entry['passed'] and entry['question_count'] == 105
            if result.get('mock_id'):
                paper, read = call('full_booklet_read', 'GET', f"/api/mocks/{result['mock_id']}")
                read['question_count'] = len(paper.get('questions') or [])
                read['passed'] = read['passed'] and read['question_count'] == 105
    report = {'api': args.api, 'checks': checks,
              'passed': bool(checks) and all(row['passed'] for row in checks),
              'scope': 'Dedicated account, real HTTP requests. No SMS delivery test.'}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
