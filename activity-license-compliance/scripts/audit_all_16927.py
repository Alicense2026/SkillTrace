"""Reconcile historical combination results and repository-specific custom results."""
import csv, json, re, hashlib, sys
from pathlib import Path
from collections import Counter
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.aggregate_license_combinations import PROVIDERS
from license_checker.input_files import load_input
from license_checker.llm.aggregate_input import adapt_aggregate_rows
from license_checker.llm.license_sources import resolve_row_sources
from scripts.run_custom_license_experiment import prepare_row

OUT=ROOT/'runs/all-16927-execution-audit'
def read(p):return json.loads(p.read_text())
def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def table(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def verdict(e):
    if e['status']!='SUCCESS':return e['status']
    a=e['analysis'];fs=a['license_license_findings']+a['license_behavior_findings']
    if any(f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION'} for f in fs):return 'CONFIRMED_CONFLICT'
    if any(f['status'] in {'POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED'} for f in fs) or a['review_items']:return 'REVIEW_REQUIRED'
    if a['overall_status']=='INCOMPLETE_ANALYSIS':return 'INCOMPLETE_ANALYSIS'
    return 'NO_CONFLICT_WITH_OBLIGATIONS' if a['overall_status']=='OBLIGATIONS_OPEN' else 'NO_CONFLICT_IN_CHECKED_SCOPE'

def main():
    OUT.mkdir(exist_ok=True)
    src=ROOT/'aggregate_all_16927/result.csv'
    with src.open(encoding='utf-8-sig',newline='') as f:raws=list(csv.DictReader(f))
    rows=load_input(src)[0]['rows']
    agg=ROOT/'runs/license-combination-16927-2026-11-12'
    groups=[read(p) for p in (agg/'results').glob('*.json')]
    keys=lambda e:tuple(e['combination'][k] for k in ('GitHub许可证','资产许可证原文标题/标签','调用方式（代码修改）'))
    bykey={keys(e):e for e in groups};assert len(bykey)==len(groups)
    adapted=adapt_aggregate_rows([e['combination'] for e in groups],src)
    group_sources={keys(e):resolve_row_sources(r) for e,r in zip(groups,adapted)}
    custom={e['source_csv_line']:e for e in map(read,(ROOT/'runs/custom-license-16927-2026-11-12/results').glob('*.json'))}
    corpus=read(ROOT/'data/structured_asc_v1.json');sources={s['filename']:s for s in corpus['sources']}
    labels={r[k].strip() for r in raws for k in ('GitHub许可证','资产许可证')};canonical={}
    for label in sorted(labels,key=lambda s:(s==s.lower(),s)):canonical.setdefault(label.casefold(),label)
    canonical.update({'gemma':'Apache-2.0','odc-by':'ODC-BY-1.0'})
    def key(r):
        github,asset=[canonical[r[k].strip().casefold()] for k in ('GitHub许可证','资产许可证')]
        if asset.casefold()=='proprietary':
            host=(urlparse(r['资产URL']).hostname or '').lower()
            if host=='llama.com' or host.endswith('.llama.com'):
                m=re.search(r'llama[-_\s]*(3[._]?[123]|[234])(?=$|[^0-9])',r['AI模型/数据集/工具名'].casefold())
                v=m.group(1).replace('_','.') if m else '4'
                if v in ('31','32','33'):v=v[0]+'.'+v[1]
                asset=f'LLAMA {v} COMMUNITY LICENSE AGREEMENT'
            else:asset=next(v for d,v in PROVIDERS.items() if host==d or host.endswith('.'+d))
        mode='远程服务调用（修改不适用）' if r['调用方式'].strip()=='远程服务调用' else f"代码层面集成（修改：{r['代码集成是否修改'].strip()}）"
        return github,asset,mode
    records=[];mapped=Counter();overrides=[];used_sources=set();coverage=Counter();success_modes=Counter();reason_counts=Counter();side_gaps=Counter();origins=Counter();overall=Counter();findings=Counter();obligations=Counter()
    for line,(r,row) in enumerate(zip(raws,rows),2):
        pair=[r[k].strip() for k in ('GitHub许可证','资产许可证')]
        excluded=[]
        if any(re.search(r'(?<![a-z])gpl-2\.0(?:\b|$)',x,re.I) for x in pair):excluded.append('GPL-2.0系列')
        if any('lgpl' in x.casefold() for x in pair):excluded.append('LGPL系列')
        iscustom=any('licenseref-' in x.casefold() for x in pair)
        old=None
        if excluded:e={'status':'EXCLUDED','reason':'、'.join(excluded)};ss=[];channel='按用户口径排除'
        else:
            k=key(r);old=bykey[k];mapped[k]+=1
            if iscustom:
                e=custom[line];ss=resolve_row_sources(prepare_row(row));channel='自定义逐行'
                overrides.append({'line':line,'old_case':old['case_id'],'old_status':old['status'],'new_case':e['case_id'],'new_status':e['status']})
            else:e=old;ss=group_sources[k];channel='非自定义组合映射'
        available=[];ready=[];details=[]
        for side,field in [('downstream','github_license'),('upstream','artifact_license')]:
            items=[s for s in ss if s['side']==side and s.get('file')]
            expected=len(re.split(r'\s+OR\s+',row[field],flags=re.I))
            complete=len(items)==expected
            included=complete and all(sources[s['file']]['status']=='INCLUDED' for s in items)
            available.append(complete);ready.append(included)
            files=[s['file'] for s in items];used_sources.update(files)
            details.append('|'.join(files))
            if not excluded and not included:side_gaps[(side,row[field], 'NO_ORIGINAL_MAPPING' if not complete else 'NO_VALID_ASC')]+=1
        cv='EXCLUDED' if excluded else 'ASC_READY' if all(ready) else 'ORIGINALS_PRESENT_NO_VALID_ASC' if all(available) else 'MISSING_ORIGINAL_MAPPING'
        coverage[cv]+=1
        v=verdict(e);a=e.get('analysis',{})
        reason=e.get('reason','')
        if e['status']=='SKIPPED' and channel=='非自定义组合映射':
            side='upstream' if reason.startswith('upstream') else 'downstream'
            reason=side+': '+row['artifact_license' if side=='upstream' else 'github_license']+'；'+reason
        if e['status']!='SUCCESS':reason_counts[(e['status'],reason)]+=1
        else:
            origins[(channel,e.get('origin','NEW_ROW'))]+=1;overall[a['overall_status']]+=1;success_modes[row['integration']]+=1
            for field in ('license_license_findings','license_behavior_findings'):
                for status in {f['status'] for f in a[field]}:findings[(field,status)]+=1
            obligations.update(o['fulfillment_status'] for o in a['obligations'])
        records.append({'CSV记录位置':line,'仓库URL':row['github_url'],'下游许可证':row['github_license'],'资产':row['artifact_name'],'资产许可证':row['artifact_license'],'调用方式':row['integration'],'代码修改':row['modified'],'统计渠道':channel,'结果case_id':e.get('case_id',''),'执行状态':e['status'],'汇总判定':v,'模型原始总体状态':a.get('overall_status',''),'当前原文_ASC覆盖':cv,'下游原文':details[0],'上游原文':details[1],'义务数':len(a.get('obligations',[])),'失败或跳过原因':reason})
    assert len(mapped)==len(groups)
    assert all(mapped[keys(e)]==e['aggregate_count'] for e in groups)
    assert len(overrides)==len(custom)
    table('全部关系执行明细.csv',records)
    table('失败跳过原因统计.csv',[{'状态':s,'原因':r,'关系数':n} for (s,r),n in reason_counts.most_common()])
    table('原文_ASC缺口统计.csv',[{'侧别':s,'许可证标签':l,'缺口类型':g,'关系侧数':n} for (s,l,g),n in side_gaps.most_common()])
    table('原文结构化清单.csv',[{'原文文件':s['filename'],'ASC状态':s['status'],'规则数':sum(r['license_source_id']==s['source_id'] for r in corpus['rules']),'被本次范围映射使用':s['filename'] in used_sources} for s in corpus['sources']])
    summary={'input_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'total':len(records),'execution':dict(Counter(r['执行状态'] for r in records)),'verdict':dict(Counter(r['汇总判定'] for r in records)),'channels':{ch:dict(Counter(r['执行状态'] for r in records if r['统计渠道']==ch)) for ch in {r['统计渠道'] for r in records}},'coverage':dict(coverage),'overall':dict(overall),'success_modes':dict(success_modes),'origins':[{ 'channel':c,'origin':o,'relationships':n} for (c,o),n in origins.items()],'findings':[{ 'field':f,'status':s,'relationships':n} for (f,s),n in findings.items()],'obligations_expanded_by_relationship':dict(obligations),'custom_overrides_prior_success':[x for x in overrides if x['old_status']=='SUCCESS'],'source_count':len(sources),'source_status':dict(Counter(s['status'] for s in sources.values())),'rule_count':len(corpus['rules']),'used_source_count':len(used_sources),'used_source_status':dict(Counter(sources[f]['status'] for f in used_sources)),'all_combination_weights_reconciled':True,'all_custom_rows_overridden_once':True}
    write('summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
