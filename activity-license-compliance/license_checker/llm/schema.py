"""LLM 输出合同：校验身份、ASC、状态和引用；不自动应用模型建议。"""
import json
from ..asc import validate_triple, atoms
from ..taxonomy import normalize_activity

FIELDS = {'case_id','asc_rules','license_license_findings','license_behavior_findings',
          'obligations','review_items','overall_status','limitations'}
STATUS = {'VIOLATION','CONSTRAINT_CONFLICT','OBLIGATIONS_OPEN','INCOMPLETE_ANALYSIS','NO_CONFLICT_IN_CHECKED_SCOPE'}
FINDING_STATUS = STATUS | {'POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED','NOT_APPLICABLE','CONDITIONS_INCLUDED','CONDITIONS_TO_INHERIT'}


def nonempty(value):
    return isinstance(value,str) and bool(value.strip())


def strings(value):
    return isinstance(value,list) and all(nonempty(x) for x in value)


def parse_result(text, case_id, allowed_subjects, allowed_refs):
    # Deliberately don't strip markdown fences or extract a random JSON fragment.
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d: raise ValueError('Duplicate JSON key: '+k)
            d[k]=v
        return d
    try: data=json.loads(text, object_pairs_hook=unique)
    except (json.JSONDecodeError,TypeError) as exc: raise ValueError('Output must be one valid JSON object') from exc
    if not isinstance(data,dict): raise ValueError('Output must be an object')
    # Some compatible endpoints append this harmless schema marker despite the
    # instruction to emit only the eight payload fields. Preserve the untouched
    # raw response separately; validate and store the normalized payload here.
    if data.get('schema_version')=='llm-analysis-2.0' and set(data)==FIELDS|{'schema_version'}:
        data.pop('schema_version')
    elif data.get('schema_version')=='llm-analysis-2.0' and set(data)==(FIELDS-{'case_id'})|{'schema_version'}:
        data.pop('schema_version')
        data['case_id']=case_id
    if set(data)!=FIELDS: raise ValueError('Output fields do not match contract')
    if data['case_id'] != case_id: raise ValueError('Wrong case_id')
    if not nonempty(data['overall_status']) or data['overall_status'] not in STATUS: raise ValueError('Unknown overall_status')
    for name in FIELDS-{'case_id','overall_status'}:
        if not isinstance(data[name],list): raise ValueError(name+' must be an array')
    if not strings(data['review_items']) or not strings(data['limitations']): raise ValueError('Invalid review_items/limitations')
    def refs(value):
        if not strings(value) or not set(value) <= set(allowed_refs): raise ValueError('Unknown evidence reference')
    def subject(s):
        if s not in allowed_subjects: raise ValueError('Unknown subject')
    for record in data['asc_rules']:
        if not isinstance(record,dict) or set(record)!={'side','triple','source_refs'}: raise ValueError('Invalid ASC rule record')
        if not nonempty(record['side']) or record['side'] not in {'upstream','downstream'}: raise ValueError('Invalid side')
        validate_triple(record['triple']); subject(record['triple']['S']); refs(record['source_refs'])
        if record['triple']['S']['artifact'] != case_id+':'+record['side']: raise ValueError('Rule side/subject mismatch')
    for name in ('license_license_findings','license_behavior_findings'):
        for f in data[name]:
            if not isinstance(f,dict) or set(f)!={'activity','status','reason','source_refs','figure_case_refs'}: raise ValueError('Invalid finding')
            if normalize_activity(f['activity']) != f['activity'] or not nonempty(f['status']) or f['status'] not in FINDING_STATUS or not nonempty(f['reason']): raise ValueError('Invalid finding values')
            refs(f['source_refs'])
            if not strings(f['figure_case_refs']) or not set(f['figure_case_refs']) <= {f'figure10-{i:02d}' for i in range(1,13)}: raise ValueError('Invalid figure references')
    for o in data['obligations']:
        if not isinstance(o,dict) or set(o)!={'activity','subject','requirement','trigger','applicability','fulfillment_status','unresolved_predicates','source_refs'}: raise ValueError('Invalid obligation')
        if normalize_activity(o['activity'])!=o['activity'] or not nonempty(o['requirement']): raise ValueError('Invalid obligation values')
        subject(o['subject']); refs(o['source_refs'])
        atoms(o['trigger'])
        if o['applicability'] is not None and type(o['applicability']) is not bool: raise ValueError('Invalid obligation applicability')
        if not strings(o['unresolved_predicates']): raise ValueError('Invalid unresolved predicates')
        if not nonempty(o['fulfillment_status']) or o['fulfillment_status'] not in {'FULFILLED','NOT_FULFILLED','UNKNOWN'}: raise ValueError('Invalid fulfillment status')
    return data


def output_contract():
    return {
      'case_id':'exact task.case_id',
      'asc_rules':[{'side':'upstream|downstream','triple':{'A':'canonical activity','S':'one of allowed_subjects','C':{'kind':'one of seven modalities','when':'boolean expression','requires':'boolean expression'}},'source_refs':['one of allowed_source_refs']}],
      'license_license_findings':[{'activity':'canonical activity','status':'one of finding_statuses','reason':'A/S; upstream requirement; opposing term or observed behavior; trigger; conflict witness; sources','source_refs':[],'figure_case_refs':[]}],
      'license_behavior_findings':[{'activity':'canonical activity','status':'one of finding_statuses','reason':'A/S; upstream requirement; opposing term or observed behavior; trigger; conflict witness; sources','source_refs':[],'figure_case_refs':[]}],
      'obligations':[{'activity':'canonical activity','subject':'one of allowed_subjects','requirement':'compliance requirement, preserve OR','trigger':'boolean expression','applicability':'true|false|null','unresolved_predicates':['unknown fact names'],'fulfillment_status':'FULFILLED|NOT_FULFILLED|UNKNOWN','source_refs':[]}],
      'review_items':['Only decisive semantic contradiction/ambiguity that cannot be represented as a conditional obligation; normally empty'], 'overall_status':'one of overall_statuses', 'limitations':['text'],
      'overall_statuses':sorted(STATUS),'finding_statuses':sorted(FINDING_STATUS),
      'condition_syntax':{'expressions':['true','false','nonempty predicate string',{'all':['expression']},{'any':['expression']},{'not':'expression'}],'unknown_facts':'null, never invented true/false'},
      'schema_version':'llm-analysis-2.0',
      'note':'This is a contract description; output ONLY the eight data fields, not *_statuses, condition_syntax, schema_version or note helper fields. Empty arrays are allowed.'}
