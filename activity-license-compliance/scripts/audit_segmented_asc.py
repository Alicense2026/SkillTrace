"""Verify this experiment without API calls and write a readable source index."""
import json
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.extract_segmented_asc import RUN, INPUT, LICENSE_DIR, inventory, make_jobs, compile_outputs, digest, save

def main():
    frozen=json.loads((RUN/'inventory.json').read_text())
    assert frozen['input_sha256']==digest(INPUT.read_bytes()),'Input changed'
    inv=inventory();assert inv==frozen,'Source mappings changed'
    jobs=make_jobs(inv)
    for src in inv['sources']:
        selected=[j for j in jobs if j['source']['sha256']==src['sha256']]
        lines=selected[0]['lines']
        counts=Counter(i for j in selected for u in j['units'] for i in range(u['start_line'],u['end_line']+1) if lines[i-1].strip())
        assert set(counts)=={i for i,l in enumerate(lines,1) if l.strip()}
        assert all(n==1 for n in counts.values())
    summary=compile_outputs(inv,jobs)
    corpus=json.loads((RUN/'structured_asc.json').read_text())
    ids=[r['rule_id'] for r in corpus['rules']];assert len(set(ids))==len(ids)
    for r in corpus['rules']:
        src=(LICENSE_DIR/r['license_id']).read_text(encoding='utf-8-sig').splitlines()
        a,b=r['source_lines'];assert r['source_excerpt']=='\n'.join(src[a-1:b])
    table=['逐许可证 ASC 提取清单（模型自评，不是独立专家覆盖率）',
           '文件名 | 状态 | 已处理段/总段 | ASC条目 | 具体义务项目 | 未解决自然段']
    for s in corpus['sources']:
        rr=[r for r in corpus['rules'] if r['source_sha256']==s['sha256']]
        table.append(' / '.join(s['files'])+' | '+s['status']+f" | {s['chunks']-len(s['pending_chunks'])}/{s['chunks']} | {len(rr)} | {sum(len(r['obligation_items']) for r in rr)} | {s['paragraph_status_counts'].get('UNRESOLVED',0)}")
    table.extend(['','汇总：',json.dumps(summary,ensure_ascii=False,indent=2),'','注意：零条目不等于无约束；应查看 pending_chunks、paragraph_audit 与 coverage_notes。'])
    (RUN/'逐许可证提取统计.txt').write_text('\n'.join(table)+'\n',encoding='utf-8')
    verification={'input_unchanged':True,'source_mappings_unchanged':True,'all_nonblank_source_lines_assigned_once':True,'unique_rule_ids':True,'exact_source_excerpts':True,'validated_chunks':summary['validated_chunks'],'total_chunks':summary['chunks'],'complete':not summary['pending_chunks']}
    save(RUN/'verification.json',verification)
    report=['新输入许可证 ASC 分段提取结果',
            '阶段状态：'+('全部目标段均已有通过校验的结果；语义限制另列。' if verification['complete'] else '尚未全部完成，以下为阶段统计。'),
            f"供应链关系：{summary['relationships']}；原文文件：{summary['source_files']}；不同文本：{summary['unique_source_texts']}。",
            f"分段完成：{summary['validated_chunks']}/{summary['chunks']}；ASC 条目：{summary['asc_rules']}；具体义务项目：{summary['obligation_items']}。",
            '原文状态：'+json.dumps(summary['source_status'],ensure_ascii=False),
            '自然段审查状态：'+json.dumps(summary['paragraph_audit'],ensure_ascii=False),
            '全部已落盘响应的 token 用量（包括试运行、重试）：'+json.dumps(summary['api_usage_all_attempts'],ensure_ascii=False),
            '未完成分段：'+json.dumps(summary['pending_chunks'],ensure_ascii=False),
            '', '这是许可证级提取，不是供应链冲突检测结果。',
            'EXTRACTED_SELF_CHECKED 仅表示模型自评没有遗留 UNRESOLVED 段；不构成专家验证。',
            'EXTRACTED_WITH_LIMITATIONS 表示模型报告仍有表示范围、跨文档依赖或未覆盖内容。',
            'INCOMPLETE 表示存在尚未通过校验的分段。不能把零条目或未完成解释为没有约束。',
            '完整度统计不能冒充语义覆盖率：模型可能遗漏同段中的条件或将实质条款误分为上下文。',
            '后续冲突检测必须使用本次 inventory.json 的原文映射和 structured_asc.json，且保留映射假设、OR 许可选择、主体/对象/条件与限制说明。',
            '具体文件计数见逐许可证提取统计.txt，方法见实验方法与运行说明.txt。']
    (RUN/'提取结果报告.txt').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps(verification,ensure_ascii=False))

if __name__=='__main__':main()
