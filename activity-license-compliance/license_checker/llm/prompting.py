"""唯一提示词组装入口：每次请求都携带完整12案例，禁止静默裁剪。"""
import json
import hashlib
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from ..asc import validate_triple
from .schema import output_contract
from .casebook import compact_figure_cases, load_patterns, compact_patterns
from .license_sources import resolve_row_sources

RESOURCES = Path(__file__).resolve().parents[1] / 'resources'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASC_CORPUS_PATH = PROJECT_ROOT / 'data' / 'structured_asc_v1.json'


def stable_json(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def load_cases():
    data=json.loads((RESOURCES/'figure10_cases.json').read_text(encoding='utf-8'))
    if [x['case_id'] for x in data['cases']] != [f'figure10-{i:02d}' for i in range(1,13)]:
        raise ValueError('All 12 Figure 10 cases are mandatory')
    for case in data['cases']:
        for term in case['asc_terms']:
            validate_triple(term['asc']);validate_triple(term['counterexample']['downstream_asc'])
    return data


@lru_cache(maxsize=1)
def load_structured_asc():
    data=json.loads(ASC_CORPUS_PATH.read_text(encoding='utf-8'))
    if data.get('schema_version') != 'asc-corpus-1.0' or not isinstance(data.get('sources'),list) or not isinstance(data.get('rules'),list):
        raise ValueError('Invalid structured ASC corpus')
    return data


def compact_structured_asc_rules(rules):
    """Group identical clause provenance/excerpts while retaining every ASC term."""
    grouped={}
    for rule in rules:
        key=tuple(rule.get(k) for k in ('side','license_label','license_id','clause_id',
                                        'clause_label','source_ref','source_excerpt','scope_note',
                                        'actor_role','extraction_status','condition_explanation'))
        if key not in grouped:
            grouped[key]={k:rule.get(k) for k in ('side','license_label','license_id','clause_id',
                                                   'clause_label','source_ref','source_excerpt','scope_note',
                                                   'actor_role','extraction_status')}
            grouped[key]['terms']=[]
            if rule.get('condition_explanation'):
                grouped[key]['condition_explanation']=rule['condition_explanation']
        term={'rule_id':rule['rule_id'],'triple':rule['triple']}
        grouped[key]['terms'].append(term)
    return list(grouped.values())


def build_request(config, case, inventory):
    cases=load_cases()
    casebook=compact_figure_cases(cases)
    patterns=compact_patterns(load_patterns())
    subjects=list(case['allowed_subjects'])
    allowed_refs={case['source_ref']}
    for facts in case['facts_by_subject'].values():
        for f in facts.values():allowed_refs.update(f['evidence_refs'])
    license_sources=resolve_row_sources(case['row'])
    asc_corpus=load_structured_asc()
    source_ids={s['filename']:s['source_id'] for s in asc_corpus['sources']}
    rules_by_source={}
    for rule in asc_corpus['rules']:
        rules_by_source.setdefault(rule['license_source_id'],[]).append(rule)
    structured_rules=[]
    subjects_by_artifact={(s['artifact'],s['kind']):s for s in subjects}
    for source in license_sources:
        allowed_refs.add(source['source_ref'])
        inventory[source['source_ref']]={'kind':'LOCAL_LICENSE_TEXT' if source.get('text') else 'MISSING_LICENSE_TEXT',
                                         'file':source.get('file'),'sha256':source.get('sha256'),
                                         'provider_match':source.get('provider_match')}
        filename=source.get('file')
        source_id=source_ids.get(filename)
        if not source_id:
            continue
        for rule in rules_by_source.get(source_id,[]):
            if source.get('applicable_line_range'):
                import re
                span=re.fullmatch(r'L(\d+)-L(\d+)',rule['clause_id'])
                lo,hi=source['applicable_line_range']
                if not span or not lo <= int(span[1]) <= int(span[2]) <= hi:
                    continue
            triple=deepcopy(rule['ASC'])
            triple['S']['artifact']=case['case_id']+':'+source['side']
            subjects_by_artifact[(triple['S']['artifact'],triple['S']['kind'])]=triple['S']
            structured_rules.append({'side':source['side'],'license_label':source['license_label'],
                                     'license_id':rule['license_id'],'rule_id':rule['rule_id'],
                                     'clause_id':rule['clause_id'],'clause_label':rule['clause_label'],
                                     'triple':triple,'source_ref':source['source_ref'],
                                     'source_excerpt':rule['source_excerpt'],'scope_note':rule['scope_note'],
                                     'actor_role':rule['actor_role'],'extraction_status':rule['extraction_status'],
                                     **({'condition_explanation':rule['condition_explanation']} if rule.get('condition_explanation') else {})})
    subjects=list(subjects_by_artifact.values())
    prompt_license_sources=[]
    rule_counts={}
    for rule in structured_rules:rule_counts[rule['source_ref']]=rule_counts.get(rule['source_ref'],0)+1
    for source in license_sources:
        prompt_license_sources.append({k:v for k,v in source.items() if k!='text'} |
                                      {'text_included':False,
                                       'matched_structured_rule_count':rule_counts.get(source['source_ref'],0)})
    compact_rules=compact_structured_asc_rules(structured_rules)
    task={'case_id':case['case_id'],'trusted_row':case.get('prompt_row',case['row']),
          'object_graph':case['object_graph'],
          'facts_by_subject':case['facts_by_subject'],
          'license_sources':prompt_license_sources,
          'license_source_policy':'Full license texts are retained locally and identified by filename/hash. Use the exact clause excerpts attached to structured_asc_rules; if those excerpts are insufficient for a conclusion, state the limitation rather than infer missing language.',
          'structured_asc_rules':compact_rules,
          'structured_asc_corpus':{'schema_version':asc_corpus['schema_version'],
                                   'sha256':hashlib.sha256(ASC_CORPUS_PATH.read_bytes()).hexdigest(),
                                   'extraction_status':'FIRST_PASS_REVIEW_REQUIRED'},
          'allowed_subjects':subjects,'allowed_source_refs':sorted(allowed_refs),
          'evidence':{ref:inventory[ref] for ref in sorted(allowed_refs)},
          'canonical_activities':case['canonical_activities']}
    if case.get('aggregate_weight') is not None:
        task['relationship_multiplicity']=case['aggregate_weight']
        task['multiplicity_note']='For a grouped license-combination input, this is the number of represented rows; it is not additional legal or behavior evidence.'
    instructions=(RESOURCES/'llm_system.txt').read_text(encoding='utf-8')
    user={'figure10_cases':casebook,'conflict_patterns':patterns,'output_contract':output_contract(),'task':task}
    body={'model':config.model,'store':False,'stream':False,'reasoning':{'effort':config.reasoning_effort},
          'max_output_tokens':config.max_output_tokens,'instructions':instructions,
          'input':[{'role':'user','content':[{'type':'input_text','text':stable_json(user)}]}]}
    serialized=stable_json(body)
    if len(serialized)>config.max_input_chars:raise ValueError('Prompt exceeds max_input_chars; no cases were silently truncated')
    meta={'case_id':case['case_id'],'request_sha256':sha(serialized),'cases_sha256':sha(stable_json(cases)),
          'casebook_sha256':sha(stable_json(casebook)),'patterns_sha256':sha(stable_json(patterns)),
          'system_sha256':sha(instructions),'example_count':12,'pattern_count':len(patterns['patterns']),'prompt_chars':len(serialized),
          'structured_asc_rule_count':len(structured_rules),
          'structured_asc_clause_group_count':len(compact_rules),
          'structured_asc_sha256':hashlib.sha256(ASC_CORPUS_PATH.read_bytes()).hexdigest(),
          'allowed_subjects':subjects,'allowed_refs':sorted(allowed_refs)}
    return body,meta
