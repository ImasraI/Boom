import pytest
from app.rag.chunking import chunk_text,_split_into_sentences

def test_abbreviation_numbered_item_decimal_and_persian_boundary():
    assert _split_into_sentences('Dr. Smith used 3.14. Next? Yes.')==['Dr. Smith used 3.14.','Next?','Yes.']
    assert _split_into_sentences('1. Solve this. 2. Continue.')==['1. Solve this.','2. Continue.']
    assert _split_into_sentences('اول؟ دوم۔ سوم!')==['اول؟','دوم۔','سوم!']

def test_limits_and_whole_sentence_overlap_preserve_new_content():
    text='Alpha one. Beta two. Gamma three. Delta four.'
    chunks=chunk_text(text,25,12)
    assert all(len(x)<=25 for x in chunks)
    assert all(sentence in '\n'.join(chunks) for sentence in _split_into_sentences(text))
    assert all(not c.startswith('ha ') for c in chunks)

def test_formula_with_punctuation_and_spaces_stays_intact():
    formula=r'$f(x) = 1. x + 2$'
    chunks=chunk_text('Before. '+formula+' End. '+('more '*15),40,8)
    assert any(formula in c for c in chunks)
    assert all(len(c)<=40 for c in chunks)
    display='$$a + b\n\n= c$$'
    assert any(display in c for c in chunk_text('Before.\n\n'+display+'\n\nAfter.',40,8))

def test_long_sentence_and_invalid_configuration():
    chunks=chunk_text('word '*100,30,8)
    assert all(len(c)<=30 for c in chunks)
    with pytest.raises(ValueError):chunk_text('a',10,10)
    with pytest.raises(ValueError):chunk_text('$'+'x '*30+'$',20,0)
