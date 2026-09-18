import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Create a mock json file for testing the frontend integration
data = [
    { "subject": "ریاضی", "source": "کتاب خیلی سبز ۱.ن فی �^ �.����", "read": 65, "total": 100, "testsLeft": 42 },
    { "subject": "فیزیک", "source": "کتاب خیلی سبز ������ ������", "read": 30, "total": 100, "testsLeft": 85 },
    { "subject": "شیمی", "source": "کتاب خیلی سبز ������", "read": 80, "total": 100, "testsLeft": 20 }
]

output_dir = Path(__file__).resolve().parent / "backend" / "data"
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / "mock_subjects_progress.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")