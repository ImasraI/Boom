"""Machine-readable shape contract; references/semantics need Python checks too."""
from app.rag.pedagogical_authoring import TECHNIQUES
from app.rag.reasoning_tags import TAXONOMY_VERSION


def schema():
    def text(limit=12000):return {'type':'string','minLength':1,'maxLength':limit,'pattern':r'\S'}
    def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    point={'type':'string','pattern':'^[A-Z][0-9]?$'}
    step_id={'type':'string','pattern':'^s[1-9][0-9]?$'}
    pair={'type':'array','items':point,'minItems':2,'maxItems':2,'uniqueItems':True}
    witness=obj({k:text() for k in ('transformation','preserved','conclusion')})
    technique=obj({'id':{'enum':sorted(TECHNIQUES)},'role':{'enum':['primary','supporting','check']},
        'step_ids':{'type':'array','items':step_id,'minItems':1,'maxItems':30,'uniqueItems':True},
        'evidence':text(),'symmetry_witness':{'anyOf':[{'type':'null'},witness]}})
    technique['allOf']=[{'if':{'properties':{'id':{'const':'tech.symmetry'}}},
        'then':{'properties':{'symmetry_witness':witness}},
        'else':{'properties':{'symmetry_witness':{'type':'null'}}}}]
    figure=obj({'points':{'type':'object','minProperties':2,'maxProperties':16,'propertyNames':point,
         'additionalProperties':{'type':'array','items':{'type':'number','minimum':-1000000,'maximum':1000000},'minItems':2,'maxItems':2}},
        'segments':{'type':'array','items':pair,'maxItems':32},
        'circles':{'type':'array','maxItems':5,'items':obj({'center':point,'through':point})}})
    pedagogy=obj({'key_observation':text(),
        'steps':{'type':'array','minItems':1,'maxItems':30,'items':obj({'id':step_id,'explanation':text(),'math':text()})},
        'proposed_techniques':{'type':'array','maxItems':12,'items':technique},
        'boundary_checks':{'type':'array','maxItems':20,'items':text()},'answer_justification':text(),
        'alternative_route':{'anyOf':[{'type':'null'},text()]}})
    result=obj({'text':text(),'options':{'type':'array','minItems':4,'maxItems':4,'uniqueItems':True,'items':text(1500)},
        'answer_index':{'type':'integer','minimum':0,'maximum':3},'solution':text(10000),
        'design':obj({k:text(3000) for k in ('givens','unknown','domains','essential_insight','structural_departure','tempting_wrong_route')}),
        'figure':{'anyOf':[{'type':'null'},figure]},'pedagogy':pedagogy,
        'verification_record':obj({'method':{'enum':['analytic','symbolic','finite_enumeration','mixed']},
            'summary':text(),'claimed_by':{'const':'author_model'}})})
    return {'$schema':'https://json-schema.org/draft/2020-12/schema',
            '$id':'urn:karzar:pedagogical-authoring:0.2','title':'Local pedagogical authoring candidate v0.2',
            '$comment':'Shape only. Python additionally checks unique step/tag IDs, references, finite coordinates, distinct points and circle radius. No mathematical/human approval.',
            'x-taxonomy-version':TAXONOMY_VERSION,**result}
