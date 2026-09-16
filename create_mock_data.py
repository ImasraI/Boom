import json
from pathlib import Path

# Create a mock json file for testing the frontend integration
data = [
    { "subject": "حسابان", "source": "کتاب تست مهر و ماه", "read": 65, "total": 100, "testsLeft": 42 },
    { "subject": "فیزیک", "source": "کتاب تست خیلی سبز", "read": 30, "total": 100, "testsLeft": 85 },
    { "subject": "شیمی", "source": "کتاب تست مبتکران", "read": 80, "total": 100, "testsLeft": 20 }
]

output_dir = Path("C:/Users/Arsam/Desktop/Boom-merged/backend/data")
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / "mock_subjects_progress.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
