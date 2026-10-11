"""Book-backed exam coverage, shared by drafting and verified-bank assembly.

The math quotas are a product blueprint, not an assertion about Sanjesh's
annual chapter distribution. Topics come only from the promoted OCR catalogue.
"""
import json
import random
import re
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.rag.book_curriculum import load_catalog, norm, page_text
from app.rag.konkur_format import RIAZI_MATH_BLUEPRINT


def math_branch(subject, title=""):
    if subject == "هندسه":
        return "geometry"
    if subject == "آمار و احتمال":
        return "statistics"
    if subject in ("ریاضیات گسسته", "جبر و گسسته", "گسسته و آمار و احتمال"):
        return "statistics" if any(norm(t) in norm(title) for t in (
            "احتمال", "آمار", "داده", "پراکندگی", "گرایش به مرکز", "برآورد")) else "discrete"
    if subject in ("حسابان", "ریاضی"):
        return "calculus"
    return ""


def full_plan(plan, major):
    if major != "riazi":
        return [dict(row) for row in plan]
    return [{**row, "major": major, "book_grounded": True, "full_mock": True,
             **({"branches": dict(RIAZI_MATH_BLUEPRINT)}
                if row['name'] == 'ریاضی' and row['questions'] == 40 else {})}
            for row in plan]


def coverage_rows(plan):
    """Expand quotas internally while retaining the public three-subject plan."""
    rows = []
    for row in plan:
        if row.get('branches'):
            rows.extend({**row, 'questions': count, 'branch': branch}
                        for branch, count in row['branches'].items() if count)
        else:
            rows.append(dict(row))
    return rows


def matches_plan(questions, plan, grade="", topics=()):
    if len(questions) != sum(row['questions'] for row in plan):
        return False
    if any(row.get('full_mock') for row in plan) and any(
            q.get('grounding_status') != 'book_ocr' or not q.get('curriculum_id') or
            not q.get('book') or type(q.get('page')) is not int or not q.get('source_quote')
            for q in questions):
        return False
    for row in coverage_rows(plan):
        selected = [q for q in questions if q.get('subject') == row['name'] and
                    (not row.get('branch') or q.get('branch') == row['branch'])]
        if len(selected) != row['questions']:
            return False
        if row.get('full_mock'):
            expected = min(row['questions'], len(lessons_for(row, grade, topics)))
            if len({q.get('curriculum_id') for q in selected}) < expected:
                return False
    return True


def lessons_for(row, grade="", topics=(), catalog=None):
    from app.rag.question_bank import grade_number
    catalog = load_catalog() if catalog is None else catalog
    wanted = [norm(t) for t in topics if norm(t) and t != row['name']]
    candidates = []
    for node in catalog.get('nodes', []):
        subject = node.get('subject', '')
        branch = math_branch(subject, node.get('title', ''))
        if row.get('major', 'riazi') not in node.get('majors', []):
            continue
        if any(major not in node.get('majors', []) for major in row.get('majors', [])):
            continue
        if (row['name'] == 'ریاضی' and not branch) or (row['name'] != 'ریاضی' and subject != row['name']):
            continue
        if row.get('branch') and branch != row['branch']:
            continue
        if node.get('year', 0) > grade_number(grade) or not node.get('sources'):
            continue
        if wanted and not any(t in norm(node['title']) or t == norm(subject) for t in wanted):
            continue
        candidates.append(node)
    return candidates


def topic_slots(nodes, count, rng=None):
    """Round-robin grades and lessons; no single retrieved chapter dominates."""
    rng = rng or random.SystemRandom()
    groups = {}
    for node in nodes:
        groups.setdefault(node.get('year', 0), []).append(node)
    for group in groups.values():
        rng.shuffle(group)
    ordered = []
    while any(groups.values()):
        for year in sorted(groups):
            if groups[year]:
                ordered.append(groups[year].pop())
    return [ordered[i % len(ordered)] for i in range(count)] if ordered else []


@lru_cache(maxsize=80)
def _read_book(signature):
    pages = []
    for filename, _, _ in signature:
        path = Path(filename)
        try:
            text = page_text(path)
            # Structured question OCR supplies real stems/options as style examples.
            if path.suffix == '.json':
                data = json.loads(path.read_text(encoding='utf-8-sig'))
                if not data.get('error'):
                    data = data.get('data', data)
                    for q in data.get('questions', []) if isinstance(data, dict) else []:
                        if not isinstance(q, dict):
                            continue
                        stem = str(q.get('text') or q.get('question') or q.get('stem') or '')
                        options = q.get('options') or []
                        if stem:
                            text += '\n' + stem + '\n' + json.dumps(options, ensure_ascii=False)
            if text.strip():
                pages.append((int(re.search(r'page_(\d+)', path.name)[1]), text, norm(text)))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return pages


def book_excerpt(node, limit=1500):
    """Read only promoted shared OCR; no raw PDF or private-account access."""
    root = Path(get_settings().OCR_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    for source in node.get('sources', []):
        book = str(source.get('book') or '').removesuffix('.pdf')
        if not book or Path(book).name != book or '/' in book or '\\' in book:
            continue
        paths = {}
        for folder in (root / book, root / (book + '.pdf')):
            for path in [*folder.glob('page_*.txt'), *(folder / 'pages').glob('page_*.json')]:
                old = paths.get(path.stem)
                if old is None or path.stat().st_size > old.stat().st_size:
                    paths[path.stem] = path
        signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(paths.values()))
        words = [norm(w) for w in node['title'].split() if len(norm(w)) > 2]
        ranked = []
        for page, text, normalized in _read_book(signature):
            score = 10 * (norm(node['title']) in normalized) + sum(w in normalized for w in words)
            # A contents page proves a heading, but is not a question style example.
            enough_words = sum(w in normalized for w in words) >= max(1, (len(words) * 2 + 2) // 3)
            if score and enough_words and not ('فهرست' in text and page <= 18):
                ranked.append((score, page, text))
        if not ranked:
            continue
        _, page, text = max(ranked, key=lambda entry: (entry[0], len(entry[2])))
        needle = next((w for w in node['title'].split() if w in text and len(w) > 2), '')
        start = max(0, text.find(needle) - 100) if needle else 0
        return {'book': book, 'page': page, 'quote': text[start:start + limit]}
    return None
