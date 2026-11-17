"""JSON 产物与 HTML 报告输出，不参与判定。"""
import json
import html
import re
from pathlib import Path


def write_outputs(result, out):
    out.mkdir(parents=True, exist_ok=True)
    def dump(name, obj): (out/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    dump('analysis.json', result); dump('summary.json', result['summary']); dump('normalized_cases.json', result['cases'])
    for filename, field in [('license_license.json','license_license'), ('license_behavior.json','license_behavior'),
                             ('obligations_by_activity.json','obligations_by_activity'), ('joint_obligations.json','joint_obligation_analysis'),
                             ('review_queue.json','manual_review_items')]:
        dump(filename, [{'case_id': r['case_id'], 'repo': r['repo'], 'asset': r['asset'], field: r[field]} for r in result['results']])
    tasks = {}
    for r in result['results']:
        for q in r['manual_review_items']:
            ident = q['type']
            task = tasks.setdefault(ident, {'type': ident, 'owner': q['owner'], 'priority': q['priority'],
                                            'question': q['question'], 'case_ids': []})
            task['case_ids'].append(r['case_id'])
    dump('review_tasks.json', list(tasks.values()))
    dump('evidence_inventory.json', result['evidence_inventory'])
    dump('rules.json', [r for c in result['cases'] for r in c['rules']])
    dump('object_graphs.json', [{'case_id': c['case_id'], **c['object_graph']} for c in result['cases']])
    decisions = [{k: r[k] for k in ('case_id', 'row_number', 'repo', 'asset', 'status', 'primary_relation', 'rule_coverage')} for r in result['results']]
    dump('decisions.json', decisions)
    if not (out/'human_input.json').exists(): dump('human_input.json', {})
    dump('components.json', {'implemented': ['独立 LicenseLicense 引擎', '独立 LicenseBehavior 引擎',
         '按活动/对象去重义务与来源', '激活/候选义务分别做联合可满足性检查', '关系图与规则范围门控',
         '条款/行为证据索引', '覆盖及未完成检查', '人工事实和条款接口'],
         'remaining': ['全量条款和许可表达式覆盖', '服务合同和模型专用条款', '原文全文快照和签审体系',
                       '复杂派生/链接范围推理', '自动读取发布物验证义务履行'],
         'automatically_collected_additional_product_evidence': False})
    def esc(x): return html.escape(str(x))
    rows = []
    for r in result['results']:
        active = [o for o in r['obligations_by_activity'] if o['applicability'] is True]
        details = {'license_license': r['license_license'], 'active_obligations': active,
                   'behavior_violations': r['license_behavior']['violations'], 'review_items': r['manual_review_items']}
        cells = [r['row_number'], r['repo'], r['asset'], r['primary_relation'], r['status'], len(active),
                 len(r['license_license']['potential_conflicts']), len(r['license_behavior']['violations'])]
        rows.append('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in cells)+'<td><details><summary>审计明细</summary><pre>'+esc(json.dumps(details,ensure_ascii=False,indent=2))+'</pre></details></td></tr>')
    o_rows = []
    for r in result['results']:
        for o in r['obligations_by_activity']:
            if o['applicability'] is not True: continue
            vals = [r['repo']+' → '+r['asset'], o['activity'], o['subject']['kind'], o['requirement'],
                    '; '.join(s['license']+' '+s['clause_id'] for s in o['sources']), o['fulfillment_status'],
                    ', '.join(o['evidence_refs']) or '无履行证据（行为证据另存）', o['next_action']]
            o_rows.append('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in vals)+'</tr>')
    page = (Path(__file__).parent / 'resources' / 'report.html').read_text(encoding='utf-8')
    values = {'SUMMARY': esc(json.dumps(result['summary'], ensure_ascii=False,indent=2)), 'OBLIGATIONS': ''.join(o_rows), 'ROWS': ''.join(rows), 'LIMITS': esc('\n'.join(result['limitations']))}
    page = re.sub(r'@@(SUMMARY|OBLIGATIONS|ROWS|LIMITS)@@', lambda match: values[match.group(1)], page)
    (out/'report.html').write_text(page, encoding='utf-8')
