"""Row-level custom license experiment, isolated from standard-license statistics."""
import argparse,csv,json,re,sys,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from license_checker.input_files import load_input
from license_checker.identity import case_id
from license_checker.llm.custom_licenses import resolve_custom_source,REGISTRY
from license_checker.llm.license_sources import resolve_row_sources,_provider
from license_checker.llm.experiment import prepare_llm_case,save,save_three_outputs
from license_checker.llm.prompting import build_request,stable_json,sha,ASC_CORPUS_PATH
from license_checker.llm.config import load_config
from license_checker.llm.client import ResponsesClient,extract_text,APIError
from license_checker.llm.schema import parse_result
OUT=ROOT/'runs/custom-license-16927-2026-11-12'
INPUT=ROOT/'aggregate_all_16927/result.csv'

def has_custom(row):return any('licenseref-' in row.get(k,'').casefold() for k in ('github_license','artifact_license'))

def prepare_row(row):
    row=dict(row);row['_raw_modified']=row['modified']
    if row['integration']=='远程服务调用':row['modified']='\\'
    if row['artifact_license'].casefold()=='gemma':row['artifact_license']='Apache-2.0';row['_license_convention']='Gemma mapped to Apache-2.0 by user study convention'
    if row['artifact_license'].casefold()=='odc-by':row['artifact_license']='ODC-BY-1.0'
    if row['artifact_license'].casefold()=='proprietary' and 'llama.com' in row['artifact_url'] and not _provider(row):
        row['_original_artifact_name']=row['artifact_name'];row['artifact_name']='llama 4';row['_license_convention']='Unrecognized Llama version defaults to 4 by user instruction'
    return row

def skip_reason(row,corpus):
    included={s['filename'] for s in corpus['sources'] if s['status']=='INCLUDED'}
    for side,field in [('downstream','github_license'),('upstream','artifact_license')]:
        label=row[field].strip()
        if 'lgpl' in label.casefold() or re.search(r'(?<![a-z])gpl-2\.0\b',label,re.I):return 'EXCLUDED_LICENSE_FAMILY',label
        if label.casefold().startswith('licenseref-'):
            mapping=resolve_custom_source(row,side)
            if not mapping:return 'MISSING_REPOSITORY_MAPPING',side+': '+row.get('github_url' if side=='downstream' else 'artifact_url','')
            if mapping['status']!='AVAILABLE':return 'EMPTY_CUSTOM_ORIGINAL',mapping['repository']
    sources=resolve_row_sources(row)
    for side,field in [('upstream','artifact_license'),('downstream','github_license')]:
        matched=[s for s in sources if s['side']==side]
        expected=len(re.split(r'\s+OR\s+',row[field],flags=re.I))
        if len(matched)!=expected or any(s.get('file') not in included for s in matched):
            return 'NO_USABLE_ASC',side+': '+row[field]
    return None,None

def placeholder(e):
    for folder in ('license_license','license_activity','obligations'):
        save(OUT/'three_outputs'/folder/(e['case_id']+'.json'),{'case_id':e['case_id'],'status':e['status'],'reason':e.get('reason'),'source_csv_line':e['source_csv_line'],'output':None})

