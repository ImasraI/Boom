"""Deterministic paragraph/sentence chunking with whole-unit overlap.

Sizes are characters, not model tokens. Structured questions use their own
parent records; this splitter must never be used to separate question options.
"""
import re
from typing import List

VERSION = 'paragraph-sentence-v2'
_MATH = re.compile(r'\$\$[\s\S]*?\$\$|(?<!\\)\$[^$\n]+?\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)')
_ABBREVIATIONS = {'dr','mr','mrs','ms','prof','etc','eg','ie','e.g','i.e','vs','fig','no','pp','vol'}


def _split_into_sentences(text: str) -> List[str]:
    # Mask protected spans at the same offsets; slice only the original text.
    masked=list(text)
    for match in _MATH.finditer(text):
        masked[match.start():match.end()]='x'*(match.end()-match.start())
    masked=''.join(masked)
    starts=0;result=[]
    for match in re.finditer(r'(?<=[.!?؟۔])\s+',masked):
        end=match.start();prefix=masked[:end]
        if prefix.endswith('.'):
            word=re.search(r'([\w.]+)\.$',prefix)
            value=word.group(1) if word else ''
            # Decimal dots followed by digits have no whitespace and never match.
            if value.lower() in _ABBREVIATIONS or value.isdigit() or re.fullmatch(r'[A-Z]',value):continue
        unit=text[starts:end].strip()
        if unit:result.append(unit)
        starts=match.end()
    tail=text[starts:].strip()
    if tail:result.append(tail)
    return result


def _bounded_units(unit,size):
    if len(unit)<=size:return [unit]
    pieces=[];current=''
    # Equations remain atomic even when they contain spaces and punctuation.
    pattern=re.compile('('+_MATH.pattern+r')|\S+')
    for match in pattern.finditer(unit):
        token=match.group()
        if len(token)>size:
            if _MATH.fullmatch(token):
                raise ValueError('An equation exceeds the chunk limit; retain it as a linked parent record')
            tokens=[token[i:i+size] for i in range(0,len(token),size)]
        else:tokens=[token]
        for token in tokens:
            candidate=(current+' '+token).strip()
            if len(candidate)>size:
                if current:pieces.append(current)
                current=token
            else:current=candidate
    if current:pieces.append(current)
    return pieces


def chunk_text(text: str,chunk_size: int=800,chunk_overlap: int=150) -> List[str]:
    if type(chunk_size) is not int or chunk_size<1:raise ValueError('chunk_size must be positive')
    if type(chunk_overlap) is not int or not 0<=chunk_overlap<chunk_size:
        raise ValueError('chunk_overlap must be nonnegative and smaller than chunk_size')
    text=text.strip();masked=list(text)
    for match in _MATH.finditer(text):
        masked[match.start():match.end()]='x'*(match.end()-match.start())
    breaks=list(re.finditer(r'\n\s*\n',''.join(masked)))
    paragraphs=[];start=0
    for boundary in breaks:
        if text[start:boundary.start()].strip():paragraphs.append(text[start:boundary.start()].strip())
        start=boundary.end()
    if text[start:].strip():paragraphs.append(text[start:].strip())
    chunks=[];current=[]
    for paragraph in paragraphs:
        for sentence in _split_into_sentences(paragraph):
            for unit in _bounded_units(sentence,chunk_size):
                candidate='\n'.join([*current,unit])
                if len(candidate)<=chunk_size:current.append(unit);continue
                if current:chunks.append('\n'.join(current))
                overlap=[]
                for previous in reversed(current):
                    if len('\n'.join([previous,*overlap]))>chunk_overlap:break
                    if len('\n'.join([previous,*overlap,unit]))>chunk_size:break
                    overlap.insert(0,previous)
                current=[*overlap,unit]
    if current:chunks.append('\n'.join(current))
    return chunks
