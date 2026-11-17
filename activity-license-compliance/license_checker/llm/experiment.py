"""可复现实验编排：dry-run、逐条落盘、失败记录、断点续跑；建议不自动入库。"""
import json
import platform
import time
from pathlib import Path
from ..input_files import load_input
from ..asc import OBJECTS
from ..asc_rules import ACTIVITIES
from .config import load_config
from .prompting import build_request, stable_json, sha, load_cases, ASC_CORPUS_PATH, RESOURCES
from .client import ResponsesClient, APIError, extract_text
from .schema import parse_result, output_contract
from .casebook import compact_figure_cases, load_patterns, compact_patterns
from .license_sources import is_lgpl_row, source_manifest
from ..identity import case_id


def _subject_key(subject):
    return json.dumps(subject,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def prepare_llm_case(row,index,source):
    """Build trusted behavior facts without running the offline license engine."""
    cid=case_id(row,index);ref=f'{source}#/rows/{index}'
    up_id,down_id=cid+':upstream',cid+':downstream'
    remote=row['integration']=='远程服务调用'
    modified=row.get('modified')=='是'
    if row.get('integration') not in {'远程服务调用','代码层面集成'}:
        raise ValueError('Unsupported integration')
    if row.get('modified') not in {'是','否','\\','','未知','无法确定'}:
        raise ValueError('Unsupported modified value')
    allowed=[{'artifact':asset,'kind':kind} for asset in (up_id,down_id) for kind in OBJECTS]
    facts={_subject_key(s):{'activity:'+a:{'value':None,'evidence_refs':[],'derivation':'NOT_PROVIDED'} for a in ACTIVITIES} for s in allowed}
    original=_subject_key({'artifact':up_id,'kind':'OriginalArtifact'})
    facts[original]['activity:Use']={'value':True,'evidence_refs':[ref],'derivation':'TRUSTED_CHAIN_USE'}
    if remote:
        facts[original]['activity:RemoteInteraction']={'value':True,'evidence_refs':[ref],'derivation':'TRUSTED_REMOTE_CALL'}
        facts[original]['activity:Link']={'value':True,'evidence_refs':[ref],'derivation':'API_LINK_RELATION_NOT_LEGAL_DERIVATION'}
    else:
        facts[original]['activity:Copy']={'value':True,'evidence_refs':[ref],'derivation':'SOURCE_INCORPORATION'}
    if modified:
        facts[original]['activity:Modify']={'value':True,'evidence_refs':[ref],'derivation':'TRUSTED_MODIFIED_COPY'}
    elif row.get('modified')=='否':
        facts[original]['activity:Modify']={'value':False,'evidence_refs':[ref],'derivation':'TRUSTED_UNMODIFIED'}
    nodes=[{'artifact':up_id,'kind':'OriginalArtifact'},
           {'artifact':down_id,'kind':'CombinedProduct'}]
    tags={'LINK':True if remote else None,'REMOTE_CALL':True if remote else None,
          'DEPENDENCY':None,'BUNDLE':None,'MODIFIED_COPY':True if modified else None,
          'COMBINED_PRODUCT':True if not remote else None}
    graph={'primary_relation':'LINK' if remote else 'BUNDLE',
           'primary_relation_meaning':'API调用/加载关系' if remote else '代码纳入关系（不等于已发布打包物）',
           'nodes':nodes,'edges':[{'from':down_id,'to':up_id,'type':kind,'status':value,
                                    'evidence_refs':[ref] if value is not None else []} for kind,value in tags.items()],
           'scope_shared':None,'scope_note':'API/代码纳入均不直接证明两份许可约束同一对象；所有活动仍进行条件性条款比较。'}
    prompt_row=row.get('_aggregate_prompt_row',row)
    return {'case_id':cid,'row_number':index+1,'row':row,'prompt_row':prompt_row,
            'aggregate_weight':row.get('_aggregate_weight'),'source_ref':ref,
            'upstream_id':up_id,'downstream_id':down_id,'allowed_subjects':allowed,
            'facts_by_subject':facts,'object_graph':graph,'canonical_activities':list(ACTIVITIES)+['TrainModel']}


def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)


def save_three_outputs(out,cid,analysis,aggregate_count=None):
    for folder,field in (('license_license','license_license_findings'),
                         ('license_activity','license_behavior_findings'),('obligations','obligations')):
        record={'case_id':cid,'output':analysis[field]}
        if aggregate_count is not None:record['aggregate_count']=aggregate_count
        save(Path(out)/'three_outputs'/folder/f'{cid}.json',record)


