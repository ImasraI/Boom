"""Tests for the trace's 2-D embedding map (app/rag/embedding_map.py).

The map is only worth drawing if its claim survives checking: the chunk
positions really are the principal plane of the retrieved vectors, and the query
marker really is where the recorded cosine similarities put it. These tests
reconstruct both from an independent eigendecomposition (a different path from
the SVD the module uses) and compare, so a sign, transpose or projection mistake
fails here instead of shipping a plausible-looking picture.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.rag import embedding_map as em  # noqa: E402


def _unit(matrix):
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def _plane(vectors, dimensions=2):
    """Principal directions in embedding space, by eigendecomposition.

    Deliberately not the module's SVD: an independent route to the same plane.
    A principal direction is only defined up to sign, so callers align signs.
    """
    matrix = _unit(np.asarray(vectors, dtype=float))
    mean = matrix.mean(axis=0)
    centred = matrix - mean
    values, directions = np.linalg.eigh(centred.T @ centred)
    picked = np.argsort(values)[::-1][:dimensions]
    return centred, mean, directions[:, picked]


def _align(actual, expected):
    """Flip each axis to match, since an eigenvector's sign is arbitrary."""
    actual = np.asarray(actual, dtype=float)
    expected = np.asarray(expected, dtype=float)
    sign = np.where(np.sum(actual * expected, axis=0) < 0, -1.0, 1.0)
    return expected * sign


def test_chunk_plane_and_query_marker_match_an_independent_decomposition():
    rng = np.random.default_rng(20261015)
    candidates = _unit(rng.normal(size=(7, 24)))
    query = rng.normal(size=24)
    similarities = candidates @ (query / np.linalg.norm(query))

    geometry = em.project_vectors(candidates, similarities)
    centred, mean, direction = _plane(candidates)
    query_hat = query / np.linalg.norm(query)

    assert geometry is not None
    assert geometry["dimensions"] == 24
    assert np.allclose(geometry["coordinates"], _align(geometry["coordinates"], centred @ direction), atol=1e-3)
    assert np.allclose([geometry["query"]], _align([geometry["query"]],
                                                   [direction.T @ (query_hat - mean)]), atol=1e-3)
    assert sum(geometry["explained_variance_ratio"]) <= 1.0 + 1e-9


def test_the_recorded_similarities_are_what_place_the_query():
    """Two different queries over the same candidates must not land alike."""
    rng = np.random.default_rng(7)
    candidates = _unit(rng.normal(size=(6, 16)))
    first, second = rng.normal(size=16), rng.normal(size=16)
    near = em.project_vectors(candidates, candidates @ (first / np.linalg.norm(first)))
    far = em.project_vectors(candidates, candidates @ (second / np.linalg.norm(second)))
    centred, mean, direction = _plane(candidates)

    assert near is not None and far is not None
    assert not np.allclose(near["query"], far["query"], atol=1e-3)
    for record, query in ((near, first), (far, second)):
        expected = direction.T @ (query / np.linalg.norm(query) - mean)
        assert np.allclose([record["query"]], _align([record["query"]], [expected]), atol=1e-3)
    assert np.allclose([near["query"]], _align([near["query"]],
                                               [direction.T @ (first / np.linalg.norm(first) - mean)]), atol=1e-3)
    assert np.allclose(near["coordinates"], _align(near["coordinates"], centred @ direction), atol=1e-3)


def test_a_rank_one_cloud_keeps_the_query_on_its_line():
    """No second direction exists, so nothing may be drawn along one."""
    # Unit vectors that are centred onto a single line: distinct rows, one
    # direction. A collinear set through the origin would just be one vector
    # repeated, which the module refuses as having nothing to spread out.
    candidates = np.array([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]])
    query = np.array([0.3, 0.1, 0.0])
    similarities = candidates @ (query / np.linalg.norm(query))

    geometry = em.project_vectors(candidates, similarities)
    centred, mean, direction = _plane(candidates)

    assert geometry is not None
    assert geometry["components"] == 2
    # The second axis carries no variance and must not borrow any.
    assert geometry["explained_variance_ratio"][1] == pytest.approx(0.0, abs=1e-6)
    assert all(abs(point[1]) < 1e-6 for point in geometry["coordinates"])
    # The query projects onto the span, so it stays on that same line.
    assert geometry["query"][1] == pytest.approx(0.0, abs=1e-4)
    expected = (centred @ direction)[:, 0]
    actual = [point[0] for point in geometry["coordinates"]]
    assert np.allclose(actual, _align(actual, expected), atol=1e-3)


def test_no_plane_is_claimed_without_enough_or_distinct_vectors():
    assert em.project_vectors([[1.0, 0.0], [0.0, 1.0]], [0.5, 0.5]) is None
    assert em.project_vectors([], []) is None
    same = [[1.0, 0.0, 0.0]] * 4
    assert em.project_vectors(same, [1.0, 1.0, 1.0, 1.0]) is None
    # A stored zero vector has no direction to normalise.
    assert em.project_vectors([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], [0.0, 0.5, 0.5]) is None
    # One similarity per candidate, and all of them real numbers.
    assert em.project_vectors([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], [0.5, 0.5]) is None
    assert em.project_vectors([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], [0.5, float("nan"), 0.5]) is None


