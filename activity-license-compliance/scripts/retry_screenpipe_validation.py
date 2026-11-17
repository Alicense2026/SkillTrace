"""Additional feedback repair for Screenpipe/Qwen; preserve round-two records."""
import csv,copy,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_supplement_round2 import execute_one,read,save,table,ext
from scripts.audit_all_16927 import verdict
from license_checker.llm.client import extract_text
from license_checker.llm.schema import parse_result
OLD=ROOT/'runs/supplement-repair-2026-11-12-round2'
OUT=ROOT/'runs/screenpipe-validation-followup-2026-11-12'
CID='chain-1391-c97465bfaf95'

def main():
    e=read(OLD/'supplement/results'/(CID+'.json'))
    req=read(OLD/'supplement/requests'/(CID+'-attempt1.json'))
    prior=read(OLD/'supplement/responses'/(CID+'-attempt2.json'))
    task=json.loads(req['body']['input'][0]['content'][0]['text'])['task']
    source=next(s for s in task['license_sources'] if s['side']=='upstream')
    assert source['file']=='aliyun.txt' and source['provider_match']=='aliyun-bailian'
    assert ext.digest((ROOT/'许可证原文/aliyun.txt').read_bytes())==source['sha256']
    assert req['metadata']['example_count']==12
    save(OUT/'original_case.json',{'result':e,'request':req,'last_response':prior})
    save(OUT/'manifest.json',{'case_id':CID,'source_csv_line':e['source_csv_line'],'prior_run':str(OLD),'prior_attempts':2,'upstream_source':source,'user_confirmation':'This Qwen asset uses the supplied Aliyun license; prior mapping already correct','reason':'Same Invalid obligation values / Unknown subject errors as the earlier 80 relationships','scope':'Only remaining validation ERROR; GLM already repaired, Gemma is semantic incompleteness, not schema failure'})
    req=copy.deepcopy(req)
    req['body']['instructions']+='\nThe user explicitly confirms that THIS Qwen asset uses the supplied Aliyun terms. The existing upstream aliyun.txt/provider aliyun-bailian mapping is correct. Do not request additional provider identity evidence. CombinedProduct is an object KIND, not an artifact identity suffix; use only the exact artifact identities in allowed_subjects. This clarification does not establish any otherwise unknown commercial, distribution or fulfillment facts.'
    e.update(cohort='ADDITIONAL_VALIDATION_REPAIR',original_error=e['reason'],prior_attempts=2)
    result=execute_one(OUT,e,req,extract_text(prior),e['reason'])
    if result['status']=='SUCCESS':
        n=result['attempts'];q=read(OUT/'requests'/f'{CID}-attempt{n}.json');raw=read(OUT/'responses'/f'{CID}-attempt{n}.json')
        assert parse_result(extract_text(raw),CID,q['metadata']['allowed_subjects'],q['metadata']['allowed_refs'])==result['analysis']
        for folder,field in [('license_license','license_license_findings'),('license_activity','license_behavior_findings'),('obligations','obligations')]:
            assert read(OUT/'three_outputs'/folder/(CID+'.json'))['output']==result['analysis'][field]
    with (OLD/'全部关系执行明细.csv').open(encoding='utf-8-sig')as f:rows=list(csv.DictReader(f))
    hits=[r for r in rows if r['结果case_id']==CID];assert len(hits)==1
    r=hits[0];before=copy.deepcopy(r);a=result.get('analysis',{})
    r.update({'执行状态':result['status'],'汇总判定':verdict(result),'模型原始总体状态':a.get('overall_status',''),'义务数':len(a.get('obligations',[])),'失败或跳过原因':result.get('reason',''),'统计渠道':r['统计渠道']+' / 校验追加修复'})
    assert len(rows)==23206
    table(OUT/'全部关系执行明细.csv',rows)
    summary={'case_id':CID,'source_csv_line':e['source_csv_line'],'status':result['status'],'overall_status':a.get('overall_status'),'additional_attempts':result.get('attempts'),'total_case_attempts':2+result.get('attempts',0),'obligations':len(a.get('obligations',[])),'execution':dict(Counter(r['执行状态'] for r in rows)),'verdict':dict(Counter(r['汇总判定'] for r in rows)),'reported_model':result.get('reported_model'),'validation_passed':result['status']=='SUCCESS','before_row':before,'after_row':r}
    save(OUT/'summary.json',summary)
    lines=['# Screenpipe 校验追加修复','','Qwen资产已确认使用阿里云原文；核验旧请求本来就是aliyun.txt（28条匹配ASC），因此没有替换许可证或将错误归因于缺原文。原请求中的12个Figure 10案例继续保留。','','原失败链：第一次 Invalid obligation values（requirement被写成条件对象而非字符串）；第二次 Unknown subject（artifact写成了case_id:CombinedProduct）。本次使用完整旧任务、最后一次原始响应和精确字段诊断进行追加反馈；不通过删除义务或离线修改判断强制通过。','',f"本次执行状态：{result['status']}；模型总体状态：{a.get('overall_status','未取得有效输出')}；新增尝试：{result.get('attempts')}；该任务累计尝试：{2+result.get('attempts',0)}。",'', '## 其他两个案例的区别','','- GLM：chain-1389-e6526a1e0c17 曾出现 Unknown subject 与 Unknown evidence reference，和此前80条错误类型相同，已在上一轮第二次请求成功修复为 OBLIGATIONS_OPEN，不重复调用。','- Gemma：chain-1394-1d3fbe20d3c4 已通过结构校验，但模型因provider_match为空质疑既定的Gemma→Apache-2.0对应关系而返回 INCOMPLETE_ANALYSIS。这是输入约定执行/语义问题，不属于80条的校验错误。本次保留原判，未混入格式修复成功数。','','## 全量合并统计','','|状态|关系数|','|---|---:|']
    for k,v in summary['execution'].items():lines.append(f'|{k}|{v}|')
    lines+=['','|判定|关系数|','|---|---:|']
    for k,v in summary['verdict'].items():lines.append(f'|{k}|{v}|')
    lines+=['','成功返回包含分析不完整，不等同于全部已确认合规。旧轮次未覆盖；本目录的全部关系执行明细.csv是合并该次修复后的版本。','','## 本案例义务集合','']
    for o in a.get('obligations',[]):lines.append('- '+o['requirement']+'；履行状态：'+o['fulfillment_status'])
    for l in a.get('limitations',[]):lines.append('- 范围限制：'+l)
    (OUT/'追加实验报告.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('before_row','after_row')},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
