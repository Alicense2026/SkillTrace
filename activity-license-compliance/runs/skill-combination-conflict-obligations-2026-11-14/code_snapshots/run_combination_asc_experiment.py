"""Group equivalent frozen ASC/fact contexts; retain representative provenance."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from scripts import run_skill_asc_experiment as b

RUN=b.ROOT/'runs/skill-combination-conflict-obligations-2026-11-14'
OLD=b.ROOT/'runs/skill-conflict-obligations-2026-11-14'

def key(task):
    def normalize(value):
        if isinstance(value,dict):return {k.replace(task['case_id'],'ARTIFACT'):normalize(v) for k,v in value.items() if k!='evidence_refs'}
        if isinstance(value,list):return [normalize(v) for v in value]
        if isinstance(value,str):return value.replace(task['case_id'],'ARTIFACT')
        return value
    return b.sha(b.stable_json(normalize({'rules':task['structured_asc_rules'],'facts':task['facts_by_subject'],'graph':task['object_graph'],
        'integration':task['trusted_row']['调用方式'],'modified':task['trusted_row']['是否修改']})))

def summarize(ctx,groups,skips):
    counts=Counter();weighted=Counter();statuses=Counter();obligations=0;done=0;reused=0
    for g in groups:
        p=RUN/'results'/f"{g['representative_case_id']}.json"
        if not p.exists():counts['PENDING']+=1;weighted['PENDING']+=len(g['members']);continue
        r=b.load(p);counts[r['status']]+=1;weighted[r['status']]+=len(g['members'])
        if r['status']=='SUCCESS':
            done+=1;reused+=bool(g.get('reused_from'));statuses[r['analysis']['overall_status']]+=1;obligations+=len(r['analysis']['obligations'])
        b.save(RUN/'combination_results'/f"{g['combination_id']}.json",{'combination_id':g['combination_id'],'result_file':str(p),'status':r['status'],'member_csv_rows':[m['csv_row'] for m in g['members']], 'reused_from':g.get('reused_from')})
    summary={'input_relationships':len(ctx['rows']),'analyzable_combinations':len(groups),'execution_counts':dict(counts),'relationship_execution_counts':dict(weighted),'skipped_relationships':len(skips),'reused_successful_combinations':reused,'overall_combination_counts':dict(statuses),'obligation_items_unweighted':obligations,'updated_unix':time.time()}
    b.save(RUN/'summary.json',summary)
    lines=['# 许可证组合冲突检测与义务聚合实验','',f"输入 {len(ctx['rows'])} 条；有效组合 {len(groups)}；成功 {done}；待执行 {counts['PENDING']}；失败 {counts['ERROR']}；缺失 ASC 跳过 {len(skips)} 条。",f"成功组合中 {reused} 组复用前次有效输出。",'', '以完整有效 ASC、上下游方向、调用/修改方式及已知事实归并，忽略仓库名。原文版本、自定义许可适用段落、修改事实不同不合并。', '每组保留代表关系的原始请求、响应与三类输出。逐行索引引用代表结果，不伪造对每行独立调用。旧失败响应不视为可复用结果。', '组合计数与按组合成员数加权的关系计数须分别报告；同组重复关系不是独立 LLM 实验。义务条款数在此按组合计数，不能当作逐行总数。', '', '|组合总体状态|组合数|','|---|---:|']
    lines += [f'|{k}|{v}|' for k,v in sorted(statuses.items())]
    lines += ['', '## 冲突案例（最多三组）']
    n=0
    for g in groups:
        p=RUN/'results'/f"{g['representative_case_id']}.json"
        if not p.exists():continue
        r=b.load(p)
        if r['status']!='SUCCESS':continue
        findings=[f for field in ('license_license_findings','license_behavior_findings') for f in r['analysis'][field] if f['status'] in {'VIOLATION','CONSTRAINT_CONFLICT','POTENTIAL_CONFLICT'}]
        if findings and n<3:
            n+=1;lines += ['',f"### {g['combination_id']}（{len(g['members'])} 条关系）"]+[f"- {f['status']} / {f['activity']}：{f['reason']}" for f in findings[:3]]
    (RUN/'实验结果报告.md').write_text('\n'.join(lines)+'\n')
    return summary

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--background',action='store_true');ap.add_argument('--workers',type=int,default=6);args=ap.parse_args()
    RUN.mkdir(parents=True,exist_ok=True)
    if args.background:
        if not args.execute:raise ValueError('background needs execute')
        cmd=[sys.executable,'-u',str(b.ROOT/'scripts/run_skill_asc_experiment.py'),'--combinations',*[x for x in sys.argv[1:] if x not in {'--combinations','--background'}]]
        with (RUN/'worker.log').open('ab') as log:p=subprocess.Popen(cmd,cwd=b.ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        b.save(RUN/'launcher.json',{'pid':p.pid,'started_unix':time.time()});print(json.dumps({'pid':p.pid,'run':str(RUN)}));return
    with (RUN/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Never overlap the old row-wise experiment.
        with (OLD/'run.lock').open('a') as oldlock:fcntl.flock(oldlock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ctx=b.context();grouped={};skips=[];successful={}
        for p in sorted((OLD/'results').glob('*.json')):
            r=b.load(p)
            if r['status']=='SUCCESS':successful[r['csv_row']-2]=r
        for i in range(len(ctx['rows'])):
            try:t=b.make_task(ctx,i)
            except ValueError as e:
                if str(e)!='No effective ASC rules on one side':raise
                skips.append({'csv_row':i+2,'case_id':f'skill-{i+1:05d}','status':'SKIPPED_MISSING_ASC','reason':str(e)});continue
            k=key(t);g=grouped.setdefault(k,{'key':k,'members':[],'candidates':[]})
            g['members'].append({'csv_row':i+2,'case_id':t['case_id'],'source_excel_row':t['source_excel_row']})
            if i in successful:
                r=successful[i];b.validate(json.dumps(r['analysis'],ensure_ascii=False),t)
                cfg=replace(b.load_config(b.ROOT/'configs/experiment.toml'),max_input_chars=600000)
                if r.get('request_sha256')==b.sha(b.stable_json(b.request(t,ctx,cfg))):g['candidates'].append(i)
        groups=list(grouped.values());b.RUN=RUN
        for n,g in enumerate(groups,1):
            i=g['candidates'][0] if g['candidates'] else g['members'][0]['csv_row']-2
            g.update(combination_id=f'combo-{n:04d}',representative_index=i,representative_case_id=f'skill-{i+1:05d}')
            if g['candidates']:
                r=successful[i];g['reused_from']=str(OLD/'results'/f"{r['case_id']}.json")
                b.save(RUN/'results'/f"{r['case_id']}.json",r);b.publish_three(r)
                source=OLD/'requests'/f"{r['case_id']}.json"
                if source.exists():b.save(RUN/'requests'/source.name,b.load(source))
        b.save(RUN/'combinations.json',groups);b.save(RUN/'skipped_relationships.json',skips)
        b.save(RUN/'relationship_index.json',[{'csv_row':m['csv_row'],'case_id':m['case_id'],'combination_id':g['combination_id'],'representative_case_id':g['representative_case_id'],'result_file':str(RUN/'results'/f"{g['representative_case_id']}.json"),'three_outputs':{s:str(RUN/'three_outputs'/s/f"{g['representative_case_id']}.json") for s in ('license_license','license_activity','obligations')}} for g in groups for m in g['members']]+skips)
        b.save(RUN/'manifest.json',{'input_sha256':b.extraction.digest(b.INPUT.read_bytes()),'asc_sha256':b.extraction.digest(b.CORPUS.read_bytes()),'system_sha256':b.sha(b.SYSTEM),'grouping':'effective ASC + known facts + object graph + integration + modification; repository identity excluded','old_successful_rows':len(successful),'source_run':str(OLD)})
        (RUN/'system_prompt.txt').write_text(b.SYSTEM)
        summary=summarize(ctx,groups,skips);print(json.dumps(summary,ensure_ascii=False),flush=True)
        if not args.execute:return
        b.save(RUN/'execution_state.json',{'status':'RUNNING','pid':os.getpid(),'workers':args.workers,'started_unix':time.time(),'combinations':len(groups)})
        cfg=replace(b.load_config(b.ROOT/'configs/experiment.toml'),timeout_seconds=600,max_retries=0,max_input_chars=600000)
        pending=[g for g in groups if not (RUN/'results'/f"{g['representative_case_id']}.json").exists() or b.load(RUN/'results'/f"{g['representative_case_id']}.json")['status']!='SUCCESS']
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(b.execute_one,g['representative_index'],ctx,cfg,True):g for g in pending}
            for f in as_completed(futures):
                g=futures[f]
                try:r=f.result()
                except Exception as e:
                    r={'case_id':g['representative_case_id'],'status':'ERROR','error':str(e)};b.save(RUN/'results'/f"{r['case_id']}.json",r)
                print(json.dumps({'combination_id':g['combination_id'],'status':r['status']},ensure_ascii=False),flush=True);summary=summarize(ctx,groups,skips)
        b.save(RUN/'execution_state.json',{'status':'FINISHED_WITH_ERRORS' if summary['execution_counts'].get('ERROR') else 'FINISHED','finished_unix':time.time(),'pid':os.getpid()})