def report(entries):
    ok=[e for e in entries if e['status']=='SUCCESS'];counts=Counter(e['status'] for e in entries)
    overview=[];metrics=[];repos={}
    for e in entries:
        a=e.get('analysis',{});ll=a.get('license_license_findings',[]);la=a.get('license_behavior_findings',[])
        def classify(fs):
            if e['status']!='SUCCESS':return e['status']
            if any(f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION'} for f in fs):return '冲突/违规'
            if any(f['status'] in {'POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED'} for f in fs):return '潜在冲突/范围核查'
            if a['overall_status']=='INCOMPLETE_ANALYSIS':return '分析不完整'
            return '检查范围内未检出冲突'
        r=e['row'];repo=r['github_url'];item={'源CSV行号':e['source_csv_line'],'case_id':e['case_id'],'仓库':repo,'自定义许可证':r['github_license'],'原文文件':(e.get('custom_mapping') or {}).get('filename',''),'原文SHA256':(e.get('custom_mapping') or {}).get('sha256',''),'资产':r['artifact_name'],'资产许可证':r['artifact_license'],'调用方式':r['integration'],'代码修改':r['_raw_modified'],'状态':e['status'],'license-license':classify(ll),'license-activity':classify(la),'义务条目数':len(a.get('obligations',[])),'总体状态':a.get('overall_status',''),'原因':e.get('reason','')};overview.append(item)
        repos.setdefault((repo,r['github_license']),[]).append(item)
    with (OUT/'custom_relationship_results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(overview[0]));w.writeheader();w.writerows(overview)
    for field,title in [('license_license_findings','License-License'),('license_behavior_findings','License-Activity')]:
        statuses={f['status'] for e in ok for f in e['analysis'][field]}|{'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED'}
        for status in sorted(statuses):
            relevant=[e for e in ok if any(f['status']==status for f in e['analysis'][field])]
            metrics.append({'category':title,'status':status,'finding_count':sum(f['status']==status for e in ok for f in e['analysis'][field]),'relationship_count':len(relevant),'repository_count':len({e['row']['github_url'] for e in relevant})})
    with (OUT/'custom_conflict_statistics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(metrics[0]));w.writeheader();w.writerows(metrics)
    with (OUT/'custom_repository_statistics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['仓库','自定义许可证','关系数','成功','跳过','失败','确定冲突关系数','潜在冲突关系数','义务条目数'])
        for (repo,label),items in sorted(repos.items()):
            w.writerow([repo,label,len(items),sum(i['状态']=='SUCCESS' for i in items),sum(i['状态']=='SKIPPED' for i in items),sum(i['状态']=='ERROR' for i in items),sum('冲突/违规' in (i['license-license'],i['license-activity']) for i in items),sum('潜在冲突/范围核查' in (i['license-license'],i['license-activity']) for i in items),sum(i['义务条目数'] for i in items)])
    summary={'input':str(INPUT),'selected_custom_relationships':len(entries),'repositories':len(repos),'status':dict(counts),'overall_status':dict(Counter(e['analysis']['overall_status'] for e in ok)),'skip_reasons':dict(Counter(e.get('reason_code') for e in entries if e['status']=='SKIPPED')),'error_reasons':dict(Counter(e.get('reason') for e in entries if e['status']=='ERROR')),'obligation_count':sum(len(e['analysis']['obligations']) for e in ok),'review_item_relationships':sum(bool(e['analysis']['review_items']) for e in ok)}
    save(OUT/'summary.json',summary)
    lines=['# 自定义许可证供应链 ASC 实验报告','','本报告按 LicenseRef 标签单独统计自定义许可证关系，不与此前组合实验混合计数。标签表示数据集分类，不保证每份原文均为实质非标准条款。输入为 `aggregate_all_16927/result.csv`，筛选任一侧含 LicenseRef 的关系；按原始明细行检测，保留原始 CSV 行号。不同仓库的 LicenseRef-Custom 不共享许可身份。', '',f"共 {len(entries)} 条关系、{len(repos)} 个仓库；处理状态：{dict(counts)}。",'','## 方法与来源','','根据 `_licenseref_full/licenseref_full.json` 的完整仓库名、许可证标签及原文 SHA-256 精确匹配；不按仓库短名推断 fork 或继承关系。相同原文字节可复用 ASC，但每条供应链关系均保留自己的仓库、资产和行为证据。新增提取使用 GPT-6-luna，保留原文行号、分块请求、原始响应和覆盖说明；只有完成的来源被纳入。新冲突请求使用工具现有提示词及 Figure 10 全部12个案例，不运行离线判定引擎。', '', '模型：GPT-6-luna，reasoning_effort=medium；输出上限8192 token。未确认分发、商用收费、网络提供修改版本等事实不会补写；可履行条件放入义务集合。', '', '## 冲突类型统计','','同一关系可能产生多项条款发现；关系数在各状态内去重，类型间不可直接相加。','','|类别|状态|发现条数|关系数|仓库数|','|---|---|---:|---:|---:|']
    for m in metrics:lines.append(f"|{m['category']}|{m['status']}|{m['finding_count']}|{m['relationship_count']}|{m['repository_count']}|")
    lines+=['','## 总体状态与义务','','|总体状态|关系数|','|---|---:|']
    for k,v in summary['overall_status'].items():lines.append(f'|{k}|{v}|')
    lines+=['','## 处理覆盖率','','|处理结果|关系数|占筛选关系比例|','|---|---:|---:|']
    for state in ('SUCCESS','ERROR','SKIPPED'):
        lines.append(f'|{state}|{counts[state]}|{counts[state]/len(entries):.2%}|')
    lines+=['','|调用方式|筛选关系|成功|失败|跳过|','|---|---:|---:|---:|---:|']
    for mode in sorted({e['row']['integration'] for e in entries}):
        subset=[e for e in entries if e['row']['integration']==mode];tally=Counter(e['status'] for e in subset)
        lines.append(f"|{mode}|{len(subset)}|{tally['SUCCESS']}|{tally['ERROR']}|{tally['SKIPPED']}|")
    lines+=['','检测告警数仅统计成功响应；没有告警不等于全部条款完整覆盖。若成功样本均为远程调用，结论不能外推到代码集成、修改或分发。分析不完整的关系及跳过、失败关系均不作为确定的无冲突样本。']
    lines += ['',f"义务条目共 {summary['obligation_count']} 条；包含显式人工核查项的关系 {summary['review_item_relationships']} 条。UNKNOWN 履行状态不等同于未履行。",'', '## 案例分析','']
    ranked=sorted(ok,key=lambda e:(-sum(f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT'} for field in ('license_license_findings','license_behavior_findings') for f in e['analysis'][field]),e['source_csv_line']))
    examples=[];seen_repos=set()
    for e in ranked:
        repo=e['row']['github_url'].casefold()
        if repo not in seen_repos:examples.append(e);seen_repos.add(repo)
        if len(examples)==3:break
    for n,e in enumerate(examples,1):
        a=e['analysis'];r=e['row'];lines += [f"### 案例 {n}：{r['github_url']}",'',f"原始CSV第 {e['source_csv_line']} 行，`{e['case_id']}`；{r['github_license']} / {r['artifact_license']}；{r['integration']}；总体状态 {a['overall_status']}。"]
        found=[f for field in ('license_license_findings','license_behavior_findings') for f in a[field] if f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED'}]
        if not found:lines.append('未报告冲突告警，作为检测范围和义务继承的对照案例，不作为冲突正例。')
        for f in found[:3]:lines.append(f"- {f['status']} / {f['activity']}：{f['reason']}")
        for o in a['obligations'][:3]:lines.append(f"- 义务：{o['requirement']}（{o['fulfillment_status']}）")
        for l in a['limitations'][:2]:lines.append('- 范围限制：'+l)
        lines.append('')
    lines+=['## 缺口与解释边界','',f"跳过原因：{summary['skip_reasons']}。格式/请求失败：{summary['error_reasons']}。",'','缺失映射、空原文、无有效 ASC、未知上游许可证及响应失败均不计为无冲突。仅提供名称或外部协议引用的原文不被扩写为完整许可证。结果属于基于给定材料的模型检测，未经人工金标准验证，不报告精确率或召回率。']
    (OUT/'final_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--workers',type=int,default=3);args=ap.parse_args()
    config=replace(load_config(ROOT/'configs/experiment.toml'),max_input_chars=400000)
    payload,source=load_input(INPUT);corpus=json.loads(ASC_CORPUS_PATH.read_text());entries=[];pending=[]
    manifest={'input_sha256':sha(INPUT.read_text(encoding='utf-8-sig')),'asc_sha256':sha(ASC_CORPUS_PATH.read_text()),'registry_sha256':sha(REGISTRY.read_text()),'config':config.public_dict()}
    if (OUT/'manifest.json').exists():assert json.loads((OUT/'manifest.json').read_text())==manifest,'Input/ASC/config changed'
    save(OUT/'manifest.json',manifest)
    for i,raw in enumerate(payload['rows']):
        if not has_custom(raw):continue
        row=prepare_row(raw);cid=case_id(row,i);e={'case_id':cid,'source_csv_line':i+2,'row':row,'custom_mapping':resolve_custom_source(row,'downstream')};entries.append(e);dest=OUT/'results'/(cid+'.json')
        if dest.exists():e.update(json.loads(dest.read_text()));continue
        code,reason=skip_reason(row,corpus)
        if code:e.update(status='SKIPPED',reason_code=code,reason=reason);save(dest,e);placeholder(e);continue
        case=prepare_llm_case(row,i,str(source));inventory={case['source_ref']:{'kind':'TRUSTED_CHAIN_RECORD','raw_record':raw}}
        try:body,meta=build_request(config,case,inventory)
        except ValueError as exc:e.update(status='ERROR',reason=str(exc));save(dest,e);placeholder(e);continue
        save(OUT/'requests'/(cid+'.json'),{'endpoint':config.endpoint,'body':body,'metadata':meta});e['status']='PENDING';pending.append((e,body,meta))
    save(OUT/'plan.json',entries);print(json.dumps({'selected':len(entries),'statuses':dict(Counter(e['status'] for e in entries))}),flush=True)
    if not args.execute:return
    def run(item):
        e,body,meta=item;cid=e['case_id'];start=time.monotonic()
        try:
            raw=ResponsesClient(config).create(body);save(OUT/'responses'/(cid+'.json'),raw)
            a=parse_result(extract_text(raw),cid,meta['allowed_subjects'],meta['allowed_refs'])
            e.update(status='SUCCESS',analysis=a,usage=raw.get('usage'),reported_model=raw.get('model'),request_sha256=meta['request_sha256']);save_three_outputs(OUT,cid,a)
        except (APIError,ValueError,TypeError,KeyError) as exc:e.update(status='ERROR',reason=str(exc));placeholder(e)
        e['elapsed_seconds']=round(time.monotonic()-start,2);save(OUT/'results'/(cid+'.json'),e);return e
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n,f in enumerate(as_completed([pool.submit(run,j) for j in pending]),1):
            e=f.result();print(f"{n}/{len(pending)} {e['case_id']} {e['status']} {e.get('reason','')}",flush=True)
            save(OUT/'progress.json',{'completed_new':n,'total_new':len(pending),'statuses':dict(Counter(e['status'] for e in entries))})
    report(entries)
if __name__=='__main__':main()
