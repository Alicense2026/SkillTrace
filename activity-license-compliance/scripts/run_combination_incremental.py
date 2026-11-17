"""Incremental grouped experiment: retain raw historical evidence and run unmatched groups."""
import csv,json,hashlib,shutil,sys,time,argparse
from pathlib import Path
from collections import Counter
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from license_checker.input_files import load_input
from license_checker.identity import case_id
from license_checker.llm.config import load_config
from license_checker.llm.experiment import prepare_llm_case,save,save_three_outputs
from license_checker.llm.prompting import build_request,stable_json,ASC_CORPUS_PATH
from license_checker.llm.schema import parse_result
from license_checker.llm.client import ResponsesClient,extract_text,APIError

def task(q):return json.loads(q['body']['input'][0]['content'][0]['text'])['task']
def key(t):
    return (tuple(sorted((s['side'],s['file'],s['sha256']) for s in t['license_sources'])),t['trusted_row']['调用方式（代码修改）'])
def remap(v,m):
    if isinstance(v,str):
        for a,b in m.items():v=v.replace(a,b)
        return v
    if isinstance(v,list):return [remap(x,m) for x in v]
    if isinstance(v,dict):return {remap(k,m):remap(x,m) for k,x in v.items()}
    return v

def report(out,entries):
    ok=[e for e in entries if e['status']=='SUCCESS'];weighted=Counter()
    for e in entries:weighted[e['status']]+=e['aggregate_count']
    summary={'groups':len(entries),'relationships':sum(e['aggregate_count'] for e in entries),'status_groups':dict(Counter(e['status'] for e in entries)),'status_relationships':dict(weighted),'reused':sum(e.get('origin')=='REUSED' for e in ok),'new_success':sum(e.get('origin')=='NEW' for e in ok)}
    save(out/'summary.json',summary)
    lines=['# 16927 数据集供应链 ASC 冲突检测实验报告','','输入：`aggregate_all_16927/许可证组合统计.csv`。组合为检测单位，数量列仅用于加权，不是重复实验或额外法律证据。','',f"共 {len(entries)} 组，代表 {summary['relationships']} 条关系；复用历史成功结果 {summary['reused']} 组，新增模型检测成功 {summary['new_success']} 组。",'','按有方向的上下游原文文件与哈希、调用方式和修改状态匹配历史结果；忽略仓库、标签大小写、数量。旧请求、响应及结果原样保存于 reused_originals；新请求使用当前 ASC、既有提示词和 Figure 10 全部12个案例。未使用离线判定引擎。','','|处理状态|组合数|代表关系数|','|---|---:|---:|']
    for s,n in summary['status_groups'].items():lines.append(f'|{s}|{n}|{weighted[s]}|')
    lines += ['', '运行配置：GPT-6-luna；reasoning_effort=medium；每次最多 8,192 输出 token；3 路并发；每个新请求保留全部 12 个 Figure 10 案例。实际返回模型名保存在各结果 reported_model 字段。']

    lines+=['','## 冲突数量与类型统计','','发现条数可包含同组的多个条款；组合数和关系数在每种状态内去重，各类型不能直接相加。','','|类别|状态|发现条数|去重组合数|代表关系数|','|---|---|---:|---:|---:|'];metrics=[]
    for field,title in [('license_license_findings','License–License'),('license_behavior_findings','License–Activity')]:
        kinds={f['status'] for e in ok for f in e['analysis'][field]}|{'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED'}
        for s in sorted(kinds):
            subset=[e for e in ok if any(f['status']==s for f in e['analysis'][field])]
            count=sum(f['status']==s for e in ok for f in e['analysis'][field]);weight=sum(e['aggregate_count'] for e in subset)
            metrics.append({'category':title,'status':s,'findings':count,'groups':len(subset),'relationships':weight})
            lines.append(f'|{title}|{s}|{count}|{len(subset)}|{weight}|')
    save(out/'conflict_statistics.json',metrics)
    with (out/'conflict_statistics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['category','status','findings','groups','relationships']);writer.writeheader();writer.writerows(metrics)
    exact=[e for e in ok if any(f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION'} for field in ('license_license_findings','license_behavior_findings') for f in e['analysis'][field])]
    potential=[e for e in ok if any(f['status']=='POTENTIAL_CONFLICT' for field in ('license_license_findings','license_behavior_findings') for f in e['analysis'][field])]
    lines += ['',f'两类检测合并去重：确定冲突/违规 {len(exact)} 组（{sum(e["aggregate_count"] for e in exact)} 条代表关系）；潜在冲突 {len(potential)} 组（{sum(e["aggregate_count"] for e in potential)} 条代表关系）。分母仅为成功完成检测的 {len(ok)} 组、{sum(e["aggregate_count"] for e in ok)} 条代表关系。']
    if (out/'reuse_effective_asc_audit.json').exists() and (out/'reuse_prompt_audit.json').exists():
        asc_audit=json.loads((out/'reuse_effective_asc_audit.json').read_text());prompt_audit=json.loads((out/'reuse_prompt_audit.json').read_text())
        if not asc_audit['changed_effective_ASC'] and not prompt_audit['changed_prompt_components']:
            lines += ['',f'复用一致性审计：{asc_audit["checked"]} 组的实际 ASC 条款、系统提示词、Figure 10 案例和冲突模式均与当前任务一致（忽略任务标识和标签大小写）；全局语料哈希不同来自其他新增许可证，未改变这些组的实际输入条款。']
    lines+=['','## 总体判定和义务集合','','|总体状态|组合数|代表关系数|','|---|---:|---:|']
    for s in sorted({e['analysis']['overall_status'] for e in ok}):
        subset=[e for e in ok if e['analysis']['overall_status']==s]
        lines.append(f"|{s}|{len(subset)}|{sum(e['aggregate_count'] for e in subset)}|")
    buckets={}
    for e in ok:
        a=e['analysis'];findings=a['license_license_findings']+a['license_behavior_findings']
        if any(f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION'} for f in findings):verdict='冲突/违规'
        elif a['overall_status']=='INCOMPLETE_ANALYSIS' or a['review_items'] or any(f['status'] in {'POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED'} for f in findings):verdict='需要核查或分析不完整'
        else:verdict='检查范围内未检出冲突（保留义务）'
        buckets.setdefault(verdict,[]).append(e)
    lines+=['','### 组级汇总分类','','分类由原始状态确定，不更改模型原始输出。义务履行未知本身不自动转为人工核查。','','|分类|组合数|代表关系数|','|---|---:|---:|']
    for verdict,subset in buckets.items():lines.append(f'|{verdict}|{len(subset)}|{sum(e["aggregate_count"] for e in subset)}|')
    obligations=Counter(o['fulfillment_status'] for e in ok for o in e['analysis']['obligations'])
    lines+=['',f'义务条目状态：{dict(obligations)}。UNKNOWN 不代表未履行或违规。',f"含人工核查项的成功组合：{sum(bool(e['analysis']['review_items']) for e in ok)}。",'','## 案例分析','']
    ranked=sorted(ok,key=lambda e:(-sum(f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT'} for field in ('license_license_findings','license_behavior_findings') for f in e['analysis'][field]),e['case_id']))
    examples=[e for e in ranked if any(f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT'} for field in ('license_license_findings','license_behavior_findings') for f in e['analysis'][field])][:3]
    for cid in ('chain-0293-c9823b13815c','chain-0359-5b89953c210c'):
        candidate=next((e for e in ok if e['case_id']==cid),None)
        if candidate and candidate not in examples and len(examples)<3:examples.append(candidate)
    for e in ranked:
        if len(examples)>=3:break
        if e not in examples:examples.append(e)
    for n,e in enumerate(examples,1):
        r=e['combination'];a=e['analysis']
        lines += [f"### 案例 {n}：{r['资产许可证原文标题/标签']} → {r['GitHub许可证']}",'',f"{r['调用方式（代码修改）']}；代表 {e['aggregate_count']} 条关系；来源 {e['origin']}；编号 `{e['case_id']}`；总体判定 {a['overall_status']}。"]
        findings=[f for field in ('license_license_findings','license_behavior_findings') for f in a[field] if f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED'}]
        for f in findings[:3]:lines.append(f"- {f['status']} / {f['activity']}：{f['reason']}")
        if not findings:lines.append('未报告确定冲突或潜在冲突，作为无冲突对照案例。')
        if e['case_id']=='chain-0297-43a032907f77':
            lines.append('- 结果一致性检查：原始标签为 POTENTIAL_CONFLICT，但原始理由明确称两项条件可共同履行、未见相反要求。该项仅作为模型原始告警统计，不能写作已验证的许可证冲突；按现有理由应更接近条件继承/义务待履行。为忠实复用历史实验，本报告保留原始标签并单列此问题，未覆盖模型输出。')
        for o in a['obligations'][:2]:lines.append(f"- 义务：{o['requirement']}（{o['fulfillment_status']}）")
        for limit in a['limitations'][:2]:lines.append(f'- 范围限制：{limit}')
        if e['case_id']=='chain-0293-c9823b13815c':
            lines.append('- 实验口径：BUSL-1.1按用户指定的模板分析；上述用途限制作为条件义务保留，不要求补充许可参数，也不将参数未填写单独计为违规或人工核查项。')
        if e['case_id']=='chain-0359-5b89953c210c':
            lines.append('- 事实一致性检查：输入只确认代码集成及修改，未确认网络交互。原始理由中的“已知……远程调用”不受本行输入支持，不能作为已发生事实；AGPL网络源码义务只能保留为条件义务。原始结果不作覆盖修改。')

        lines.append('')
    lines+=['## 研究范围与限制','','本报告是 ASC 摘录与可信行为事实下的模型检测结果；没有人工金标准，不能据此计算精确率或召回率。跳过和响应失败不计为无冲突。历史复用沿用旧 ASC 版本和原始结论，不能表述为全部使用新增语料重新分析。分发、收费等未确认事实不会补写为已发生；可履行条件保留在义务集合。']
    (out/'final_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (out/'results_overview.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['case_id','GitHub许可证','资产许可证','调用方式','数量','处理状态','来源','总体判定','错误或跳过原因'])
        for e in entries:
            r=e['combination'];w.writerow([e['case_id'],r['GitHub许可证'],r['资产许可证原文标题/标签'],r['调用方式（代码修改）'],e['aggregate_count'],e['status'],e.get('origin',''),e.get('analysis',{}).get('overall_status',''),e.get('reason','')])
    print(json.dumps(summary,ensure_ascii=False),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--retry-network-errors',action='store_true');ap.add_argument('--workers',type=int,default=3);args=ap.parse_args()
    src=ROOT/'aggregate_all_16927/许可证组合统计.csv';old=ROOT/'runs/license-combination-asc-2026-11-10-network';out=ROOT/'runs/license-combination-16927-2026-11-12'
    config=load_config(ROOT/'configs/experiment.toml');payload,source=load_input(src);rows=payload['rows'];history={}
    for p in sorted((old/'results').glob('*.json')):
        r=json.loads(p.read_text())
        if r.get('status')!='SUCCESS':continue
        q=json.loads((old/'requests'/p.name).read_text());m=q['metadata']
        parse_result(stable_json(r['analysis']),r['case_id'],m['allowed_subjects'],m['allowed_refs'])
        history.setdefault(key(task(q)),(p,r,q))
    manifest={'input':str(src),'input_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'asc_sha256':hashlib.sha256(ASC_CORPUS_PATH.read_bytes()).hexdigest(),'historical_run':str(old),'config':config.public_dict()}
    if (out/'manifest.json').exists():assert json.loads((out/'manifest.json').read_text())==manifest,'Input/config changed'
    save(out/'manifest.json',manifest);save(out/'run_policy.json',{'max_input_chars':400000,'reason':'Retain full ASC clauses and all 12 Figure10 cases','workers':args.workers});entries=[];pending=[]
    for i,row in enumerate(rows):
        cid=case_id(row,i);weight=row['_aggregate_weight'];e={'case_id':cid,'input_group_row':i+1,'aggregate_count':weight,'combination':row['_aggregate_prompt_row']};entries.append(e);dest=out/'results'/f'{cid}.json'
        if dest.exists():
            prior=json.loads(dest.read_text())
            if prior.get('reason')!='Prompt exceeds max_input_chars; no cases were silently truncated' and not (args.retry_network_errors and prior.get('reason')=='Network/timeout failure (details omitted)'):
                e.update(prior);continue
            save(out/'prior_failures'/dest.name,prior)
        if row.get('_aggregate_skip_reason'):
            e.update(status='SKIPPED',reason=row['_aggregate_skip_reason']);save(dest,e)
            for folder in ('license_license','license_activity','obligations'):save(out/'three_outputs'/folder/f'{cid}.json',dict(e,output=None))
            continue
        case=prepare_llm_case(row,i,str(source));inventory={case['source_ref']:{'kind':'TRUSTED_CHAIN_RECORD','raw_record':case['prompt_row']}}
        try:body,meta=build_request(replace(config,max_input_chars=400000),case,inventory)
        except ValueError as exc:e.update(status='ERROR',reason=str(exc));save(dest,e);continue
        q={'endpoint':config.endpoint,'body':body,'metadata':meta};save(out/'requests'/f'{cid}.json',q);match=history.get(key(task(q)))
        if match:
            p,r,oq=match;ot,nt=task(oq),task(q);mapping={r['case_id']:cid}
            for s in ot['license_sources']:
                ns=next(x for x in nt['license_sources'] if x['side']==s['side'] and x['file']==s['file']);mapping[s['source_ref']]=ns['source_ref']
            for ref in oq['metadata']['allowed_refs']:
                if '#/rows/' in ref:mapping[ref]=case['source_ref']
            a=remap(r['analysis'],mapping);parse_result(stable_json(a),cid,meta['allowed_subjects'],meta['allowed_refs'])
            archive=out/'reused_originals'/r['case_id'];archive.mkdir(parents=True,exist_ok=True)
            for folder in ('requests','responses','results'):
                original=old/folder/p.name
                if original.exists():shutil.copy2(original,archive/f'{folder}.json')
            e.update(status='SUCCESS',origin='REUSED',analysis=a,reused_from=str(p),original_case_id=r['case_id'],original_request_sha256=r['request_sha256'],original_asc_sha256=oq['metadata']['structured_asc_sha256'],reported_model=r.get('reported_model'),reference_remapping=mapping)
            save(dest,e);save_three_outputs(out,cid,a,weight)
        else:e.update(status='PENDING',origin='NEW');pending.append((e,body,meta))
    save(out/'plan.json',[{k:v for k,v in e.items() if k!='analysis'} for e in entries]);print(json.dumps({'groups':len(entries),'status':dict(Counter(e['status'] for e in entries)),'pending':len(pending)},ensure_ascii=False),flush=True)
    if not args.execute:return
    def run(item):
        e,body,meta=item;cid=e['case_id'];start=time.monotonic()
        try:
            response=ResponsesClient(config).create(body);save(out/'responses'/f'{cid}.json',response)
            a=parse_result(extract_text(response),cid,meta['allowed_subjects'],meta['allowed_refs'])
            e.update(status='SUCCESS',analysis=a,reported_model=response.get('model'),usage=response.get('usage'),request_sha256=meta['request_sha256']);save_three_outputs(out,cid,a,e['aggregate_count'])
        except (APIError,ValueError,TypeError,KeyError) as exc:
            e.update(status='ERROR',reason=str(exc))
            for folder in ('license_license','license_activity','obligations'):save(out/'three_outputs'/folder/f'{cid}.json',{'case_id':cid,'status':'ERROR','output':None,'reason':str(exc),'aggregate_count':e['aggregate_count']})
        e['elapsed_seconds']=round(time.monotonic()-start,2);save(out/'results'/f'{cid}.json',e);return e
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n,f in enumerate(as_completed([pool.submit(run,item) for item in pending]),1):
            e=f.result();print(f"{n}/{len(pending)} {e['case_id']} {e['status']} {e.get('reason','')}",flush=True)
            save(out/'progress.json',{'completed_new':n,'total_new':len(pending),'statuses':dict(Counter(e['status'] for e in entries))})
    report(out,entries)
if __name__=='__main__':main()
