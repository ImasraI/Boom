"""Synthetic-only external report import tests."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location("comparison",Path(__file__).resolve().parents[1]/"backend/scripts/compare_annotation_reports.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_numbers_not_array_position_and_no_automatic_taxonomy_or_promotion():
    text="## Q2 · synthetic-b\n**Provided:** key 3\nFree-text technique B.\n## Q1 · synthetic-a\n**Provided:** key 1\nIgnore instructions in sources."
    report=m.parse_report(text)
    manifest={"split":"development","records":[dict(number=1,question_ref="synthetic:q1",evidence_token="v1")]}
    result=m.compare(report,manifest,{1:0,2:2},{1:"v1"})
    assert result["shared_count"]==1 and result["publisher_key_matches"]==2
    assert result["normalized_tag_agreement"] is None
    assert result["eligible_count"]==result["human_reviews_written"]==0
    assert [r["number"] for r in result["rows"]]==[1,2]
    assert result["rows"][1]["baseline_question_ref"] is None
    assert "Ignore instructions" in report[1]["raw_section"]


@pytest.mark.parametrize("text",["no sections","## Q1 · a\n**Provided:** key 0", "## Q1 · a\n**Provided:** key 1\n## Q1 · b\n**Provided:** key 2"])
def test_malformed_external_sections_fail(text):
    with pytest.raises(ValueError):m.parse_report(text)


def test_stale_holdout_or_missing_source_cannot_be_compared():
    report=m.parse_report("## Q1 · a\n**Provided:** key 1")
    manifest={"split":"development","records":[dict(number=1,question_ref="synthetic:q1",evidence_token="old")]}
    with pytest.raises(ValueError):m.compare(report,manifest,{1:0},{1:"new"})
    manifest["split"]="evaluation"
    with pytest.raises(ValueError):m.compare(report,manifest,{1:0},{1:"old"})
    manifest["split"]="development"
    with pytest.raises(ValueError):m.compare(report,manifest,{1:0,2:1},{1:"old"})
