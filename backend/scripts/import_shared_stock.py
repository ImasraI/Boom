"""Import an authorized shared-stock export without copying accounts or replacing DBs.

The JSON must contain bank/papers arrays exported from the source database.
Existing fingerprints are reused. A receipt makes repeated imports idempotent.
Verification and status are preserved; this script does not approve questions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args()
    payload = args.export.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    data = json.loads(payload)
    if not isinstance(data.get('bank'), list) or not isinstance(data.get('papers'), list):
        raise ValueError('Expected bank and papers arrays')
    for row in data['bank']:
        if row.get('owner_id') != 0 or row.get('status') != 'active' or row.get('verified') != 1:
            raise ValueError('Export contains nonshared or unverified bank data')
    for row in data['papers']:
        if row.get('student_id') != 0 or row.get('status') != 'pending_use':
            raise ValueError('Export contains an assigned or nonshared paper')
    receipt_dir = args.database.resolve().parent / 'shared-stock-imports'
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / (digest + '.json')
    if receipt.exists():
        print('This exact export was already imported; no duplicates added.')
        return
    db = sqlite3.connect(args.database)
    backup = sqlite3.connect(receipt_dir / ('before-' + digest[:12] + '.sqlite3'))
    db.backup(backup)
    backup.close()
    mapping = {}
    imported = 0
    try:
        with db:
            columns = {table: {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')}
                       for table in ('bank_questions', 'generated_mocks')}
            for row in data['bank']:
                fields = [key for key in row if key != 'id']
                if not set(fields) <= columns['bank_questions']:
                    raise ValueError('Unknown bank fields in export')
                db.execute('INSERT OR IGNORE INTO bank_questions (' + ','.join(fields) +
                           ') VALUES (' + ','.join('?' for _ in fields) + ')',
                           [row[key] for key in fields])
                mapping[row['id']] = db.execute(
                    'SELECT id FROM bank_questions WHERE fingerprint=?',
                    (row['fingerprint'],)).fetchone()[0]
            for original in data['papers']:
                row = dict(original)
                questions = json.loads(row['questions'])
                for question in questions:
                    old = question.get('bank_id')
                    if old in mapping:
                        question['bank_id'] = mapping[old]
                    else:
                        question.pop('bank_id', None)
                row.update(questions=json.dumps(questions, ensure_ascii=False),
                           bank_indexed=0, bank_scope='shared')
                fields = [key for key in row if key != 'id']
                if not set(fields) <= columns['generated_mocks']:
                    raise ValueError('Unknown paper fields in export')
                # The source identity and timestamp distinguish actual papers;
                # do not insert the same snapshot on a later expanded export.
                present = db.execute('SELECT 1 FROM generated_mocks WHERE student_id=0 '
                    'AND created_at=? AND title=? AND difficulty=?',
                    (row['created_at'], row['title'], row['difficulty'])).fetchone()
                if not present:
                    db.execute('INSERT INTO generated_mocks (' + ','.join(fields) +
                               ') VALUES (' + ','.join('?' for _ in fields) + ')',
                               [row[key] for key in fields])
                    imported += 1
        receipt.write_text(json.dumps({'sha256': digest, 'bank_records': len(mapping),
                                      'papers_added': imported}), encoding='utf-8')
    finally:
        db.close()
    print(f'Imported/reused {len(mapping)} shared verified bank records; added {imported} shared papers.')


if __name__ == '__main__':
    main()
