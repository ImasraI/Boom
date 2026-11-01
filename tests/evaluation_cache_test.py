import pytest
from app.rag.evaluation_cache import EvaluationCache


def test_vectors_are_bound_to_model_dimensions_text_and_task(tmp_path):
    path = tmp_path / 'cache.json'
    cache = EvaluationCache(path, 'model-a', 2)
    cache.put('question', 'query', [1.0, 2.0])
    assert EvaluationCache(path, 'model-a', 2).get('question', 'query') == [1.0, 2.0]
    assert cache.get('question', 'document') is None
    assert cache.get('different', 'query') is None
    assert EvaluationCache(path, 'model-b', 2).get('question', 'query') is None
    assert EvaluationCache(path, 'model-a', 3).get('question', 'query') is None


@pytest.mark.parametrize('vector', [[float('nan'), 1], [float('inf'), 1], [0, 0], [1], [True, 1]])
def test_invalid_vectors_never_persist(tmp_path, vector):
    cache = EvaluationCache(tmp_path / 'cache.json', 'model', 2)
    with pytest.raises(ValueError):
        cache.put('query', 'query', vector)


def test_corrupt_cache_does_not_prevent_a_fresh_evaluation(tmp_path):
    path = tmp_path / 'cache.json'
    path.write_text('[]')
    cache = EvaluationCache(path, 'model', 2)
    assert cache.get('query', 'query') is None
    cache.put('query', 'query', [1, 2])
    assert cache.get('query', 'query') == [1, 2]
