"""Row-wise live LLM experiment on the frozen, repaired ASC corpus.
Never calls the offline conflict engine. All three outputs retain row identity.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import replace
import csv
import fcntl
import json
import os
import subprocess
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import extract_segmented_asc as extraction
from license_checker.llm.experiment import prepare_llm_case
from license_checker.llm.prompting import load_cases, stable_json, sha, RESOURCES
from license_checker.llm.casebook import compact_figure_cases, compact_patterns, load_patterns
from license_checker.llm.schema import output_contract, parse_result
from license_checker.llm.config import load_config
from license_checker.llm.client import ResponsesClient, extract_text

ASC_RUN=ROOT/'runs/skill-asc-gap-repair-2026-11-14'
CORPUS=ASC_RUN/'reviewed_structured_asc.json'
INPUT=extraction.INPUT
RUN=ROOT/'runs/skill-conflict-obligations-2026-11-14'
AUDIT_STATUSES={'INCLUDED','NO_OBLIGATION','NOT_APPLICABLE','OUT_OF_SCOPE','ALTERNATIVE_LICENSE_PATH'}
SYSTEM=(RESOURCES/'llm_system.txt').read_text(encoding='utf-8').replace('含LGPL标签的记录已从本批排除；不得对其作许可证结论。','本批沿用新输入所包含的所有许可证，LGPL/GPL 不因历史批次排除政策而跳过；LGPL-3.0 的本地 GPL-3.0 引用材料以显式依赖提供。').replace('FIRST_PASS_REVIEW_REQUIRED','SEGMENTED_EXTRACTION_REPAIRED_MODEL_REVIEWED')+'''

【本轮补充合同与覆盖检查，优先于旧接口描述】
输出上述八字段，另加第九个字段 rule_obligation_audit。task.structured_asc_rules 是本轮逐条记录，rule_ref 为短编号 U001/D001；每条含 triple、source_excerpt_ref、source_ref、actor_role、scope_note、condition_explanation、obligation_items、supporting_excerpts。source_excerpt_ref 指向 task.clause_excerpts 中的精确原文，共享摘录只存一次，不能漏读。facts_by_subject 仅列已知事实，未列的事实均为未知，不是 false。先比较所有候选约束，聚合两侧相关义务，勿只给少数代表性通知。
rule_obligation_audit 对每个 rule_ref 恰好输出一次：{"rule_ref":"U001","status":"INCLUDED|NO_OBLIGATION|NOT_APPLICABLE|OUT_OF_SCOPE|ALTERNATIVE_LICENSE_PATH","obligation_indices":[0],"reason":"简短说明义务如何保留或为何不适用"}。obligation_indices 是 obligations 数组的零基索引。INCLUDED 必须引用至少一项有相同来源的义务；一条 ASC 的多个独立义务均应保留，OR 保持可选路径。其他状态索引必须为空。不能把含明确相关义务的规则列为 NO_OBLIGATION；仅尚不知道触发是否发生，应该 INCLUDED 并保留条件，而非 NOT_APPLICABLE。索引仅关联最终输出，不依赖推理过程。
未提供的外部引用文件已按用户政策排除，不要求补文件、不因此生成 review_items；仅保留本地文本明确规定的义务，不虚构外部内容。超出现有活动词表的事项不强行映射、不新增 activity。排除并非该行为获准。源段落审计仅为方法边界，不能证明实际违规或义务已经履行。
调用、修改、商业行为依据该行事实。模型或平台是商用产品不等于下游已收费、获得相关授权、违反非商业条款。精确保留本行明确商业信息，其他留条件，不再次索取采集证据。自定义许可证仅用此行冻结的仓库映射，OR 许可为可选路径，不能把两种许可强行同时要求。
保留每条许可证的对象和主体范围：远程服务提供者的义务不自动转给调用者；上游输出、模型权重、独立下游代码不视为同一对象。义务 requirement 写明承担主体、对象与例外。许可证之间的判断和实际行为的判断分别输出。
最终输出所有 reason/requirement/limitations 使用简明中文，谓词可英文。仅严格 JSON，不附 Markdown。
'''

def load(p):return json.loads(p.read_text(encoding='utf-8'))
save=extraction.save

def context():
    inv=load(extraction.RUN/'inventory.json');corpus=load(CORPUS)
    if extraction.digest(INPUT.read_bytes())!=inv['input_sha256']:raise ValueError('Input differs from extraction inventory')
    if not load(ASC_RUN/'final_verification.json')['baseline_rules_preserved']:raise ValueError('ASC verification missing')
    with INPUT.open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.DictReader(handle))
    mappings=defaultdict(list)
    for m in inv['mappings']:mappings[m['csv_row']].append(m)
    rules=defaultdict(list);sources={s['sha256']:s for s in corpus['sources']};by_file={f:s for s in corpus['sources'] for f in s['files']}
    lines={}
    for s in corpus['sources']:
        p=extraction.LICENSE_DIR/s['files'][0]
        if extraction.digest(p.read_bytes())!=s['sha256']:raise ValueError('License original changed')
        lines[s['sha256']]=p.read_text(encoding='utf-8-sig').splitlines()
    for r in corpus['rules']:rules[r['source_sha256']].append(r)
    return {'rows':rows,'mappings':mappings,'rules':rules,'sources':sources,'by_file':by_file,'lines':lines,'inventory':inv,
            'figure':compact_figure_cases(load_cases()),'patterns':compact_patterns(load_patterns())}

def make_task(ctx,index):
    raw=ctx['rows'][index];repo=raw['Skill 仓库']
    row={'github_repo':repo,'github_url':repo if repo.startswith('https://') else 'https://github.com/'+repo,
         'github_license':raw['normalized_downstream_license'],'artifact_name':raw['上游依赖'],
         'artifact_url':raw['上游 URL'],'artifact_license':raw['normalized_upstream_license'],
         'integration':raw['调用方式'],'modified':raw['是否修改'],'evidence':raw['调用证据（截断）'],'batch':raw['批次']}
    case=prepare_llm_case(row,index,str(INPUT));cid=f'skill-{index+1:05d}'
    old=case['case_id'];case=json.loads(json.dumps(case,ensure_ascii=False).replace(old,cid))
    mappings=deepcopy(ctx['mappings'][index+2])
    for mapping in list(mappings):
        for filename in ctx['inventory'].get('dependencies',{}).get(mapping['source_file'],[]):
            s=ctx['by_file'][filename]
            mappings.append({**mapping,'source_file':filename,'sha256':s['sha256'],'applicable_line_range':None,'incorporated_by':mapping['source_file']})
    selected=[];source_records=[];counts=Counter();seen=set()
    refs={case['source_ref']}
    for m in mappings:
        source_ref='license:'+m['sha256'];refs.add(source_ref)
        source_records.append({**m,'source_ref':source_ref,'extraction_status':ctx['sources'][m['sha256']]['status']})
        for r in ctx['rules'][m['sha256']]:
            span=m.get('applicable_line_range');a,b=r['source_lines']
            if span and not (span[0]<=a<=b<=span[1]):continue
            identity=(m['side'],r['rule_id'])
            if identity in seen:continue
            seen.add(identity);counts[m['side']]+=1
            triple=deepcopy(r['ASC']);triple['S']['artifact']=cid+':'+m['side']
            selected.append({'rule_ref':('U' if m['side']=='upstream' else 'D')+f"{counts[m['side']]:03d}",
                             'rule_id':r['rule_id'],'side':m['side'],'license_label':m['label'],'license_id':r['license_id'],
                             'triple':triple,'source_ref':source_ref,
                             **{k:r[k] for k in ('source_lines','source_excerpt','actor_role','scope_note','condition_explanation','obligation_items')},
                             'supporting_excerpts':[{'source_lines':[lo,hi],'text':'\n'.join(ctx['lines'][m['sha256']][lo-1:hi])} for lo,hi in r.get('supporting_source_ranges',[])]})
    if not counts['upstream'] or not counts['downstream']:raise ValueError('No effective ASC rules on one side')
    excerpts={};excerpt_keys={}
    for rule in selected:
        key=(rule['source_ref'],tuple(rule['source_lines']),rule['source_excerpt'])
        if key not in excerpt_keys:
            ref=f'E{len(excerpts)+1:03d}';excerpt_keys[key]=ref
            excerpts[ref]={'source_ref':rule['source_ref'],'source_lines':rule['source_lines'],'text':rule['source_excerpt']}
        rule['source_excerpt_ref']=excerpt_keys[key];rule.pop('source_excerpt')
    known_facts={s:{k:v for k,v in facts.items() if v['value'] is not None} for s,facts in case['facts_by_subject'].items()}
    known_facts={s:f for s,f in known_facts.items() if f}
    return {'case_id':cid,'trusted_row':raw,'object_graph':case['object_graph'],'facts_by_subject':known_facts,'clause_excerpts':excerpts,
            'structured_asc_rules':selected,'license_sources':source_records,'allowed_subjects':case['allowed_subjects'],
            'allowed_source_refs':sorted(refs),'canonical_activities':extraction.ACTS,
            'evidence':{case['source_ref']:{'kind':'TRUSTED_CHAIN_RECORD','raw_record':raw}},
            'source_excel_row':raw['source_excel_row'],'csv_row':index+2}

def validate(text,task):
    data=json.loads(text);audit=data.pop('rule_obligation_audit')
    # Exact serialization aliases only; never infer artifact identity or scope.
    aliases={s['artifact']+' '+s['kind']:s for s in task['allowed_subjects']}
    for obligation in data.get('obligations',[]):
        if isinstance(obligation.get('subject'),str) and obligation['subject'] in aliases:
            obligation['subject']=deepcopy(aliases[obligation['subject']])
    result=parse_result(json.dumps(data,ensure_ascii=False),task['case_id'],task['allowed_subjects'],task['allowed_source_refs'])
    index={r['rule_ref']:r for r in task['structured_asc_rules']}
    if sorted(a['rule_ref'] for a in audit)!=sorted(index):raise ValueError('Audit every rule_ref exactly once')
    for a in audit:
        if set(a)!={'rule_ref','status','obligation_indices','reason'} or a['status'] not in AUDIT_STATUSES or not isinstance(a['reason'],str) or not a['reason'].strip():raise ValueError('Invalid rule obligation audit')
        indices=a['obligation_indices']
        if not isinstance(indices,list) or any(type(i)!=int or not 0<=i<len(result['obligations']) for i in indices):raise ValueError('Invalid obligation index')
        if a['status']=='INCLUDED':
            if not indices:raise ValueError('INCLUDED requires obligation indices')
            if any(index[a['rule_ref']]['source_ref'] not in result['obligations'][i]['source_refs'] for i in indices):raise ValueError('Obligation source inconsistent with rule audit')
        elif indices:raise ValueError('Excluded/no-duty audit must use empty obligation_indices')
    # These are consistency checks, never a replacement legal decision engine.
    statuses={f['status'] for f in result['license_license_findings']+result['license_behavior_findings']}
    if 'VIOLATION' in statuses and result['overall_status']!='VIOLATION':raise ValueError('overall_status must retain explicit VIOLATION')
    if 'CONSTRAINT_CONFLICT' in statuses and result['overall_status'] not in {'VIOLATION','CONSTRAINT_CONFLICT'}:raise ValueError('overall_status must retain explicit conflict')
    result['rule_obligation_audit']=audit
    return result

def request(task,ctx,cfg):
    contract=output_contract();contract['rule_obligation_audit']=[{'rule_ref':'each U001/D001 once','status':sorted(AUDIT_STATUSES),'obligation_indices':'zero-based indices','reason':'why included or excluded'}]
    body={'model':cfg.model,'instructions':SYSTEM,'input':stable_json({'figure10_cases':ctx['figure'],'conflict_patterns':ctx['patterns'],'output_contract':contract,'task':task}),
          'max_output_tokens':48000 if len(task['structured_asc_rules'])>150 else 24000,'reasoning':{'effort':'medium'},'store':False,'stream':False}
    if len(stable_json(body))>cfg.max_input_chars:raise ValueError('Prompt exceeds configured limit; no clauses or cases truncated')
    return body

def publish_three(record):
    analysis=record['analysis'];cid=record['case_id']
    for name,field in [('license_license','license_license_findings'),('license_activity','license_behavior_findings'),('obligations','obligations')]:
        out={k:record[k] for k in ('case_id','csv_row','source_excel_row','raw_response')}
        out['output']=analysis[field];out['limitations']=analysis['limitations']
        if name=='obligations':out['rule_obligation_audit']=analysis['rule_obligation_audit']
        save(RUN/'three_outputs'/name/f'{cid}.json',out)

def execute_one(index,ctx,cfg,execute):
    cid=f'skill-{index+1:05d}'
    try:task=make_task(ctx,index)
    except ValueError as e:
        if str(e)!='No effective ASC rules on one side':raise
        record={'case_id':cid,'csv_row':index+2,'source_excel_row':ctx['rows'][index]['source_excel_row'],'status':'SKIPPED_MISSING_ASC','reason':'Mapped original has no effective ASC rules; do not infer permission from UNLICENSED or absent rules.'}
        if execute:
            save(RUN/'results'/f'{cid}.json',record)
            for folder in ('license_license','license_activity','obligations'):save(RUN/'three_outputs'/folder/f'{cid}.json',{**record,'output':None})
        return record
    body=request(task,ctx,cfg);sig=sha(stable_json(body))
    result_path=RUN/'results'/f'{cid}.json'
    if result_path.exists():
        old=load(result_path)
        if old.get('status')=='SUCCESS' and old.get('request_sha256')==sig:
            validate(json.dumps(old['analysis'],ensure_ascii=False),task);publish_three(old);return old
    save(RUN/'requests'/f'{cid}.json',{'request_sha256':sig,'body':body,'csv_row':index+2})
    if not execute:return {'case_id':cid,'status':'DRY_RUN','asc_rules':len(task['structured_asc_rules']),'prompt_chars':len(stable_json(body))}
    def publish_success(response,response_path,analysis,attempt):
        record={'case_id':cid,'csv_row':index+2,'source_excel_row':task['source_excel_row'],'status':'SUCCESS','request_sha256':sig,
                'analysis':analysis,'raw_response':str(response_path),'usage':response.get('usage',{}),'model':response.get('model',cfg.model),'attempt':attempt,'normalization_policy':'Exact subject serialization aliases may be converted to allowed_subject objects; raw response retained'}
        save(result_path,record)
        publish_three(record)
        return record
    for response_path in sorted((RUN/'responses').glob(cid+'-*.json'),reverse=True):
        try:
            response=load(response_path);analysis=validate(extract_text(response),task)
            return publish_success(response,response_path,analysis,'recovered_raw_response')
        except (ValueError,KeyError,TypeError,RuntimeError):continue
    original=body['input'];invocation=time.time_ns()
    for attempt in range(1,4):
        aid=f'{cid}-{invocation}-{attempt}';save(RUN/'attempt_requests'/f'{aid}.json',body);raw=''
        try:
            response=ResponsesClient(cfg).create(body);save(RUN/'responses'/f'{aid}.json',response)
            raw=extract_text(response);analysis=validate(raw,task)
            return publish_success(response,RUN/'responses'/f'{aid}.json',analysis,attempt)
        except Exception as e:
            error=f'{type(e).__name__}: {e}';save(RUN/'errors'/f'{aid}.json',{'case_id':cid,'error':error,'attempt':attempt})
            if 'HTTP 401' in error or 'HTTP 403' in error:break
            body['input']=original+('\n上次待修复输出（不是证据）：\n'+raw if raw else '')+'\n校验失败：'+error+'\n仅修复错误，保留全部合法判断和义务，返回完整九字段 JSON；rule_ref 与来源编号必须精确复制。'
            time.sleep(min(5*attempt,15))
    record={'case_id':cid,'csv_row':index+2,'source_excel_row':task['source_excel_row'],'status':'ERROR','request_sha256':sig,'error':error}
    save(result_path,record);return record

def report(ctx,selected):
    records=[load(p) for p in sorted((RUN/'results').glob('*.json'))]
    success=[r for r in records if r['status']=='SUCCESS'];errors=[r for r in records if r['status']=='ERROR']
    overall=Counter(r['analysis']['overall_status'] for r in success)
    ll=Counter(f['status'] for r in success for f in r['analysis']['license_license_findings'])
    la=Counter(f['status'] for r in success for f in r['analysis']['license_behavior_findings'])
    relation_counts={}
    for field in ('license_license_findings','license_behavior_findings'):
        relation_counts[field]=dict(Counter(status for r in success for status in {f['status'] for f in r['analysis'][field]}))
    summary={'input_relationships':len(ctx['rows']),'scheduled_relationships':selected,'success':len(success),'failed':len(errors),'skipped':sum(r['status'].startswith('SKIPPED') for r in records),'pending':len(ctx['rows'])-len(records),
             'overall':dict(overall),'license_license_findings':dict(ll),'license_activity_findings':dict(la),'relationship_status_counts':relation_counts,
             'obligation_items':sum(len(r['analysis']['obligations']) for r in success),'rule_audits':sum(len(r['analysis']['rule_obligation_audit']) for r in success),
             'review_relationships':sum(bool(r['analysis']['review_items']) for r in success),'updated_unix':time.time()}
    save(RUN/'summary.json',summary)
    lines=['# 新输入供应链冲突与义务聚合实验（运行中自动更新）','',f"输入关系 {len(ctx['rows'])}；本次计划 {selected}；成功 {len(success)}；失败 {len(errors)}；跳过 {summary['skipped']}；待执行 {summary['pending']}。",'',
           '模型：GPT-6-luna。使用本轮最终 ASC 和每行冻结映射；每次包含完整 Figure 10 的 12 个案例及既有冲突模式。逐行调用模型，不调用离线冲突引擎。',
           '仅成功响应纳入判断统计，失败和待执行不计为合规。OBLIGATIONS_OPEN 表示有待履行或条件性义务，不等于已证实违规。规则义务审计为模型自检，不是专家验证。','',
           '|统计口径|状态|数量|','|---|---|---:|']
    for title,counts in [('关系总体互斥状态',overall),('许可证冲突发现条目',ll),('行为冲突发现条目',la)]:
        lines.extend(f'|{title}|{k}|{v}|' for k,v in sorted(counts.items()))
    lines+=['',f"义务项合计：{summary['obligation_items']}；需人工核查关系：{summary['review_relationships']}。",'', '## 案例（最多三个）','']
    examples=[]
    for r in success:
        fs=[f for f in r['analysis']['license_license_findings']+r['analysis']['license_behavior_findings'] if f['status'] in {'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT'}]
        if fs and len(examples)<3:
            examples.append(r['case_id']);row=ctx['rows'][r['csv_row']-2]
            lines+=[f"### {r['case_id']}：{row['Skill 仓库']} → {row['上游依赖']}"]+[f"- {f['status']} / {f['activity']}：{f['reason']}" for f in fs[:3]]+['']
    if not examples:lines+=['当前已完成结果中尚无符合上述状态的案例，不能据此推断待执行样本无冲突。']
    (RUN/'实验结果报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--background',action='store_true');ap.add_argument('--limit',type=int);ap.add_argument('--offset',type=int,default=0);ap.add_argument('--workers',type=int,default=6);ap.add_argument('--report-only',action='store_true');args=ap.parse_args()
    RUN.mkdir(parents=True,exist_ok=True)
    if args.background:
        if not args.execute:raise ValueError('--background requires --execute')
        argv=[sys.executable,'-u',str(Path(__file__).resolve()),*[arg for arg in sys.argv[1:] if arg!='--background']]
        with (RUN/'worker.log').open('ab') as log:
            process=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        save(RUN/'launcher.json',{'pid':process.pid,'started_unix':time.time(),'command':argv});print(json.dumps({'pid':process.pid,'log':str(RUN/'worker.log')}));return
    code=Path(__file__).read_bytes();snapshot=RUN/'code_snapshots'/(extraction.digest(code)+'.py');snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(code)
    with (RUN/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ctx=context();indices=list(range(args.offset,min(args.offset+(args.limit or len(ctx['rows'])),len(ctx['rows']))));count=len(indices);cfg=replace(load_config(ROOT/'configs/experiment.toml'),timeout_seconds=600,max_retries=0,max_input_chars=600000)
        fingerprint={'input_sha256':extraction.digest(INPUT.read_bytes()),'asc_sha256':extraction.digest(CORPUS.read_bytes()),'system_sha256':sha(SYSTEM),
                     'figure_sha256':sha(stable_json(ctx['figure'])),'patterns_sha256':sha(stable_json(ctx['patterns'])),'model':cfg.model,'method':'row-wise-three-outputs-rule-obligation-audit-v1'}
        if (RUN/'manifest.json').exists() and load(RUN/'manifest.json')['fingerprint']!=fingerprint:raise ValueError('Run inputs/prompt changed; use a new output directory')
        save(RUN/'manifest.json',{'fingerprint':fingerprint,'input':str(INPUT),'asc_corpus':str(CORPUS),'row_count':len(ctx['rows'])})
        (RUN/'system_prompt.txt').write_text(SYSTEM)
        if args.report_only:print(json.dumps(report(ctx,count),ensure_ascii=False));return
        # Prepare all rows first to detect mapping/context failures before paying for calls.
        preflight=[]
        for i in indices:
            try:task=make_task(ctx,i);body=request(task,ctx,cfg)
            except ValueError as e:
                if str(e)!='No effective ASC rules on one side':raise
                preflight.append({'case_id':f'skill-{i+1:05d}','csv_row':i+2,'rules':0,'prompt_chars':0,'status':'SKIPPED_MISSING_ASC'});continue
            preflight.append({'case_id':task['case_id'],'csv_row':i+2,'rules':len(task['structured_asc_rules']),'prompt_chars':len(stable_json(body))})
        save(RUN/'preflight.json',preflight)
        print(json.dumps({'preflight_rows':count,'max_prompt_chars':max(x['prompt_chars'] for x in preflight),'workers':args.workers}),flush=True)
        if not args.execute:
            for i in indices[:3]:execute_one(i,ctx,cfg,False)
            return
        save(RUN/'execution_state.json',{'status':'RUNNING','pid':os.getpid(),'workers':args.workers,'scheduled':count,'started_unix':time.time()})
        completed=0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            fs={pool.submit(execute_one,i,ctx,cfg,True):i for i in indices}
            for future in as_completed(fs):
                i=fs[future]
                try:record=future.result()
                except Exception as e:
                    record={'case_id':f'skill-{i+1:05d}','csv_row':i+2,'status':'ERROR','error':f'{type(e).__name__}: {e}'};save(RUN/'results'/f"{record['case_id']}.json",record)
                completed+=1
                print(json.dumps({'completed_this_invocation':completed,'case_id':record['case_id'],'status':record['status']},ensure_ascii=False),flush=True)
                if completed%10==0 or completed==count:
                    summary=report(ctx,count)
                    if completed%1000==0:save(RUN/'milestones'/f'{completed:05d}.json',summary)
        summary=report(ctx,count);save(RUN/'execution_state.json',{'status':'PARTIAL_BATCH_FINISHED' if summary['pending'] else 'FINISHED_WITH_ERRORS' if summary['failed'] else 'FINISHED','pid':os.getpid(),'finished_unix':time.time()})
        print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
