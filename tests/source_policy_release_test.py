from datetime import date
from types import SimpleNamespace
import pytest


def test_production_switch_preserves_existing_maze_extractor(monkeypatch):
    from app.routers import boom_ai
    from app import config
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(SOURCE_POLICY_ENABLED=False))
    calls=[]
    monkeypatch.setattr(boom_ai,'_extract_week_mock_legacy_candidates',lambda *args:calls.append(args) or {'summary':'existing scope'})
    assert boom_ai._extract_week_mock(7,date(2026,11,1),2)=={'summary':'existing scope'}
    assert calls==[(7,date(2026,11,1),2)]


@pytest.mark.parametrize('enabled,expected',[(False,1),(True,0)])
def test_image_hash_enforcement_is_explicitly_gated(monkeypatch,enabled,expected):
    from app.rag import pipeline
    from app.utils import storage
    monkeypatch.setattr(pipeline,'get_settings',lambda:SimpleNamespace(SOURCE_POLICY_ENABLED=enabled))
    monkeypatch.setattr(storage,'get_object',lambda key:b'synthetic image bytes')
    hits,images=pipeline._load_page_images([{'content':'synthetic.png'}])
    assert len(hits)==len(images)==expected
