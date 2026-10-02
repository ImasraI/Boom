"""Deterministic three-year curriculum graph for each student's major."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional


# The catalog is intentionally compact and prerequisite-oriented. It is a
# navigable backbone, not a claim that every textbook uses identical chapters.
_SUBJECT_LESSONS: Dict[str, List[dict]] = {
    "حسابان": [
        {"id": "functions", "title": "تابع‌ها", "year": 10, "importance": 5},
        {"id": "algebra", "title": "جبر و معادله", "year": 10, "importance": 4},
        {"id": "limits", "title": "حد و پیوستگی", "year": 11, "importance": 5, "requires": ["functions", "algebra"]},
        {"id": "derivatives", "title": "مشتق", "year": 11, "importance": 5, "requires": ["limits"]},
        {"id": "integrals", "title": "انتگرال", "year": 12, "importance": 5, "requires": ["derivatives"]},
        {"id": "sequences", "title": "دنباله و تصاعد", "year": 11, "importance": 3, "requires": ["algebra"]},
    ],
    "ریاضی": [
        {"id": "numbers", "title": "اعداد و عبارت‌ها", "year": 10, "importance": 4},
        {"id": "functions", "title": "تابع‌ها", "year": 10, "importance": 5},
        {"id": "limits", "title": "حد و پیوستگی", "year": 11, "importance": 5, "requires": ["functions"]},
        {"id": "derivatives", "title": "مشتق", "year": 11, "importance": 5, "requires": ["limits"]},
        {"id": "statistics", "title": "آمار و احتمال", "year": 11, "importance": 4, "requires": ["numbers"]},
    ],
    "جبر و گسسته": [
        {"id": "logic", "title": "منطق و گزاره‌ها", "year": 10, "importance": 3},
        {"id": "combinatorics", "title": "شمارش و ترکیبیات", "year": 11, "importance": 5, "requires": ["logic"]},
        {"id": "graph-theory", "title": "گراف و الگوریتم", "year": 12, "importance": 4, "requires": ["logic"]},
        {"id": "discrete-probability", "title": "احتمال گسسته", "year": 12, "importance": 4, "requires": ["combinatorics"]},
    ],
    "هندسه": [
        {"id": "geometry-basics", "title": "مفاهیم پایه هندسه", "year": 10, "importance": 4},
        {"id": "triangles", "title": "مثلث و تشابه", "year": 10, "importance": 5, "requires": ["geometry-basics"]},
        {"id": "circles", "title": "دایره", "year": 11, "importance": 4, "requires": ["triangles"]},
        {"id": "analytic-geometry", "title": "هندسه تحلیلی", "year": 11, "importance": 5, "requires": ["geometry-basics"]},
        {"id": "spatial-geometry", "title": "هندسه فضایی", "year": 12, "importance": 4, "requires": ["triangles"]},
    ],
    "فیزیک": [
        {"id": "measurement", "title": "اندازه‌گیری و بردار", "year": 10, "importance": 4},
        {"id": "kinematics", "title": "حرکت‌شناسی", "year": 10, "importance": 5, "requires": ["measurement"]},
        {"id": "dynamics", "title": "دینامیک", "year": 10, "importance": 5, "requires": ["kinematics"]},
        {"id": "work-energy", "title": "کار و انرژی", "year": 11, "importance": 5, "requires": ["dynamics"]},
        {"id": "electricity", "title": "الکتریسیته", "year": 11, "importance": 5, "requires": ["measurement"]},
        {"id": "waves", "title": "نوسان و موج", "year": 12, "importance": 4, "requires": ["kinematics"]},
    ],
    "شیمی": [
        {"id": "atomic", "title": "ساختار اتم", "year": 10, "importance": 5},
        {"id": "periodic", "title": "جدول تناوبی", "year": 10, "importance": 4, "requires": ["atomic"]},
        {"id": "stoichiometry", "title": "استوکیومتری", "year": 10, "importance": 5, "requires": ["atomic"]},
        {"id": "bonding", "title": "پیوندهای شیمیایی", "year": 11, "importance": 5, "requires": ["periodic"]},
        {"id": "equilibrium", "title": "تعادل شیمیایی", "year": 12, "importance": 5, "requires": ["stoichiometry", "bonding"]},
    ],
    "زیست‌شناسی": [
        {"id": "cell", "title": "یاخته و مولکول‌ها", "year": 10, "importance": 5},
        {"id": "metabolism", "title": "سوخت‌وساز", "year": 10, "importance": 4, "requires": ["cell"]},
        {"id": "genetics", "title": "ژنتیک", "year": 11, "importance": 5, "requires": ["cell"]},
        {"id": "physiology", "title": "دستگاه‌های بدن", "year": 11, "importance": 5, "requires": ["cell"]},
        {"id": "ecology", "title": "بوم‌شناسی", "year": 12, "importance": 4, "requires": ["cell"]},
    ],
    "ادبیات فارسی": [
        {"id": "vocabulary", "title": "لغت و املا", "year": 10, "importance": 4},
        {"id": "rhetoric", "title": "آرایه‌های ادبی", "year": 10, "importance": 5, "requires": ["vocabulary"]},
        {"id": "grammar", "title": "دستور زبان", "year": 11, "importance": 4, "requires": ["vocabulary"]},
        {"id": "literary-history", "title": "تاریخ ادبیات", "year": 12, "importance": 3, "requires": ["vocabulary"]},
    ],
    "عربی": [
        {"id": "vocabulary", "title": "واژگان و ترجمه", "year": 10, "importance": 5},
        {"id": "verb", "title": "فعل و صرف", "year": 10, "importance": 5, "requires": ["vocabulary"]},
        {"id": "syntax", "title": "ترکیب و نحو", "year": 11, "importance": 5, "requires": ["verb"]},
        {"id": "rhetoric", "title": "بلاغت و درک متن", "year": 12, "importance": 3, "requires": ["vocabulary"]},
    ],
    "دین و زندگی": [
        {"id": "belief", "title": "خداشناسی و جهان‌بینی", "year": 10, "importance": 4},
        {"id": "prophecy", "title": "نبوت و امامت", "year": 11, "importance": 4, "requires": ["belief"]},
        {"id": "ethics", "title": "اخلاق و سبک زندگی", "year": 12, "importance": 4, "requires": ["belief"]},
    ],
    "زبان انگلیسی": [
        {"id": "vocabulary", "title": "واژگان پایه", "year": 10, "importance": 5},
        {"id": "grammar", "title": "دستور زبان", "year": 10, "importance": 5},
        {"id": "reading", "title": "درک مطلب", "year": 11, "importance": 5, "requires": ["vocabulary", "grammar"]},
        {"id": "cloze", "title": "کلوز تست", "year": 12, "importance": 4, "requires": ["reading"]},
    ],
    "تاریخ": [
        {"id": "ancient", "title": "ایران باستان", "year": 10, "importance": 4},
        {"id": "islamic", "title": "ایران اسلامی", "year": 11, "importance": 5, "requires": ["ancient"]},
        {"id": "contemporary", "title": "تاریخ معاصر", "year": 12, "importance": 4, "requires": ["islamic"]},
    ],
    "جغرافیا": [
        {"id": "maps", "title": "نقشه و موقعیت", "year": 10, "importance": 4},
        {"id": "population", "title": "جمعیت و سکونت", "year": 11, "importance": 4, "requires": ["maps"]},
        {"id": "economy", "title": "جغرافیای اقتصادی", "year": 12, "importance": 4, "requires": ["maps"]},
    ],
    "اقتصاد": [
        {"id": "needs", "title": "نیاز و تولید", "year": 10, "importance": 4},
        {"id": "market", "title": "بازار و قیمت", "year": 11, "importance": 5, "requires": ["needs"]},
        {"id": "finance", "title": "پول و بانک", "year": 12, "importance": 4, "requires": ["market"]},
    ],
    "منطق و فلسفه": [
        {"id": "concepts", "title": "مفاهیم منطقی", "year": 10, "importance": 5},
        {"id": "syllogism", "title": "قیاس و استدلال", "year": 10, "importance": 5, "requires": ["concepts"]},
        {"id": "philosophy", "title": "آشنایی با فلسفه", "year": 11, "importance": 4, "requires": ["concepts"]},
        {"id": "schools", "title": "مکاتب فلسفی", "year": 12, "importance": 4, "requires": ["philosophy"]},
    ],
    "علوم اجتماعی": [
        {"id": "society", "title": "جامعه و فرهنگ", "year": 10, "importance": 4},
        {"id": "identity", "title": "هویت اجتماعی", "year": 11, "importance": 4, "requires": ["society"]},
        {"id": "media", "title": "رسانه و جهانی‌شدن", "year": 12, "importance": 3, "requires": ["identity"]},
    ],
}

_MAJOR_SUBJECTS = {
    "ریاضی فیزیک": ["حسابان", "جبر و گسسته", "هندسه", "فیزیک", "شیمی", "ادبیات فارسی", "عربی", "دین و زندگی", "زبان انگلیسی"],
    "علوم تجربی": ["ریاضی", "فیزیک", "شیمی", "زیست‌شناسی", "ادبیات فارسی", "عربی", "دین و زندگی", "زبان انگلیسی"],
    "علوم انسانی": ["ادبیات فارسی", "عربی", "تاریخ", "جغرافیا", "اقتصاد", "منطق و فلسفه", "دین و زندگی", "علوم اجتماعی", "ریاضی"],
    "هنر": ["نقاشی و هنرهای تجسمی", "ترکیب‌بندی", "تاریخ هنر", "ادبیات فارسی", "زبان انگلیسی", "ریاضی"],
    "زبان‌های خارجی": ["زبان انگلیسی", "ادبیات فارسی", "ریاضی", "تاریخ"],
}


def _slug(value: str) -> str:
    # \w keeps Unicode letters (Persian included); the old [a-z0-9] class
    # stripped every Persian character, collapsing ALL subject ids to
    # "subject:" and colliding lesson ids across subjects (vocabulary,
    # grammar, rhetoric appear in several books).
    return re.sub(r"[^\w]+", "-", value.lower()).strip("-") or "x"


def _catalog_for_major(major: str) -> List[str]:
    return list(_MAJOR_SUBJECTS.get(major, _MAJOR_SUBJECTS["ریاضی فیزیک"]))


def build_graph(major: str, evidence: Optional[Dict[tuple, dict]] = None,
                read_keys: Optional[Iterable[tuple]] = None) -> dict:
    """Build a user-scoped graph from static curriculum + private evidence."""
    evidence = evidence or {}
    read_keys = set(read_keys or [])
    nodes: List[dict] = []
    edges: List[dict] = []
    subject_ids = {}
    lesson_ids = {}

    for subject in _catalog_for_major(major):
        subject_id = f"subject:{_slug(subject)}"
        subject_ids[subject] = subject_id
        lessons = _SUBJECT_LESSONS.get(subject, [
            {"id": "foundations", "title": "مبانی و واژگان", "year": 10, "importance": 4},
            {"id": "core", "title": "مباحث اصلی", "year": 11, "importance": 5},
            {"id": "review", "title": "جمع‌بندی و تست", "year": 12, "importance": 4},
        ])
        subject_read = (subject, "") in read_keys or any(k[0] == subject for k in read_keys)
        stats = evidence.get((subject, ""), {})
        nodes.append({
            "id": subject_id, "kind": "subject", "subject": subject,
            "title": subject, "year": 0, "importance": 5,
            "opened": subject_read, "available": True,
            "attempted": stats.get("attempted", 0), "correct": stats.get("correct", 0),
            "wrong": stats.get("wrong", 0), "accuracy": stats.get("accuracy"),
        })
        previous = None
        for lesson in lessons:
            node_id = f"lesson:{_slug(subject)}:{lesson['id']}"
            lesson_ids[(subject, lesson["id"])] = node_id
            stat = evidence.get((subject, lesson["title"]), {})
            opened = (subject, lesson["title"]) in read_keys or stat.get("attempted", 0) > 0
            nodes.append({
                "id": node_id, "kind": "lesson", "subject": subject,
                "title": lesson["title"], "year": lesson["year"],
                "importance": lesson["importance"], "opened": opened,
                "available": False, "attempted": stat.get("attempted", 0),
                "correct": stat.get("correct", 0), "wrong": stat.get("wrong", 0),
                "accuracy": stat.get("accuracy"),
            })
            edges.append({"source": subject_id, "target": node_id, "kind": "contains"})
            if previous:
                edges.append({"source": previous, "target": node_id, "kind": "sequence"})
            for required in lesson.get("requires", []):
                required_id = lesson_ids.get((subject, required))
                if required_id:
                    edges.append({"source": required_id, "target": node_id, "kind": "prerequisite"})
            previous = node_id

    by_id = {node["id"]: node for node in nodes}
    incoming = {}
    for edge in edges:
        if edge["kind"] in ("sequence", "prerequisite"):
            incoming.setdefault(edge["target"], []).append(edge["source"])
    for node in nodes:
        if node["kind"] == "subject":
            continue
        required = incoming.get(node["id"], [])
        subject_node = by_id[f"subject:{_slug(node['subject'])}"]
        node["available"] = node["opened"] or (
            subject_node["opened"] and all(by_id[parent]["opened"] for parent in required)
        )

    return {
        "major": major,
        "years": [10, 11, 12],
        "nodes": nodes,
        "edges": edges,
        "legend": {
            "importance": "حاشیه و اندازه گره = اهمیت مبحث",
            "mastery": "رنگ گره بازشده = دقت پاسخ‌های ثبت‌شده",
            "locked": "گره خاکستری = هنوز مطالعه یا داده‌ای ثبت نشده",
        },
    }