def write_paper_report(out,summary,total_rows):
    results=[]
    for path in sorted((Path(out)/'results').glob('*.json')):
        try:
            record=json.loads(path.read_text(encoding='utf-8'))
            if record.get('status')=='SUCCESS':results.append(record)
        except (OSError,ValueError):
            continue
    overall={}; ll={}; lb={}; obligations={}
    overall_weighted={}; ll_weighted={}; lb_weighted={}; obligations_weighted={}
    for result in results:
        analysis=result['analysis']
        weight=result.get('aggregate_count',1)
        overall[analysis['overall_status']]=overall.get(analysis['overall_status'],0)+1
        overall_weighted[analysis['overall_status']]=overall_weighted.get(analysis['overall_status'],0)+weight
        for finding in analysis['license_license_findings']:
            ll[finding['status']]=ll.get(finding['status'],0)+1
            ll_weighted[finding['status']]=ll_weighted.get(finding['status'],0)+weight
        for finding in analysis['license_behavior_findings']:
            lb[finding['status']]=lb.get(finding['status'],0)+1
            lb_weighted[finding['status']]=lb_weighted.get(finding['status'],0)+weight
        for obligation in analysis['obligations']:
            status=obligation['fulfillment_status']
            obligations[status]=obligations.get(status,0)+1
            obligations_weighted[status]=obligations_weighted.get(status,0)+weight
    lines=['# 供应链许可证冲突检测实验报告','',
           f"- 运行模式：{summary['mode']}；模型：{summary['model']}",
           f"- 输入记录：{total_rows}；本次选中：{summary['selected_cases']}；已处理：{summary['processed']}",
           f"- 成功：{summary['success']}；失败：{summary['errors']}；未知/未结构化许可证排除：{summary.get('skipped_unknown_license_rows',0)}；LGPL排除：{summary['skipped_lgpl_rows']}",
           *( [f"- 代表供应链关系：{summary['input_relationships']}；成功覆盖：{summary['success_relationships']}；未知/未结构化许可证跳过：{summary['skipped_unknown_license_relationships']}；LGPL跳过：{summary['skipped_lgpl_relationships']}"] if summary.get('input_format')=='license_combination_csv' else [] ),
           f"- ASC语料 SHA-256：{summary['structured_asc_sha256']}",
           '- 方法：以许可证组合统计 CSV 为输入，对具有完整已纳入 ASC 原文的分组逐组分析；同组数量仅作代表关系数用于加权统计，不作为法律证据。每个请求注入 Figure 10 的 12 个案例和冲突模式。未调用离线冲突判定引擎或许可证对缓存。',
           '- 状态说明：只有 SUCCESS 响应纳入统计；ERROR、未运行行不计为合规或无冲突。结构化 ASC 的原文匹配仍标记 FIRST_PASS_REVIEW_REQUIRED。','',
           '## 冲突数量与类型统计','',
           '| 输出类别 | 类型/状态 | 数量（成功响应） |','|---|---|---:|']
    metrics=[('License-License','CONSTRAINT_CONFLICT',ll.get('CONSTRAINT_CONFLICT',0)),
             ('License-License','POTENTIAL_CONFLICT',ll.get('POTENTIAL_CONFLICT',0)),
             ('License-License','CONDITIONS_TO_INHERIT',ll.get('CONDITIONS_TO_INHERIT',0)),
             ('License-Activity','VIOLATION',lb.get('VIOLATION',0)),
             ('License-Activity','POTENTIAL_CONFLICT',lb.get('POTENTIAL_CONFLICT',0)),
             ('License-Activity','SCOPE_REVIEW_REQUIRED',lb.get('SCOPE_REVIEW_REQUIRED',0)),
             ('义务集合','NOT_FULFILLED',obligations.get('NOT_FULFILLED',0)),
             ('义务集合','UNKNOWN',obligations.get('UNKNOWN',0)),
             ('义务集合','FULFILLED',obligations.get('FULFILLED',0))]
    for category,status,count in metrics:lines.append(f'| {category} | {status} | {count} |')
    for category,counts in (('License-License其他状态',ll),('License-Activity其他状态',lb),('总体判定',overall)):
        for status,count in sorted(counts.items()):
            if category.endswith('其他状态') and status in {'CONSTRAINT_CONFLICT','POTENTIAL_CONFLICT','CONDITIONS_TO_INHERIT','VIOLATION','SCOPE_REVIEW_REQUIRED'}:continue
            lines.append(f'| {category} | {status} | {count} |')
    if summary.get('input_format')=='license_combination_csv':
        lines += ['', '### 按代表供应链关系数加权','','| 输出类别 | 类型/状态 | 关系数 |','|---|---|---:|']
        weighted_metrics=[('License-License','CONSTRAINT_CONFLICT',ll_weighted.get('CONSTRAINT_CONFLICT',0)),
                          ('License-License','POTENTIAL_CONFLICT',ll_weighted.get('POTENTIAL_CONFLICT',0)),
                          ('License-License','CONDITIONS_TO_INHERIT',ll_weighted.get('CONDITIONS_TO_INHERIT',0)),
                          ('License-Activity','VIOLATION',lb_weighted.get('VIOLATION',0)),
                          ('License-Activity','POTENTIAL_CONFLICT',lb_weighted.get('POTENTIAL_CONFLICT',0)),
                          ('License-Activity','SCOPE_REVIEW_REQUIRED',lb_weighted.get('SCOPE_REVIEW_REQUIRED',0)),
                          ('义务集合','NOT_FULFILLED',obligations_weighted.get('NOT_FULFILLED',0)),
                          ('义务集合','UNKNOWN',obligations_weighted.get('UNKNOWN',0)),
                          ('义务集合','FULFILLED',obligations_weighted.get('FULFILLED',0))]
        for category,status,count in weighted_metrics:lines.append(f'| {category} | {status} | {count} |')
    if not results:lines.append('\n统计数为0是因为当前没有成功模型响应，不代表已确认不存在冲突。')
    lines += ['', '## 冲突案例分析', '']
    examples=[]
    for result in results:
        a=result['analysis']; conflicts=[x for x in a['license_license_findings']+a['license_behavior_findings'] if x['status'] in {'CONSTRAINT_CONFLICT','POTENTIAL_CONFLICT','VIOLATION'}]
        if conflicts:examples.append((result,conflicts))
    for n,(result,conflicts) in enumerate(examples[:3],1):
        lines.append(f"### 案例 {n}：{result['case_id']}（代表 {result.get('aggregate_count',1)} 条关系）")
        for finding in conflicts[:4]:lines.append(f"- **{finding['status']} / {finding['activity']}**：{finding['reason']}")
        lines.append('')
    if not examples:lines.append('当前成功结果中没有可供分析的已报告冲突；若成功结果数为零，本报告不构成检测结论。')
    if summary['errors'] or summary['processed']<summary['selected_cases']:
        lines += ['', '## 完整性限制','',
                  f"本次未完成全量输入检查：处理 {summary['processed']} / 选中 {summary['selected_cases']} 行，失败 {summary['errors']} 行。未处理行不得解释为无冲突。"]
    Path(out,'final_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def run_experiment(input_path,output_dir,config_path,limit=1,offset=0,execute=False,client=None):
    if type(limit) is not int or limit<=0 or type(offset) is not int or offset<0:raise ValueError('limit > 0 and offset >= 0 required')
    config=load_config(config_path)
    payload,source=load_input(input_path)
    rows=payload['rows']
    row_indices=list(range(offset,min(offset+limit,len(rows))))
    skipped_lgpl=[i for i in row_indices if is_lgpl_row(rows[i])]
    skipped_unknown=[i for i in row_indices if i not in set(skipped_lgpl) and rows[i].get('_aggregate_skip_reason')]
    skipped_set=set(skipped_lgpl)|set(skipped_unknown)
    selected_indices=[i for i in row_indices if i not in skipped_set]
    if not selected_indices:raise ValueError('Selected range contains no analyzable records')
    out=Path(output_dir)
    fingerprint={'schema_version':'experiment-2.2-structured-asc','input_sha256':sha(stable_json(payload)),
                 'config':config.public_dict(),'offset':offset,'limit':limit,
                 'structured_asc_sha256':sha(ASC_CORPUS_PATH.read_text(encoding='utf-8')),
                 'case_ids':[case_id(rows[i],i) for i in selected_indices],
                 'skipped_lgpl_rows':[i+1 for i in skipped_lgpl],
                 'skipped_unknown_license_rows':[i+1 for i in skipped_unknown],
                 'license_originals':source_manifest(),
                 'cases_sha256':sha(stable_json(load_cases())),
                 'casebook_sha256':sha(stable_json(compact_figure_cases(load_cases()))),
                 'patterns_sha256':sha(stable_json(compact_patterns(load_patterns()))),
                 'output_contract_sha256':sha(stable_json(output_contract())),
                 'system_sha256':sha((RESOURCES/'llm_system.txt').read_text(encoding='utf-8'))}
    manifest_path=out/'manifest.json'
    if manifest_path.exists():
        old=json.loads(manifest_path.read_text(encoding='utf-8'))
        if old['fingerprint']!=fingerprint:raise ValueError('Run configuration/input/prompt changed; choose a new output directory')
    else:save(manifest_path,{'fingerprint':fingerprint,'python':platform.python_version(),
                             'platform':platform.platform(),'model_suggestions_auto_applied':False})
    skipped_records=[]
    for i in skipped_lgpl:
        skipped_records.append({'case_id':case_id(rows[i],i),'input_group_row':i+1,
                                'status':'SKIPPED_LGPL','aggregate_count':rows[i].get('_aggregate_weight',1),
                                'reason':'LGPL excluded by experiment instruction'})
    for i in skipped_unknown:
        skipped_records.append({'case_id':case_id(rows[i],i),'input_group_row':i+1,
                                'status':'SKIPPED_UNKNOWN_LICENSE','aggregate_count':rows[i].get('_aggregate_weight',1),
                                'reason':rows[i].get('_aggregate_skip_reason')})
    if skipped_records:save(out/'skipped_rows.json',skipped_records)
    # Live mode requires explicit flag; a fake client can be injected by tests only.
    if execute and client is None:
        config.api_key();client=ResponsesClient(config)
    records=[];stop=False
    for index,i in enumerate(selected_indices):
        cid=case_id(rows[i],i)
        try:
            case=prepare_llm_case(rows[i],i,str(source))
            inventory={case['source_ref']:{'kind':'TRUSTED_CHAIN_RECORD','raw_record':case['prompt_row']}}
            cid=case['case_id'];body,meta=build_request(config,case,inventory)
        except (ValueError,TypeError,KeyError) as exc:
            result={'case_id':cid,'status':'ERROR','stage':'PROMPT_PREPARATION',
                    'error':str(exc),'auto_applied':False}
            if '_aggregate_weight' in rows[i]:result['aggregate_count']=rows[i]['_aggregate_weight']
            save(out/'results'/f'{cid}.json',result)
            records.append({'case_id':cid,'status':'ERROR','error':result['error']})
            if len(records)%100==0 or index==len(selected_indices)-1:
                save(out/'progress.json',records)
            continue
        save(out/'requests'/f'{cid}.json',{'endpoint':config.endpoint,'metadata':meta,'body':body})
        path=out/'results'/f'{cid}.json'
        if not execute:
            records.append({'case_id':cid,'status':'DRY_RUN','example_count':meta['example_count'],'prompt_chars':meta['prompt_chars']});continue
        response_path=out/'responses'/f'{cid}.json'
        cached_result=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        if response_path.exists() and (cached_result is None or
                                       (cached_result.get('status')!='SUCCESS' and cached_result.get('request_sha256')==meta['request_sha256'])):
            try:
                raw_response=json.loads(response_path.read_text(encoding='utf-8'))
                recovered=parse_result(extract_text(raw_response),cid,meta['allowed_subjects'],meta['allowed_refs'])
            except (APIError,ValueError,TypeError,KeyError):
                recovered=None
            if recovered is not None:
                recovered_result={'case_id':cid,'status':'SUCCESS','request_sha256':meta['request_sha256'],
                                  'analysis':recovered,'usage':raw_response.get('usage',{}),
                                  'response_id':raw_response.get('id'),'reported_model':raw_response.get('model'),
                                  'elapsed_seconds':cached_result.get('elapsed_seconds',0) if cached_result else 0,
                                  'auto_applied':False,'recovered_from_raw_response':True}
                if '_aggregate_weight' in rows[i]:recovered_result['aggregate_count']=rows[i]['_aggregate_weight']
                save(path,recovered_result);save_three_outputs(out,cid,recovered,rows[i].get('_aggregate_weight'))
            records.append({'case_id':cid,'status':'RECOVERED_FROM_RAW_RESPONSE',
                            'usage':recovered_result['usage'],
                            **({'aggregate_count':rows[i]['_aggregate_weight']} if '_aggregate_weight' in rows[i] else {})});continue
        if cached_result and cached_result.get('status')=='ERROR' and cached_result.get('request_sha256')==meta['request_sha256']:
            records.append({'case_id':cid,'status':'ERROR','skipped':True,
                            'error':cached_result.get('error','Previously recorded failure'),
                            **({'aggregate_count':rows[i]['_aggregate_weight']} if '_aggregate_weight' in rows[i] else {})})
            continue
        if path.exists():
            cached=cached_result or json.loads(path.read_text(encoding='utf-8'))
            if cached.get('status')=='SUCCESS' and cached.get('request_sha256')==meta['request_sha256']:
                parse_result(stable_json(cached['analysis']),cid,meta['allowed_subjects'],meta['allowed_refs'])
                save_three_outputs(out,cid,cached['analysis'],rows[i].get('_aggregate_weight'))
                records.append({'case_id':cid,'status':'RESUMED','usage':cached.get('usage',{}),
                                **({'aggregate_count':rows[i]['_aggregate_weight']} if '_aggregate_weight' in rows[i] else {})});continue
        start=time.monotonic()
        try:
            response=client.create(body)
            # Even failed schema validation retains the raw successful HTTP result for debugging.
            save(out/'responses'/f'{cid}.json',response)
            parsed=parse_result(extract_text(response),cid,meta['allowed_subjects'],meta['allowed_refs'])
            result={'case_id':cid,'status':'SUCCESS','request_sha256':meta['request_sha256'],
                    'analysis':parsed,'usage':response.get('usage',{}),'response_id':response.get('id'),
                    'reported_model':response.get('model'),'elapsed_seconds':round(time.monotonic()-start,3),
                    'auto_applied':False}
            if '_aggregate_weight' in rows[i]:result['aggregate_count']=rows[i]['_aggregate_weight']
            save_three_outputs(out,cid,parsed,rows[i].get('_aggregate_weight'))
        except (APIError,ValueError,TypeError,KeyError) as exc:
            # Known parser messages contain no request/auth material; HTTP bodies aren't logged.
            error=str(exc) if isinstance(exc,(APIError,ValueError)) else type(exc).__name__
            result={'case_id':cid,'status':'ERROR','request_sha256':meta['request_sha256'],
                    'error':error,'elapsed_seconds':round(time.monotonic()-start,3),'auto_applied':False}
            if '_aggregate_weight' in rows[i]:result['aggregate_count']=rows[i]['_aggregate_weight']
            # Row-level failures are preserved and skipped; later rows continue.
            stop=False
        save(path,result)
        records.append({k:result[k] for k in ('case_id','status','elapsed_seconds')})
        if 'aggregate_count' in result:records[-1]['aggregate_count']=result['aggregate_count']
        if 'usage' in result:records[-1]['usage']=result['usage']
        if len(records)%100==0 or index==len(selected_indices)-1:
            save(out/'progress.json',records)
        if stop:break
    summary={'mode':'LIVE' if execute else 'DRY_RUN','model':config.model,'endpoint':config.endpoint,
             'selected_cases':len(selected_indices),'skipped_lgpl_rows':len(skipped_lgpl),
             'processed':len(records),'stopped_early':stop,
             'success':sum(r['status']=='SUCCESS' for r in records),'resumed':sum(r['status']=='RESUMED' for r in records),
             'errors':sum(r['status']=='ERROR' for r in records),'dry_run':sum(r['status']=='DRY_RUN' for r in records),
             'mandatory_examples_per_request':12,'auto_applied':False,
             'structured_asc_sha256':fingerprint['structured_asc_sha256'],'records':records}
    if payload.get('summary',{}).get('input_format')=='license_combination_csv':
        weight=lambda i:int(rows[i].get('_aggregate_weight',1))
        summary.update({'input_format':'license_combination_csv','input_rows':len(rows),
                        'input_relationships':sum(weight(i) for i in range(len(rows))),
                        'selected_relationships':sum(weight(i) for i in selected_indices),
                        'success_relationships':sum(int(r.get('aggregate_count',1)) for r in records
                                                     if r['status'] in {'SUCCESS','RESUMED','RECOVERED_FROM_RAW_RESPONSE'}),
                        'error_relationships':sum(int(r.get('aggregate_count',1)) for r in records if r['status']=='ERROR'),
                        'skipped_unknown_license_rows':len(skipped_unknown),
                        'skipped_unknown_license_relationships':sum(weight(i) for i in skipped_unknown),
                        'skipped_lgpl_relationships':sum(weight(i) for i in skipped_lgpl),
                        'skipped_records':skipped_records})
    save(out/'summary.json',summary)
    write_paper_report(out,summary,len(rows))
    return summary
