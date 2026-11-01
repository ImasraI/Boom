import json
import pytest
from app.rag.model_spec_adapter import build_checked_variant


def test_supported_spec_gets_constructor_answer_without_originality_claim():
    result=build_checked_variant(json.dumps({'family':'absolute_line_intersections','params':{'a':3,'b':8}}))
    assert result['candidate']['stem']
    assert result['design_class']=='supported_practice_variant'
    assert result['eligible'] is False and result['originality_approved'] is False


@pytest.mark.parametrize('raw',[
    '{"family":"coupled_grid_count","family":"ordered_cubic_roots","params":{}}',
    '{"family":"coupled_grid_count","params":{},"answer_index":0}',
    '{"family":"unknown","params":{}}',
    '{"family":"absolute_line_intersections","params":{"a":true,"b":7}}',
    '{"family":"coupled_grid_count","params":{"code":"print(1)"}}',
    '[]', 'x'*16001,
])
def test_unsafe_unsupported_or_answer_bearing_specs_are_rejected(raw):
    with pytest.raises((ValueError,TypeError)):
        build_checked_variant(raw)
