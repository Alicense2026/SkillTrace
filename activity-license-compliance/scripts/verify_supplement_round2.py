"""Read-only validation of round-two inputs/results; generate traceable audit tables."""
import csv,json,sys,re
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_supplement_round2 import RUN,read,save,table,ORIGINALS,WORKBOOK,custom,ext,repository_id
from license_checker.llm.client import extract_text
from license_checker.llm.schema import parse_result
from license_checker.asc import validate_triple

def main():
    m=read(RUN/'manifest.json');before=read(RUN/'before_asc.json');after=read(ext.CORPUS)
    assert m['workbook_sha256']==ext.digest(WORKBOOK.read_bytes())
    assert m['input_sha256']==ext.digest(custom.INPUT.read_bytes())
    oldrules=before['rules'];oldids={r['rule_id'] for r in oldrules}
    # The historical corpus contains reused IDs for distinct clauses. Compare
    # the entire ordered records, not a dict that would silently lose duplicates.
    assert after['rules'][:len(oldrules)]==oldrules,'Historical ASC changed'
    newrules=after['rules'][len(oldrules):]
    newids={r['rule_id'] for r in newrules}
    assert len(newids)==len(newrules) and not newids.intersection(oldids)
    duplicate_counts=Counter(r['rule_id'] for r in oldrules)
    save(RUN/'historical_rule_id_collisions.json',{'note':'Pre-existing IDs retained; no new collisions introduced. Rule records are not deduplicated by ID in prompt loading.','duplicates':{k:n for k,n in duplicate_counts.items() if n>1}})
    sources={s['source_id']:s for s in after['sources']}
    assert all(s in after['sources'] for s in before['sources'])
    for r in after['rules']:
        if r['rule_id'] in oldids:continue
        validate_triple(r['ASC']);s=sources[r['license_source_id']];p=ORIGINALS/s['filename'];assert ext.digest(p.read_bytes())==s['sha256']
        lo,hi=map(int,re.fullmatch(r'L(\d+)-L(\d+)',r['clause_id']).groups());assert r['source_excerpt']=='\n'.join(p.read_text(encoding='utf-8-sig').splitlines()[lo-1:hi])
    for u in m['mappings']:assert ext.digest((ORIGINALS/u['filename']).read_bytes())==u['sha256']
    entries=[];diffs=[];stats=[];checked=0
    for name in ('repair','supplement'):
        out=RUN/name
        for p in sorted((out/'results').glob('*.json')):
            e=read(p);entries.append((name,e));cid=e['case_id']
            if e['status']=='SUCCESS':
                n=e['attempts'];req=read(out/'requests'/f'{cid}-attempt{n}.json');resp=read(out/'responses'/f'{cid}-attempt{n}.json');meta=req['metadata']
                assert ext.digest(json.dumps(req['body'],sort_keys=True,ensure_ascii=False).encode())==req['actual_request_sha256']
                a=parse_result(extract_text(resp),cid,meta['allowed_subjects'],meta['allowed_refs']);assert a==e['analysis'];assert meta['example_count']==12;checked+=1
                if name=='supplement':assert meta['structured_asc_sha256']==ext.digest(ext.CORPUS.read_bytes())
            for folder,field in [('license_license','license_license_findings'),('license_activity','license_behavior_findings'),('obligations','obligations')]:
                o=read(out/'three_outputs'/folder/p.name)
                assert o['case_id']==cid and o['output']==(e['analysis'][field] if e['status']=='SUCCESS' else None)
            if name=='repair' and e['status']=='SUCCESS':
                old=json.loads(extract_text(read(out/'original_outputs'/p.name)['response']));new=e['analysis']
                row={'case_id':cid,'关系数':e['relationship_weight'],'原校验错误':e['original_error'],'旧总体状态':old.get('overall_status'),'新总体状态':new['overall_status'],'旧义务数':len(old.get('obligations',[])),'新义务数':len(new['obligations']),'旧ASC数':len(old.get('asc_rules',[])),'新ASC数':len(new['asc_rules']),'旧LL发现数':len(old.get('license_license_findings',[])),'新LL发现数':len(new['license_license_findings']),'旧LA发现数':len(old.get('license_behavior_findings',[])),'新LA发现数':len(new['license_behavior_findings'])}
                diffs.append(row)
    table(RUN/'修复前后差异.csv',diffs)
    repairs=[e for c,e in entries if c=='repair']
    recovery=[]
    for reason in sorted({e['original_error'] for e in repairs}):
        es=[e for e in repairs if e['original_error']==reason]
        recovery.append({'原校验错误':reason,'原任务数':len(es),'原关系数':sum(e['relationship_weight'] for e in es),'修复成功任务数':sum(e['status']=='SUCCESS' for e in es),'恢复关系数':sum(e['relationship_weight'] for e in es if e['status']=='SUCCESS')})
    table(RUN/'错误类型恢复统计.csv',recovery)
    unresolved=[]
    for cohort,e in entries:
        if e['status']=='SUCCESS' and e['analysis']['overall_status']!='INCOMPLETE_ANALYSIS':continue
        unresolved.append({'实验':cohort,'case_id':e['case_id'],'CSV记录位置':e.get('source_csv_line','组合任务'),'仓库':e.get('row',{}).get('github_url',''),'资产':e.get('row',{}).get('artifact_name',''),'执行状态':e['status'],'总体状态':e.get('analysis',{}).get('overall_status',''),'原因':e.get('reason',''),'限制说明':json.dumps(e.get('analysis',{}).get('limitations',[]),ensure_ascii=False),'失败尝试记录':json.dumps(e.get('attempt_history',[]),ensure_ascii=False)})
    table(RUN/'未完成与不完整分析.csv',unresolved)
    for cohort in ('repair','supplement'):
        group=[e for name,e in entries if name==cohort and e['status']=='SUCCESS']
        for field in ('license_license_findings','license_behavior_findings'):
            states=sorted({f['status'] for e in group for f in e['analysis'][field]}|{'CONSTRAINT_CONFLICT','VIOLATION','POTENTIAL_CONFLICT','SCOPE_REVIEW_REQUIRED'})
            for status in states:
                relevant=[e for e in group if any(f['status']==status for f in e['analysis'][field])]
                stats.append({'实验':cohort,'类别':field,'类型':status,'任务数':len(relevant),'关系数':sum(e['relationship_weight'] for e in relevant),'发现条数':sum(f['status']==status for e in group for f in e['analysis'][field])})
    table(RUN/'冲突类型统计.csv',stats)
    with (RUN/'全部关系执行明细.csv').open(encoding='utf-8-sig')as f:ledger=list(csv.DictReader(f))
    assert len(ledger)==23206
    summary=read(RUN/'summary.json');assert Counter(r['执行状态'] for r in ledger)==summary['current_execution']
    assert len([1 for c,e in entries if c=='repair'])+summary['pending_repair_tasks']==15
    assert len([1 for c,e in entries if c=='supplement'])+summary['pending_supplement_rows']==43
    mapping=[]
    base={int(r['CSV记录位置']):r for r in read(RUN/'baseline_ledger.json')}
    for u in m['mappings']:
        es=[e for c,e in entries if c=='supplement' and repository_id(e['row']['github_url'])==u['repository']]
        s=next(s for s in after['sources'] if s['filename']==u['filename']);counts=Counter(e['status'] for e in es)
        mapping.append({'仓库':u['repository'],'许可证标签':u['license_label'],'原文文件':u['filename'],'ASC状态':s['status'],'ASC数':sum(r['license_source_id']==s['source_id'] for r in after['rules']),'关系数':len(es),'原成功数':sum(base[e['source_csv_line']]['执行状态']=='SUCCESS' for e in es),'本轮成功':counts['SUCCESS'],'本轮跳过':counts['SKIPPED'],'本轮失败':counts['ERROR'],'来源':u['acquisition']})
    table(RUN/'补充仓库与原文映射.csv',mapping)
    repair_ids={e['case_id'] for c,e in entries if c=='repair'}
    repaired_lines={int(r['CSV记录位置']) for r in base.values() if r['结果case_id'] in repair_ids}
    assert len(repaired_lines)==80
    assert not repaired_lines.intersection(m['affected_lines'])
    assert all(base[line]['执行状态']=='SKIPPED' for line in m['affected_lines'])
    verification={'passed':True,'unchanged_historical_rules':len(oldrules),'new_rules_source_validated':len(newrules),'preexisting_duplicate_id_excess':len(oldrules)-len(oldids),'new_duplicate_ids':0,'successful_responses_reparsed':checked,'three_output_files_checked':3*len(entries),'total_relationships':len(ledger),'repair_status_changes':sum(d['旧总体状态']!=d['新总体状态'] for d in diffs),'repair_obligation_count_changes':sum(d['旧义务数']!=d['新义务数'] for d in diffs),'pending':summary['pending_repair_tasks']+summary['pending_supplement_rows'],'repair_supplement_overlap':0,'reported_models':dict(Counter(e.get('reported_model') for c,e in entries if e['status']=='SUCCESS')),'request_attempts':dict(Counter(e.get('attempts',0) for c,e in entries if e['status']!='SKIPPED'))}
    save(RUN/'verification.json',verification)
    # Build a separate supplement to keep the primary report reproducible by the runner.
    lines=['# 第二轮结果核对与案例','','## 全量前后对照','','|处理状态|原实验|合并第二轮后|','|---|---:|---:|']
    for state in ('SUCCESS','ERROR','SKIPPED','EXCLUDED'):
        lines.append(f"|{state}|{summary['baseline_execution'].get(state,0)}|{summary['current_execution'].get(state,0)}|")
    lines+=['','补充组43条原先均为跳过，且与修复组80条没有重叠。实验覆盖的原始关系总数始终为23206。','', '|类型|成功|跳过|失败|','|---|---:|---:|---:|']
    for label,iscustom in [('自定义许可证',True),('非自定义许可证',False)]:
        subset=[r for r in ledger if ('自定义逐行' in r['统计渠道'])==iscustom and r['执行状态']!='EXCLUDED'];c=Counter(r['执行状态'] for r in subset)
        lines.append(f"|{label}|{c['SUCCESS']}|{c['SKIPPED']}|{c['ERROR']}|")
    lines+=['','## 逐仓库覆盖','','|仓库|ASC数|关系数|成功|跳过|失败|','|---|---:|---:|---:|---:|']
    for r in mapping:lines.append(f"|{r['仓库']}|{r['ASC数']}|{r['关系数']}|{r['本轮成功']}|{r['本轮跳过']}|{r['本轮失败']}|")
    lines+=['','## 冲突类型','','以下按任务及其关系权重分别计数。一个关系可以具有多个类型，列间不可相加。','','|实验|类别|类型|任务数|关系数|','|---|---|---|---:|---:|']
    for r in stats:lines.append(f"|{r['实验']}|{r['类别']}|{r['类型']}|{r['任务数']}|{r['关系数']}|")
    lines+=['','## 修复过程的语义变化','',f"15个任务中，总体状态变化 {verification['repair_status_changes']} 个，义务条目数变化 {verification['repair_obligation_count_changes']} 个；详见 `修复前后差异.csv`。格式修复不是确定性的JSON转换，模型可能同时修订适用范围。保留两版输出，结构校验通过不等于已证明全部义务语义等价。"]
    lines+=['','|原校验错误|任务数|关系数|恢复关系数|','|---|---:|---:|---:|']
    for r in recovery:lines.append(f"|{r['原校验错误']}|{r['原任务数']}|{r['原关系数']}|{r['恢复关系数']}|")
    lines+=['','已发现的内容变化包括：`chain-0073-e596a79bedcf` 将未证实复制行为下的MIT通知义务从独立义务列表移至适用范围说明，义务数从2减至1；`chain-2251-c50e14d5efa9` 重新细分商业许可/品牌相关条件，义务数从2增至3。两者总体状态均保持 OBLIGATIONS_OPEN。这是本轮模型响应的变化，不能表述为纯格式修复后语义逐字不变。']
    lines+=['','## 剩余失败、跳过与语义问题','']
    for r in unresolved:
        lines.append(f"- CSV第{r['CSV记录位置']}行，`{r['case_id']}`，{r['仓库']} / {r['资产']}：{r['执行状态']} {r['总体状态']}；{r['原因'] or r['限制说明']}")
    gemma_incomplete=[e for c,e in entries if c=='supplement' and e.get('analysis',{}).get('overall_status')=='INCOMPLETE_ANALYSIS' and 'gemma' in e.get('row',{}).get('artifact_name','').lower() and e['row']['artifact_license'].lower()=='apache-2.0']
    if gemma_incomplete:
        lines+=['','**输入约定与模型判定的一致性问题**：上述Gemma关系的输入已按用户明确规定映射为Apache-2.0，并提供对应原文和ASC。模型因 `provider_match` 为空再次质疑身份映射；该字段为空本身不证明标准许可证原文缺失。这属于模型对研究输入约定的执行问题，不应统计为新的许可证采集缺口。本轮保留其原始 INCOMPLETE_ANALYSIS 判定，不用离线规则改写为无冲突；后续若做语义纠正实验，应单独保留新请求与版本。']
    candidates=[e for c,e in entries if c=='supplement' and e['status']=='SUCCESS']
    chosen=[]
    for repo in ('rna4219/manual-bb-test-harness','fim-ai/fim-one','screenpipe/screenpipe'):
        e=next((e for e in candidates if repository_id(e['row']['github_url'])==repo),None)
        if e:chosen.append(e)
    lines+=['','## 补充案例','']
    for e in chosen:
        a=e['analysis'];r=e['row'];lines += [f"### {r['github_url']}",'',f"CSV第 {e['source_csv_line']} 行；资产 `{r['artifact_name']}`；{r['artifact_license']}；{r['integration']}；结果 `{a['overall_status']}`。",'']
        for field,label in [('license_license_findings','许可证—许可证'),('license_behavior_findings','许可证—行为')]:
            lines+=['',f'**{label}**','']
            if not a[field]:lines.append('模型未输出独立冲突发现条目（空数组）；条件限制见义务集合。这不等于证明全部义务已履行。')
            for f in a[field]:lines.append(f"- {f['activity']} / {f['status']}：{f['reason']}")
        lines+=['','**义务集合摘录**','']
        for o in a['obligations'][:5]:lines.append(f"- {o['requirement']}（适用性：{'未知' if o['applicability'] is None else o['applicability']}；履行状态：{o['fulfillment_status']}）")
        for l in a['limitations']:lines.append('- 范围限制：'+l)
        lines.append('')
    lines+=['## 统计口径','','本轮修复为15次原失败任务对应80条关系；补充任务按43条实际关系逐行执行。这两组在源CSV行上不得重复相加。全量合并以补充输入的新结果优先，其次为修复结果，最后保留历史结果。未成功或分析不完整均不并入完整无冲突样本。','',f"自动核验：{json.dumps(verification,ensure_ascii=False)}",'', '既有论文 evaluation 为上一轮冻结快照，本轮未静默改写论文统计。若更新论文，应同时替换全量统计表、缺口清单和方法中的版本说明。']
    lines+=['','核验同时发现历史语料中的规则ID不是全局唯一：5863条记录对应5701个ID，存在162个重复计数差额。它们在本轮之前已存在；本轮新增438条规则没有ID碰撞，历史5863条完整记录及顺序均保持不变。加载提示词按来源遍历规则记录，不按ID覆盖规则，因此本轮未通过删除旧规则来消除碰撞。明细见 `historical_rule_id_collisions.json`，后续语料版本应修正ID生成方式。']
    (RUN/'结果核对与案例.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(verification,ensure_ascii=False))
if __name__=='__main__':main()
