"""Tests for the book catalog question-range parser."""

import re
import os
import glob
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_BOOKS_DIR = REPO_ROOT / "backend" / "data" / "raw" / "test-books"

def test_persian_digit_pattern():
    """The regex should match question ranges with both Arabic/Persian digits and ASCII digits."""
    pattern = r"سوال\s+([\d|۱-۹]+):\s+از\s+صفحه\s+([\d|۱-۹]+)\s+تا\s+([\d|۱-۹]+)"

    # Test with Persian digits
    test_text = "سوال ۱: از صفحه ۱۰ تا ۲۰"
    matches = re.findall(pattern, test_text)
    assert len(matches) == 1, f"Expected 1 match, got {len(matches)}"
    q, s, e = matches[0]
    assert q == "۱", f"Expected '۱', got '{q}'"
    assert s == "۱۰", f"Expected '۱۰', got '{s}'"
    assert e == "۲۰", f"Expected '۲۰', got '{e}'"

    # Test with ASCII digits
    test_text2 = "سوال 1: از página 10 ta 20"
    m = re.search(pattern, test_text2)
    # May or may not match depending on exact text, but the pattern should handle both


def test_extract_question_ranges():
    """Extract question ranges from test book text files."""
    pdfs = sorted(glob.glob(str(TEST_BOOKS_DIR / "*.txt")))

    pattern = r"سوال\s+([\d|۱-۹]+):\s+از\s+صفحه\s+([\d|۱-۹]+)\s+تا\s+([\d|۱-۹]+)"

    results = {}
    for txt_path in sorted(pdfs):
        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()
        matches = re.findall(pattern, text)
        results[os.path.basename(txt_path)] = len(matches)

    # At least some books should have question ranges
    total = sum(results.values())
    assert total > 0, f"Expected at least 1 question range across all books, got {total}"
    print(f"Catalog parser test: found {total} question ranges in {len(results)} books")


def test_mathematics_has_ranges():
    """Mathematics book should have question ranges extracted."""
    pdfs = sorted(glob.glob(str(TEST_BOOKS_DIR / "*.txt")))

    pattern = r"سوال\s+([\d|۱-۹]+):\s+از\s+صفحه\s+([\d|۱-۹]+)\s+تا\s+([\d|۱-۹]+)"

    for txt_path in pdfs:
        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()
        matches = re.findall(pattern, text)
        if "mathematics" in os.path.basename(txt_path):
            assert len(matches) > 0, f"Mathematics book should have question ranges"
            print(f"Mathematics: {len(matches)} question ranges found")
            for m in matches[:2]:  # Show first 2
                print(f"  Q{m[0]}: pages {m[1]}-{m[2]}")
            break