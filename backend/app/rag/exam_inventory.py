"""Repeatable local-only PDF discovery, archive inspection and content deduplication."""
from pathlib import Path
import shutil
import subprocess

from app.rag.exam_corpus import atomic_json, digest, safe_path


def _archive_members(listing: bytes, destination: Path):
    """Validate types and paths before UnRAR can create links or special files."""
    try:text=listing.decode('utf-8')
    except UnicodeError:text=listing.decode('cp1256')
    entries=[];entry=None
    for line in text.splitlines():
        field,separator,value=line.strip().partition(':')
        if not separator:continue
        if field=='Name':
            entry={'Name':value.strip()};entries.append(entry)
        elif entry is not None:
            entry[field]=value.strip()
    if not entries:raise ValueError('Archive listing has no inspectable members')
    seen=set();pdfs=[]
    for entry in entries:
        name=entry['Name'];kind=entry.get('Type','').casefold()
        if kind not in ('file','directory'):raise ValueError('Archive contains a link or special member')
        if any(any(word in (key+' '+value).casefold() for word in ('link','target','redir','reparse'))
               for key,value in entry.items() if key not in ('Name','Host OS')):
            raise ValueError('Archive contains a link or reparse member')
        attributes=entry.get('Attributes','')
        if entry.get('Host OS','').casefold()=='unix' and attributes and attributes[0] not in ('-','d','.'):
            raise ValueError('Archive contains a special Unix member')
        safe_path(destination,name)
        normalized=name.replace('\\','/').rstrip('/').casefold()
        if normalized in seen:raise ValueError('Archive contains colliding member paths')
        seen.add(normalized)
        if kind=='file' and name.lower().endswith('.pdf'):pdfs.append(name)
    if not pdfs:raise ValueError('Archive contains no PDFs')
    return pdfs


def _no_links(path: Path, parent: Path):
    # resolve() alone conceals a link; inspect each existing component first.
    current=path
    while current!=parent.parent:
        if current.is_symlink() or (hasattr(current,'is_junction') and current.is_junction()):
            raise ValueError('Archive extraction target contains a link or junction')
        if current==parent:break
        current=current.parent


def inventory(project: Path, root: Path, *, extractor=None):
    import pymupdf
    source=project/'mocks'
    if not source.is_dir():raise ValueError('Expected root mocks/ directory')
    extractor=extractor or shutil.which('unrar') or 'C:/Program Files/WinRAR/UnRAR.exe'
    archives=[];paths=list(source.glob('*.pdf'))
    for archive in sorted(source.glob('*.rar')):
        sha=digest(archive);destination=root/'archives'/sha
        _no_links(destination,root)
        listing=subprocess.run([str(extractor),'lt','-p-','-c-','-cfg-',str(archive)],capture_output=True,check=True).stdout
        members=_archive_members(listing,destination)
        for member in members:_no_links(destination/member.replace('\\','/'),root)
        destination.mkdir(parents=True,exist_ok=True)
        result=subprocess.run([str(extractor),'x','-p-','-c-','-cfg-','-ai','-o-','-y',str(archive),'*.pdf',str(destination)+'/',],capture_output=True)
        if result.returncode not in (0,1):raise RuntimeError('Archive extraction failed')
        actual=[safe_path(destination,n) for n in members]
        if any(not p.is_file() or p.is_symlink() for p in actual):raise ValueError('Archive extraction incomplete or unsafe')
        paths.extend(actual)
        archives.append({'source':str(archive.relative_to(project)),'sha256':sha,'pdfs':len(actual),
                         'extracted_to':str(destination.relative_to(project))})
    documents=[];seen={}
    for path in sorted(paths):
        sha=digest(path)
        if sha in seen:
            seen[sha]['aliases'].append(str(path.relative_to(project)));continue
        with pymupdf.open(path) as pdf:
            if not pdf.page_count or pdf.needs_pass:raise ValueError('Empty or encrypted source PDF')
            sample=sorted({0,min(2,pdf.page_count-1),pdf.page_count//2,pdf.page_count-1})
            row={'document_id':sha,'path':str(path.relative_to(project)),'name':path.name,'pages':pdf.page_count,
                 'bytes':path.stat().st_size,'sample_native_chars':{str(i+1):len(pdf[i].get_text()) for i in sample},'aliases':[]}
        documents.append(row);seen[sha]=row
    result={'schema_version':1,'archives':archives,'documents':documents,'duplicates':len(paths)-len(documents)}
    atomic_json(root/'inventory.json',result)
    return {'unique_pdfs':len(documents),'duplicate_pdfs':result['duplicates'],'total_pages':sum(d['pages'] for d in documents)}
