import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location("maze_packet",Path(__file__).parents[1]/"backend/scripts/prepare_maze_source_packet.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def pages(numbers):
    text="".join(str(n)+"\n- stem\n" for n in numbers)
    return {2:(text,[(0,len(text),(0,20,100,30))])}

def test_complete_printed_sequence_and_inline_decoys():
    result=m.find_headers(pages([*range(1,51),1,2,*range(51,106)]),2,2)
    assert [r[0] for r in result]==list(range(1,106))

def test_missing_printed_number_is_not_offset_repaired():
    with pytest.raises(ValueError):m.find_headers(pages([1,2,4]),2,2)

def test_reordered_sequence_cannot_be_silently_zipped():
    with pytest.raises(ValueError):m.find_headers(pages([2,1,*range(3,106)]),2,2)

def test_unknown_pdf_profile_refused(tmp_path):
    source=tmp_path/"book.pdf";source.write_bytes(b"different PDF")
    with pytest.raises(ValueError,match="exact H0"):m.prepare(source,tmp_path)
