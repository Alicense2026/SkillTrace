"""Explicit, source-reviewed repairs; never alter archived API responses."""
import json
import time
import fcntl
from copy import deepcopy
from scripts import run_skill_asc_experiment as b
from scripts import run_combination_asc_experiment as combo


def main():
    p=combo.RUN;b.RUN=p
    with (p/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        repair_dir=p/'targeted_repairs'/'two-source-reviewed-repairs';repair_dir.mkdir(parents=True,exist_ok=True)
        prepared=[]
        for cid in ['skill-01103','skill-04047']:
            result_path=p/'results'/f'{cid}.json';old=b.load(result_path)
            if old.get('repair_method')=='assistant_source_reviewed_targeted_v1':continue
            assert old['status']=='ERROR'
            task=json.loads(b.load(p/'requests'/f'{cid}.json')['body']['input'])['task']
            response_path=max((p/'responses').glob(cid+'-*.json'),key=lambda f:f.stat().st_mtime)
            raw=b.load(response_path);data=json.loads(b.extract_text(raw));before=deepcopy(data)
            rules={r['rule_ref']:r for r in task['structured_asc_rules']}
            if cid=='skill-01103':
                assert len(data['obligations'])==5
                rule=rules['U044'];excerpt=task['clause_excerpts'][rule['source_excerpt_ref']]
                assert '不得以任何可能导致' in excerpt['text']
                obligation={'activity':'Use','subject':deepcopy(rule['triple']['S']),
                    'requirement':'用户不得以可能导致阿里云产品服务或其任何部分受开源软件许可协议约束的方式使用或部署该服务，包括导致该服务或其部分被要求以源代码形式披露或分发、以制作衍生作品为目的许可，或允许免费再分发的情形。仅远程调用及下游采用 AGPL 不足以证明已触发该禁止。',
                    'trigger':rule['triple']['C']['when'],'applicability':None,'fulfillment_status':'UNKNOWN',
                    'unresolved_predicates':[rule['triple']['C']['when']], 'source_refs':[rule['source_ref']]}
                data['obligations'].insert(2,obligation)
                assert data['obligations'][:2]+data['obligations'][3:]==before['obligations']
                # Restore omitted duty: existing audit positions now match all four distinct duties.
                for ref,idx in [('U044',2),('U112',3),('U115',4),('D050',5)]:
                    a=next(a for a in data['rule_obligation_audit'] if a['rule_ref']==ref)
                    assert a['obligation_indices']==[idx]
                changes={'type':'restore_omitted_obligation','insert_index':2,'source_rule':'U044','source_excerpt':excerpt,
                         'reason':'Source §8.3 duty absent from obligations, while audit retained its index; insertion restores U044/U112/U115/D050 alignment. Original five obligations and audit unchanged.'}
            else:
                correct='license:9aad0d3a4b54a45115654500b18bf1fcd76c34337471c99d4b55cbeb04c7cec8'
                wrong='license:9aad0d3a4b54a45115654500b18bf1fcd76c34337471c99d4d55cbeb04c7cec8'
                assert correct in task['allowed_source_refs'] and wrong not in task['allowed_source_refs']
                edits=[]
                def fix(value,path=''):
                    if isinstance(value,dict):
                        for k,v in value.items():
                            if k=='source_refs':
                                for i,ref in enumerate(v):
                                    if ref==wrong:v[i]=correct;edits.append(f'{path}.{k}[{i}]')
                            else:fix(v,path+'.'+k)
                    elif isinstance(value,list):
                        for i,v in enumerate(value):fix(v,path+f'[{i}]')
                fix(data);assert len(edits)==8
                changes={'type':'exact_source_identifier_correction','wrong':wrong,'correct':correct,'paths':edits,'reason':'Single-character transcription error; exact source identified by frozen task and Anthropic obligation text.'}
            analysis=b.validate(json.dumps(data,ensure_ascii=False),task)
            for field in ('license_license_findings','license_behavior_findings','overall_status','review_items','limitations'):
                assert analysis[field]==before[field]
            record={**old,'status':'SUCCESS','analysis':analysis,'raw_response':str(response_path),'usage':raw.get('usage',{}),'model':raw.get('model'),
                    'repair_method':'assistant_source_reviewed_targeted_v1','repair_log':str(repair_dir/f'{cid}-repair.json'),
                    'repaired_unix':time.time(),'prior_error':old['error']}
            record.pop('error',None)
            prepared.append((cid,old,record,changes,analysis))
        # Validate both completely before publishing either.
        for cid,old,record,changes,analysis in prepared:
            b.save(repair_dir/f'{cid}-before.json',old)
            b.save(repair_dir/f'{cid}-repair.json',{'case_id':cid,'method':'assistant source review, not a new GPT-6-luna response','changes':changes,'validation':'full b.validate passed; conflict findings, status and original obligations preserved','raw_response':record['raw_response']})
            b.save(repair_dir/f'{cid}-repaired-analysis.json',analysis)
            b.save(p/'results'/f'{cid}.json',record);b.publish_three(record)
            # Make post-processing visible in each exported output, not just main record.
            for folder in ('license_license','license_activity','obligations'):
                f=p/'three_outputs'/folder/f'{cid}.json';out=b.load(f)
                out.update(repair_method=record['repair_method'],repair_log=record['repair_log']);b.save(f,out)
        ctx=b.context();summary=combo.summarize(ctx,b.load(p/'combinations.json'),b.load(p/'skipped_relationships.json'))
        assert summary['execution_counts']=={'SUCCESS':257}
        b.save(p/'execution_state.json',{'status':'FINISHED','finished_unix':time.time(),'completion_method':'255 API-valid combinations + 2 explicitly source-reviewed postprocessed combinations'})
        note='\n\n## 定向后处理修复说明\n\n257 个组合中，255 个通过既有 API 输出校验；2 个在保留 API 原始响应的基础上，经本会话助手按原文进行定向修复后通过校验，并非两次新的 GPT-6-luna 成功调用，也非人类专家评审。combo-0120 补回遗漏的阿里云第 8.3 条条件性禁止义务，恢复既有索引关系；combo-0203 精确修正 8 处相同来源哈希笔误。冲突结论未改写。详见 targeted_repairs/two-source-reviewed-repairs。格式和来源校验通过不代表语义覆盖已获独立专家验证。\n'
        report=p/'实验结果报告.md';report.write_text(report.read_text()+note)
        (repair_dir/'修复说明.md').write_text('# 两组失败输出修复\n'+note)
        print(json.dumps({'repaired':len(prepared),'execution_counts':summary['execution_counts'],'skipped_relationships':summary['skipped_relationships']},ensure_ascii=False))

if __name__=='__main__':main()