def test_only_candidates_with_a_stored_vector_and_a_score_are_drawn():
    rows = [
        {"id": "a", "rank": 1, "score": 0.9, "doc": "book.pdf", "chunk": 1, "preview": "one"},
        {"id": "b", "rank": 2, "score": 0.8, "doc": "book.pdf", "chunk": 2, "preview": "two"},
        {"id": "c", "rank": 3, "score": 0.7, "doc": "book.pdf", "chunk": 3, "preview": "three"},
        {"id": "gone", "rank": 4, "score": 0.6, "doc": "book.pdf", "chunk": 4, "preview": ""},
        {"id": "d", "rank": 5, "score": "not recorded", "doc": "book.pdf", "chunk": 5, "preview": ""},
        {"rank": 6, "score": 0.5},
    ]
    vectors = {"a": [1.0, 0.0, 0.0], "b": [0.9, 0.2, 0.0], "c": [0.8, 0.0, 0.3],
               "d": [0.7, 0.3, 0.2]}
    built = em.build_map("books · semantic_search", "books-demo", rows, vectors)

    assert built is not None
    assert built["point_count"] == 3
    assert built["recorded_rows"] == 6
    # A chunk whose vector is gone is a different fact from one never scored,
    # and a row without an id is neither.
    assert built["missing_vectors"] == 1
    assert built["unscored_rows"] == 1
    assert [point["id"] for point in built["points"]] == ["a", "b", "c"]
    assert built["points"][0]["score"] == 0.9
    assert built["metric"] == "cosine"
    assert built["shelf"] == "books"
    two = rows[:2]
    assert em.build_map("books · semantic_search", "books-demo", two,
                        {row["id"]: vectors[row["id"]] for row in two}) is None


def test_semantic_rows_are_grouped_per_collection_keeping_the_best_rank():
    def stage(name, collection, rows):
        return {"name": name, "meta": {"collection": collection}, "rows": rows}

    def row(chunk_id, rank, score=0.5):
        return {"id": chunk_id, "rank": rank, "score": score, "doc": "d", "chunk": 0}

    groups = em.semantic_groups([
        stage("embed_query", "ignored", [row("x", 1)]),
        stage("books · semantic_search", "books", [row("a", 3), row("b", 1)]),
        stage("books rerank", "books", [row("c", 1)]),
        # The same collection searched twice: one map, best rank per chunk.
        stage("books · semantic_search", "books", [row("a", 1), row("c", 2)]),
        stage("qbank · semantic_search", "questions", [row("q", 1)]),
    ])

    assert [group["collection"] for group in groups] == ["books", "questions"]
    books = groups[0]["rows"]
    assert [item["id"] for item in books] == ["a", "b", "c"]
    assert next(item for item in books if item["id"] == "a")["rank"] == 1


def test_each_collection_gets_its_own_map_and_missing_vectors_are_explained():
    stages = [{"name": "books · semantic_search", "meta": {"collection": "books"},
               "rows": [{"id": f"b{i}", "rank": i, "score": 0.9 - i / 10, "doc": "d", "chunk": i}
                        for i in range(1, 5)]},
              {"name": "qbank · semantic_search", "meta": {"collection": "questions"},
               "rows": [{"id": f"q{i}", "rank": i, "score": 0.5, "doc": "d", "chunk": i}
                        for i in range(1, 4)]}]
    stored = {f"b{i}": [1.0, i / 10, 0.0] for i in range(1, 5)}
    seen = []

    def fetch(collection, ids):
        seen.append(collection)
        return stored if collection == "books" else {}

    built = em.build_embedding_maps({"id": "t1", "stages": stages}, fetch=fetch)

    assert seen == ["books", "questions"]
    assert [record["collection"] for record in built["maps"]] == ["books"]
    assert built["maps"][0]["shelf"] == "books"
    assert built["maps"][0]["shelf_label"] == em.SHELF_LABELS["books"]
    assert built["skipped"][0]["collection"] == "questions"
    assert "بردار" in built["skipped"][0]["reason"]
    assert built["trace_id"] == "t1"
    assert built["limitations"] and built["notice"]


def test_a_broken_store_cannot_break_the_panel_and_missing_search_is_explained():
    def explode(collection, ids):
        raise RuntimeError("chroma is on fire")

    rows = [{"id": f"b{i}", "rank": i, "score": 0.5, "doc": "d", "chunk": i} for i in range(4)]
    built = em.build_embedding_maps(
        {"id": "t2", "stages": [{"name": "books · semantic_search",
                                 "meta": {"collection": "books"}, "rows": rows}]},
        fetch=explode)
    assert built["maps"] == [] and built["skipped"][0]["found_vectors"] == 0

    empty = em.build_embedding_maps({"id": "t3", "stages": [
        {"name": "embed_query", "meta": {}, "rows": []},
        {"name": "retrieval_assembly", "meta": {}, "rows": []}]})
    assert empty["maps"] == [] and empty["skipped"] == []
    assert "کسینوسی" in empty["reason"]


def test_the_map_endpoint_is_read_only_and_scoped_to_one_trace():
    """The router's admin gate is asserted in rag_trace_test; this pins the map's own shape."""
    from app.routers.rag_trace import router

    route = next(item for item in router.routes
                 if getattr(item, "path", "").endswith("/embedding-map"))
    assert route.path == "/api/admin/rag/traces/{trace_id}/embedding-map"
    assert set(route.methods) == {"GET"}
