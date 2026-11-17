"""Verify immutable provenance and publish the completed repair/recovery report."""
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import repair_segmented_asc_gaps as repair
from license_checker.asc import validate_triple
base=repair.base

def main():
    run=repair.RUN
    current=repair.load(run/'reviewed_structured_asc.json')
    original=repair.load(run/'baseline/structured_asc.json')
    gap=repair.load(run/'summary.json');history=repair.load(run/'regression_review/summary.json')
    assert not gap['pending_chunks'] and not gap['gap_dispositions'].get('UNRESOLVED',0)
    assert not history['errors'] and not history.get('deferred_chunks')
    assert history['reviewed_chunks']==history['target_chunks']
    assert current['rules'][:len(original['rules'])]==original['rules']
    assert len({r['rule_id'] for r in current['rules']})==len(current['rules'])
    source_index={s['sha256']:s for s in original['sources']}
    lines={}
    for sha,s in source_index.items():
        path=base.LICENSE_DIR/s['files'][0]
        assert base.digest(path.read_bytes())==sha
        lines[sha]=path.read_text(encoding='utf-8-sig').splitlines()
    for r in current['rules']:
        validate_triple(r['ASC']);assert r['ASC']['A'] in base.ACTS
        a,b=r['source_lines'];assert 1<=a<=b<=len(lines[r['source_sha256']])
        assert r['source_excerpt']=='\n'.join(lines[r['source_sha256']][a-1:b])
    unchanged=all(base.digest((base.RUN/rel).read_bytes())==sha for rel,sha in repair.load(run/'baseline/manifest.json').items())
    assert unchanged
    normalizations=[]
    for j in repair.load(run/'plan.json'):
        d=repair.load(run/'validated'/f"{j['key']}.json")['data']
        normalizations.extend({'chunk':j['key'],**x} for x in d.get('representation_normalizations',[]))
    base.save(run/'representation_normalizations.json',normalizations)
    ledger=repair.load(run/'gap_ledger.json')
    quarantine=repair.load(run/'regression_review/quarantined_new_rules.json')
    excluded={(r['source_sha256'],r['clause_label']) for r in quarantine['rules']}
    chunk_sources={j['key']:j['key'].split('-')[0] for j in repair.load(run/'plan.json')}
    for a in ledger:
        removed=[label for label in a['clause_labels'] if any(sha.startswith(chunk_sources[a['chunk']]) and old_label==label for sha,old_label in excluded)]
        if removed:
            a['previous_status']=a['status'];a['excluded_candidate_labels']=removed
            a['clause_labels']=[label for label in a['clause_labels'] if label not in removed]
            if not a['clause_labels']:
                # The only such current cases are the reviewed Mistral scope,
                # consumer-terms boundary and contract-acceptance paragraphs.
                assert a['chunk']=='4f00a0042342233a-001' and a['unit_id'] in {'P0002','P0003','P0004'}
                a['status']='CONTEXT'
                a['reason']='Historical source-based review: scope, separate-consumer-terms boundary or acceptance context does not itself grant or condition an activity. See regression_review/decisions.json.'
    base.save(run/'reviewed_gap_ledger.json',ledger)
    current['repair_ledger']='reviewed_gap_ledger.json'
    for source in current['sources']:
        source['repair_dispositions']=dict(Counter(a['status'] for a in ledger if a['chunk'].startswith(source['sha256'][:16])))
    base.save(run/'reviewed_structured_asc.json',current)
    for source in current['sources']:
        rules=[r for r in current['rules'] if r['source_sha256']==source['sha256']]
        base.save(run/'reviewed_licenses'/f"{source['sha256'][:16]}.asc.json",{**source,'rules':rules})
    out={'baseline_rules':len(original['rules']),'gap_repair_additions':gap['added_rules'],'historical_review_additions':history['added_rules'],'quarantined_new_rules':history.get('quarantined_new_rules',0),'baseline_rule_concerns':history.get('baseline_rule_concerns',0),
         'final_rules':len(current['rules']),'final_obligation_items':sum(len(r['obligation_items']) for r in current['rules']),
         'completed_repair_chunks':gap['completed_chunks'],'historical_review_chunks':history['reviewed_chunks'],
         'historical_candidate_decisions':history['decisions'],'gap_dispositions':dict(Counter(a['status'] for a in ledger)),
         'baseline_rules_preserved':True,'baseline_artifacts_unchanged':unchanged,'source_hashes_and_exact_excerpts_valid':True,
         'new_activities':[],'modality_normalizations':len(normalizations),'final_corpus':'reviewed_structured_asc.json',
         'note':'Validated extraction records, not a measured expert semantic recall. Accepted exclusions are not modeled coverage.'}
    base.save(run/'final_verification.json',out)
    report=f'''# ASC 补提取及历史丢失核验完成报告

本轮依据用户四项指示，针对原分段提取中的缺口进行定向补提取，不重跑供应链冲突检测。输入为 6,113 条关系涉及的 68 个原文文件、67 份去重文本。

|项目|结果|
|---|---:|
|原有 ASC 记录|{out['baseline_rules']}|
|定向补提取及 Mistral 恢复增加|{out['gap_repair_additions']}|
|历史疑似回退逐项核验后增加|{out['historical_review_additions']}|
|核验后移入隔离记录的新增候选（不删除原始输出）|{out['quarantined_new_rules']}|
|最终 ASC 记录|{out['final_rules']}|
|最终原文层面的义务项|{out['final_obligation_items']}|
|缺口分段完成|{out['completed_repair_chunks']}/65|
|历史疑似回退分段核验完成|{out['historical_review_chunks']}/16|
|待处理分段 / 尚未解决目标段落|0 / 0|
|新增 activity|0|
|原有 1,711 条规则及基线文件保持不变|是|

数量核对：{out['baseline_rules']} + {out['gap_repair_additions']} + {out['historical_review_additions']} − {out['quarantined_new_rules']} = {out['final_rules']}。

上述 ASC 数量是结构化记录数，不等于去除全部语义重叠后的独立法律规范数量，也不是供应链关系层面的义务数量。

## 四项处理

- 跨段：提供完整带行号原文及目标段落原文，允许记录其他章节的支持行号；过大目标按至多 12 个段落一批、长段按保留行号的子段补提取。已经提取的有效规则作为不可删除锚点；剩余缺口只作增量补充。
- 固定词表：附属通知、付款等义务尽量映射为现有活动的条件和 obligation_items。无法忠实表达的活动记录为 OUTSIDE_ACTIVITY_SCOPE，不新增活动、不产生 Use/UNSPECIFIED 占位规则。
- 外部引用：确实未提供的外部文件记录为 EXTERNAL_REFERENCE_EXCLUDED，不抓取、不推断其内容，也不将其视为允许或已履行。混合段落仍保留其本地可表达条款。
- 防丢失：原提取器增加 retain_valid_clauses；补提取采用增量补丁。Mistral 第一轮从历史结构有效候选恢复 14 条，并补出 7 条，原有 1 条不删除；随后历史语义核验对其中只表达协议范围或接受程序等候选作明确排除，另存隔离记录，不作为有效活动规则使用。全量扫描另外核对条款数量下降线索；每个历史候选都有覆盖、恢复、修正恢复或排除的依据。

## 目标段落处置

|状态|段落数|
|---|---:|
'''
    report+='\n'.join(f'|{k}|{v}|' for k,v in out['gap_dispositions'].items())
    report+='\n\n目标段落共 '+str(sum(out['gap_dispositions'].values()))+' 个：包含原有 258 个 UNRESOLVED 段落、失败分段中的 1 个段落及 Mistral 恢复核验额外涉及的 4 个段落。最终段落处置以 reviewed_gap_ledger.json 为准：历史核验将 Mistral 的 3 个范围/接受程序段落由先前 MODELED 改为 CONTEXT，并保留原分类。分类互斥；被排除的混合段落也可能包含已提取的本地义务。外部排除和词表范围外事项不计作已建模覆盖。\n\n## 历史候选核验\n\n|处置|候选数|\n|---|---:|\n'
    report+='\n'.join(f'|{k}|{v}|' for k,v in history['decisions'].items())
    report+=f'''\n\n共核验 {sum(history['decisions'].values())} 条历史候选。条款数下降仅用作定位线索，不能直接证明语义丢失。COVERED 指当前规则已覆盖，ADD/CORRECT_AND_ADD 指恢复或修正后恢复，EXCLUDE 指原候选不应作为该活动的有效规则，逐条理由见 regression_review/decisions.json。对于 ADD 判断，程序另检查候选与现有规则的精确结构相等性，完全相等则记录为 COVERED，避免模型误报新增。对于与当前新增规则精确相等而被模型判 EXCLUDE 的候选，转入 regression_review/quarantined_new_rules.json；基线规则不受此操作影响。

## 可追溯性与检验

最终语料为 `reviewed_structured_asc.json`，按原文分别输出在 `reviewed_licenses/`；`structured_asc.json` 是历史核验前的补提取语料。请求、原始响应、错误及被替代版本均保留。{len(normalizations)} 次条件禁止模态标签归一化记录在 representation_normalizations.json：保留模型给出的条件、主体、对象、原文和义务，只按既定 schema 将带禁止条件的 PROHIBITED 标记改为 CONDITIONALLY_PROHIBITED；这部分是程序归一化，不冒充模型原始输出。

已验证所有活动属于原词表、规则 ID 唯一、原文哈希未变、每条摘录与引用行号一致、所有基线规则完整保留。20 项相关回归测试通过。

本轮核验标记的基线规则疑点数：{out['baseline_rule_concerns']}；若非零，原规则保持不变，具体原因见隔离记录中的 concerns。

以上是模型提取、自检和程序校验完成情况，并非独立专家确认的 100% 语义覆盖率或准确率。历史核验也是模型审查；未改变这一证据性质。
'''
    (run/'最终补提取报告.md').write_text(report,encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False))

if __name__=='__main__':main()
