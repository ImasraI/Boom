"""Freeze a local, factual-page-backed six-mechanism pilot. No provider calls."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest,atomic_json
from app.rag.pedagogical_authoring import prompt_for,VERSION

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'backend/data/authoring_work/pedagogical-geometry-v2'
BOOK='هندسه 2 خیلی سبز.pdf'
SPECS=[
 ('circle_power','lesson:754cc2e1bfaaad930c',BOOK,29,28,
  'Link two secants or a secant/tangent relation with a meaningful admissibility or point-order decision. Do not just plug three numbers into a product formula.',
  ['For two secants from an exterior point P, PA*PB=PC*PD, where A,C are nearer intersections.',
   'For a tangent PT, PT^2=PA*PB. Segment lengths are positive and nearer intersections precede farther ones.']),
 ('cyclic_constraints','lesson:b7777c00c62623d944',BOOK,51,50,
  'Determine a feasible geometric configuration or parameter by combining cyclic-quadrilateral angles with an independent constraint. Do not merely ask for 180 minus one angle.',
  ['Opposite angles of a convex cyclic quadrilateral sum to 180 degrees.',
   'A cyclic trapezoid must be isosceles; a cyclic parallelogram must be a rectangle.']),
 ('reflection_isometry','lesson:14ba762d495f4f3090',BOOK,102,101,
  'Use reflection to reveal a distance invariant or recover a configuration; a coordinate computation alone is not the teaching insight. Do not copy the circle-common-tangent or one reflected-segment area examples.',
  ['Reflection in a line preserves distances and fixes points on the line.',
   'The reflecting line bisects the angle between a line and its reflected image when they intersect.']),
 ('cosine_feasibility','lesson:45ef1d28b925a5963f',BOOK,157,156,
  'Use the cosine law with triangle feasibility to distinguish admissible angle/length configurations. Avoid asking only for the third side after a direct substitution.',
  ['In a triangle with a opposite angle A, a^2=b^2+c^2-2bc*cos(A).',
   'Triangle side lengths are positive and satisfy the strict triangle inequalities.']),
 ('heron_area','lesson:9a2b821293b055f147',BOOK,173,172,
  'Combine area feasibility or an extremal/threshold question with Heron and a justified domain. Explain the factorization or inequality rather than listing every candidate.',
  ['With s=(a+b+c)/2, triangle area is sqrt(s*(s-a)*(s-b)*(s-c)).',
   'For a nondegenerate triangle, side lengths obey strict triangle inequalities and area is positive.']),
 ('altitude_admissibility','lesson:18bbe1b38369251e94','هندسه 1 خیلی سبز.pdf',137,136,
  'Recover a feasible altitude relationship or parameter from the common-area relation and triangle inequalities. Do not use parallel sections or the classic intersecting-cevian given-area diagram.',
  ['For triangle area K and side a with altitude h_a, a=2K/h_a.',
   'The positive numbers 1/h_a,1/h_b,1/h_c satisfy the strict triangle inequalities.'])]


def prepare():
    catalog_path=ROOT/'backend/data/knowledge_graph/catalog.json'
    catalog=json.loads(catalog_path.read_text(encoding='utf8'));nodes={n['id']:n for n in catalog['nodes']}
    drafts=[];evidence=[]
    for mechanism,knowledge_id,book,page,printed,target,facts in SPECS:
        node=nodes.get(knowledge_id)
        if not node or not node.get('sources') or 'riazi' not in node.get('majors',[]):raise ValueError('Missing book-backed math node')
        if not any(s.get('book')==book.removesuffix('.pdf') for s in node['sources']):raise ValueError('Catalogue source differs')
        image=ROOT/'backend/data/1'/book/f'page_{page:04d}.png'
        ocr=ROOT/'backend/data/ocr'/book/f'page_{page:04d}.txt'
        for path in (image,ocr):
            if not path.is_file():raise ValueError('Missing factual evidence')
        spec={'id':mechanism,'knowledge_ids':[knowledge_id],'major':'riazi','target_grade':12,
              'scope':'Provided grade10/11 math-physics geometry test-book facts; local research only',
              'task':target,'facts':facts,'primary_mechanism':mechanism,
              'avoid_primary_mechanism':'parallel-section Thales/similarity chain'}
        # Triangle inequalities were visually checked on the area page too.
        dependencies=[{'book':'هندسه 1 خیلی سبز.pdf','page':137,'printed_page':136}]
        evidence.append({'spec_id':mechanism,'catalogue_node':knowledge_id,'catalogue_title':node['title'],
          'image_ref':image.relative_to(ROOT/'backend/data').as_posix(),'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
          'ocr_ref':ocr.relative_to(ROOT/'backend/data').as_posix(),'ocr_sha256':hashlib.sha256(ocr.read_bytes()).hexdigest(),
          'physical_page_1based':page,'printed_page':printed,'cross_fact_dependencies':dependencies,
          'check_kind':'assistant_visual_page_check','checked_on':'2026-10-30','human_review':False,
          'production_source_eligibility':False,'raw_page_or_example_sent_to_model':False})
        prompt=prompt_for(spec)
        drafts.append({'spec':spec,'prompt':prompt,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
    manifest={'schema_version':'0.1','prompt_version':VERSION,'provider':'gemini','model':'gemini-3.6-flash',
      'temperature':0.2,'reasoning_effort':'high','completion_tokens':16384,'timeout_seconds':180,
      'catalogue_sha256':hashlib.sha256(catalog_path.read_bytes()).hexdigest(),'planned_items':6,
      'evidence':evidence,'drafts':drafts,'released':False,'human_approved':False,
      'scope_limitations':['Convenience geometry pilot, not full Konkur coverage or a randomized estimate.',
        'Not an extension of the original paired experiment; no arm-superiority claim.',
        'Facts checked by assistant against test-book page images, not formal human scientific receipts.',
        'No source exam literals, held-out papers or source answer keys are provided to the author.',
        'Proposed technique labels require independent semantic review; JSON validation is insufficient.']}
    OUT.mkdir(exist_ok=True);digest=payload_digest(manifest);path=OUT/('protocol-'+digest+'.json')
    if (OUT/'pointer.json').exists():
        p=json.loads((OUT/'pointer.json').read_text())
        if p['sha256']!=digest:raise ValueError('Frozen pilot differs; use a new pilot revision')
    if not path.exists():atomic_json(path,manifest)
    if not (OUT/'pointer.json').exists():
        atomic_json(OUT/'pointer.json',{'file':path.name,'sha256':digest,'stage':'protocol_frozen'})
    print(json.dumps({'protocol':str(path),'items':6,'mechanisms':len(set(x['spec']['primary_mechanism'] for x in drafts)),
                      'provider_calls_in_this_preparation':0,'raw_sources_exported':False}))
    return manifest,digest


if __name__=='__main__':prepare()
