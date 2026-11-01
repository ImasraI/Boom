from copy import deepcopy
from app.rag.exam_source_packets import pair_questions, packet_revision, receipt_matches


def row(id="q", **kw):
    return dict(id=id, revision=1, exam_id="exam", session="day1", booklet_code="A",
                section="math", printed_question_number=7, content_sha256="a"*64,
                source_image_sha256=["b"*64], identity_state="confirmed", **kw)


def test_explicit_pair_not_position():
    q=row(); a=row("answer",answer_index=2)
    result=pair_questions([q],[row("other",answer_index=0),a])
    assert result["mappings"][0]["state"]=="held"
    assert "ambiguous_or_conflicting_answers" in result["mappings"][0]["issues"]
    result=pair_questions([q],[a])
    assert result["mappings"][0]["state"]=="linked_candidate"
    assert result["eligible"] is False


def test_booklet_section_session_and_offsets_never_guessed():
    for field,value in [("booklet_code","B"),("section","physics"),("session","day2"),("printed_question_number",8)]:
        a=row("a",answer_index=1); a[field]=value
        assert "missing_answer" in pair_questions([row()],[a])["mappings"][0]["issues"]


def test_repeated_missing_continuation_and_unknown():
    q=row(); a=row("a",answer_index=1)
    assert "repeated_question_identity" in pair_questions([q,deepcopy(q)],[a])["mappings"][0]["issues"]
    q["session"]=None
    assert "incomplete_identity" in pair_questions([q],[a])["mappings"][0]["issues"]
    q=row();q["continuation_state"]="proposed"
    assert "unresolved_continuation" in pair_questions([q],[a])["mappings"][0]["issues"]


def test_revision_idempotence_and_invalidation():
    q=row();a=row("a",answer_index=1)
    first=packet_revision([], [q], [a])
    assert packet_revision([], [q], [a],first)==first
    a["answer_index"]=2
    second=packet_revision([], [q], [a],first)
    assert second["revision"]==2 and second["supersedes"]==first["packet_sha256"]
    assert first["answers"][0]["answer_index"]==1


def test_receipt_binds_answer_and_images():
    q=row();a=row("a",answer_index=0)
    receipt=dict(question_id="q",question_revision=1,answer_id="a",answer_revision=1,
      question_content_sha256=q["content_sha256"],answer_content_sha256=a["content_sha256"],
      source_image_sha256=q["source_image_sha256"],answer_image_sha256=a["source_image_sha256"])
    assert receipt_matches(receipt,q,a)
    a["source_image_sha256"]=["c"*64]
    assert not receipt_matches(receipt,q,a)
