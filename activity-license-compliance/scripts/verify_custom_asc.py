"""Validate the custom ASC source chain and write a repository-readable index."""
import csv,json,re,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.extend_asc_corpus import save,digest
from license_checker.asc import validate_triple
from license_checker.llm.config import load_config

def main():
    run=ROOT/'runs/custom-asc-2026-11-12';custom=json.loads((ROOT/'data/structured_asc_custom_v1.json').read_text());all_data=json.loads((ROOT/'data/structured_asc_v1.json').read_text());before=json.loads((run/'before_extension.json').read_text())
    assert all_data['sources'][:len(before['sources'])]==before['sources']
    assert all_data['rules'][:len(before['rules'])]==before['rules']
    sources={s['source_id']:s for s in custom['sources']};lines={};counts=Counter();issues=[]
    for sid,s in sources.items():
        data=(ROOT/'许可证原文'/s['filename']).read_bytes();assert digest(data)==s['sha256'];lines[sid]=data.decode('utf-8-sig').splitlines()
    for rule in custom['rules']:
        validate_triple(rule['ASC']);lo,hi=map(int,re.fullmatch(r'L(\d+)-L(\d+)',rule['clause_id']).groups());assert rule['source_excerpt']=='\n'.join(lines[rule['license_source_id']][lo-1:hi]);counts[rule['license_source_id']]+=1
        c=rule['ASC']['C']
        if c['kind']=='PROHIBITED' and c.get('requires',True) is not True:issues.append({'rule_id':rule['rule_id'],'issue':'PROHIBITED has a conditional requires predicate','C':c})
        if c['kind']=='OBLIGATORY' and 'requires' not in c:issues.append({'rule_id':rule['rule_id'],'issue':'OBLIGATORY missing requires','C':c})
    byfile={s['filename']:s for s in sources.values()};index=[]
    for r in custom['registry']:
        s=byfile.get(r['filename']);index.append({'仓库':r['repository'],'数据许可证标签':r['license_label'],'原文文件':r['filename'],'SHA256':r['sha256'],'结构化状态':s['status'] if s else r['status'],'ASC条目数':counts[s['source_id']] if s else 0,'采集证据文件':r['evidence_file'],'覆盖说明':' | '.join(custom['coverage_notes'].get(r['filename'],[]))})
    with (run/'custom_asc_index.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(index[0]));w.writeheader();w.writerows(index)
    report={'registry_records':len(index),'unique_sources':len(sources),'rules':len(custom['rules']),'source_status':dict(Counter(s['status'] for s in sources.values())),'old_sources_and_rules_unchanged':True,'literal_excerpt_checks_passed':True,'constraint_shape_review':issues}
    save(run/'verification.json',report);save(run/'config.json',load_config(ROOT/'configs/experiment.toml').public_dict());print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
