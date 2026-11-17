"""Review/normalize only the new extraction; keep raw model output unchanged.

Repairs are explicitly logged. Older corpus entries are copied unchanged from
the pre-extension snapshot. No API calls and no conflict decisions are made.
"""
from copy import deepcopy
import json
import re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.extend_asc_corpus import ROOT, RUN, CORPUS, save, digest
from license_checker.asc import validate_triple

def literals(value):
    if isinstance(value,str) and value.lower() in {'true','false'}:
        return value.lower()=='true'
    if isinstance(value,dict):return {k:literals(v) for k,v in value.items()}
    if isinstance(value,list):return [literals(v) for v in value]
    return value

def reviewed(rule):
    r=deepcopy(rule);c=r['ASC']['C'];name=r['license_id']
    lo=int(re.match(r'L(\d+)',r['clause_id'])[1]);a=r['ASC']['A'];obj=r['ASC']['S']['kind']
    for key in ('when','requires'):
        if key in c:c[key]=literals(c[key])
    # PROHIBITED ignores requires in the ASC evaluator; preserve the model's
    # stated conditional prohibition instead of silently making it absolute.
    if c['kind']=='PROHIBITED' and c.get('requires',True) is not True:
        c['kind']='CONDITIONALLY_PROHIBITED'
    if c['kind']=='OBLIGATORY' and 'requires' not in c:
        predicate='fulfill_'+r['license_source_id'].replace('-','_')+'_'+r['clause_id'].replace('-','_')+'_duty'
        c['requires']=predicate
        r['condition_explanation'] += ' Predicate '+predicate+' means fulfilling exactly this duty: '+r['scope_note']
    if name=='CC-BY-NC-ND-4.0.txt':
        # The model grouped disjoint grants into a Cartesian product.
        if lo==143 and a=='Distribute' and obj=='DerivativeWork':return None
        if lo==143:
            c['requires']={'all':['noncommercial_purpose','comply_with_other_applicable_public_license_conditions']}
        if lo in {151,244} and c['kind']=='PROHIBITED' and obj=='ModifiedArtifact':
            c['when']='modified_material_is_adapted_material_not_merely_authorized_technical_modification'
        if lo==176:
            r['ASC']['A']='Use';r['actor_role']='downstream_recipient'
            r['ASC']['C']={'kind':'CONDITIONALLY_PERMITTED','when':'received_licensed_material_and_accepted_offer',
                          'requires':'comply_with_public_license_conditions'}
            r['condition_explanation']='The licensor makes an automatic offer to the recipient; this is not an affirmative duty on the distributor to make a separate offer.'
        if lo==189:
            r['ASC']['C']={'kind':'UNSPECIFIED','when':'asserting_or_implying_licensor_endorsement'}
            r['condition_explanation']='The license does not grant endorsement rights. This absence of a grant is not a blanket prohibition on Use.'
        if lo==209:return None  # royalty waiver/reservation is not a separate Use grant
    if name=='COCL-1.0.txt' and lo==42:
        c['when']='activity_constitutes_commercial_use_under_section_1_2'
        r['condition_explanation'] += ' The commercial-use definition is a prerequisite; noncommercial Use/Distribute is not prohibited by this clause.'
    # No trademark grant is different from an absolute ban on software use.
    if (name,lo) in {('MulanPSL-2.0.txt',31),('BUSL-1.1.txt',18),('COCL-1.0.txt',75)}:
        r['ASC']['C']={'kind':'UNSPECIFIED','when':'trademark_use_beyond_express_notice_or_attribution_exception'}
        r['condition_explanation']='No trademark rights are granted beyond the stated notice/attribution exception; separate rights or authorization are not adjudicated here.'
    if name.startswith('Kimi+') and lo==41:
        r['ASC']['C']={'kind':'CONDITIONALLY_PROHIBITED','when':'deep_synthesis_service_label_is_generated_in_output',
                      'requires':'delete_alter_or_conceal_that_label'}
        r['condition_explanation']='Only deleting, altering or concealing the generated deep-synthesis label is prohibited; other output modifications are not prohibited by this sentence.'
    validate_triple(r['ASC'])
    return r

def main():
    current=json.loads(CORPUS.read_text())
    if any(s.get('family')=='repository_custom' for s in current['sources']):
        raise ValueError('Historical 2026-11-12 finalizer would discard later custom sources; use the custom extraction workflow instead')
    raw_path=RUN/'new_rules_before_review.json'
    if not raw_path.exists():save(raw_path,json.loads((RUN/'new_rules.json').read_text()))
    extra=json.loads(raw_path.read_text());base=json.loads((RUN/'before_extension.json').read_text())
    fixes=[];new=[]
    for old in extra['rules']:
        r=reviewed(old)
        if r!=old:
            fixes.append({'original_rule_id':old['rule_id'],'original_ASC':old['ASC'],
                          'reviewed_ASC':r['ASC'] if r else None,
                          'reason':'Explicit normalization/review against source lines; see scripts/finalize_asc_extension.py'})
            if r:
                signature=json.dumps([r['clause_id'],r['ASC'],r['actor_role'],r['scope_note']],ensure_ascii=False,sort_keys=True)
                r['rule_id']=r['license_source_id']+'-'+r['clause_id']+'-'+r['ASC']['A']+'-'+r['ASC']['S']['kind']+'-'+digest(signature.encode())[:8]
                r['review_status']='ASSISTANT_REVIEWED_MAPPING; not human legal certification'
        if r:new.append(r)
    extra['rules']=new;save(RUN/'new_rules.json',extra);save(RUN/'normalization_audit.json',fixes)
    base['sources']+=extra['sources'];base['rules']+=new
    base['extensions']=base.get('extensions',[])+[{'run':'runs/asc-extension-2026-11-12','sources':len(extra['sources']),
        'rules':len(new),'method':'LLM extraction, literal source spans, recorded normalization and targeted assistant review'}]
    base['method']+=' Incremental LLM extraction with audited corrections; see extensions.'
    base['created_by']='scripts/build_asc_corpus.py + scripts/extend_asc_corpus.py + scripts/finalize_asc_extension.py'
    save(CORPUS,base)
    counts={}
    for r in base['rules']:counts[r['license_id']]=counts.get(r['license_id'],0)+1
    summary={'source_count':len(base['sources']),'included_sources':sum(s['status']=='INCLUDED' for s in base['sources']),
             'excluded_sources':len(base['excluded_sources']),'unclassified_sources':0,
             'sources_with_rules':len(counts),'sources_without_rule_match':0,
             'rule_count':len(base['rules']),'rules_per_source':counts,'output':'data/structured_asc_v1.json'}
    save(ROOT/'data/structured_asc_v1_summary.json',summary)
    s=json.loads((RUN/'summary.json').read_text());s.update(new_rules=len(new),total_rules=len(base['rules']),
        rules_per_source={x['filename']:counts[x['filename']] for x in extra['sources']},reviewed_or_removed_rules=len(fixes))
    save(RUN/'summary.json',s);print(json.dumps(s,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
