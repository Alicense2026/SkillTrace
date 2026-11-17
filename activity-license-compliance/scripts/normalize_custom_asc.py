"""Apply the previously tested generic ASC representation normalization to custom rules only."""
import json,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.extend_asc_corpus import save,digest
from scripts.finalize_asc_extension import reviewed

def main():
    corpus=ROOT/'data/structured_asc_v1.json';custom_path=ROOT/'data/structured_asc_custom_v1.json';run=ROOT/'runs/custom-asc-2026-11-12'
    data=json.loads(corpus.read_text());custom=json.loads(custom_path.read_text());audit=[];normalized=[]
    if not (run/'custom_before_normalization.json').exists():save(run/'custom_before_normalization.json',custom)
    for rule in data['rules']:
        if not rule['license_source_id'].startswith('custom-src-'):normalized.append(rule);continue
        new=reviewed(rule)
        if new!=rule:
            new['rule_id']=rule['license_source_id']+'-'+rule['clause_id']+'-'+digest(json.dumps([new['ASC'],new['actor_role'],new['scope_note']],sort_keys=True,ensure_ascii=False).encode())[:12]
            new['normalization_status']='GENERIC_ASC_REPRESENTATION_NORMALIZED; original response retained'
            audit.append({'old_rule_id':rule['rule_id'],'new_rule_id':new['rule_id'],'before':rule['ASC'],'after':new['ASC'],'reason':'Preserve conditional prohibitions and explicit obligation predicates; canonicalize boolean literals; same generic normalization as prior ASC workflow'})
        normalized.append(new)
    data['rules']=normalized;save(corpus,data)
    ids={s['source_id'] for s in custom['sources']};custom['rules']=[r for r in normalized if r['license_source_id'] in ids];save(custom_path,custom)
    if audit:save(run/'normalization_audit.json',audit)
    for s in custom['sources']:
        path=run/'by_license'/(s['sha256']+'.json');item=json.loads(path.read_text());item['rules']=[r for r in custom['rules'] if r['license_source_id']==s['source_id']];save(path,item)
    print(json.dumps({'normalized_rules':len(audit),'custom_rule_count':len(custom['rules'])}))
if __name__=='__main__':main()
