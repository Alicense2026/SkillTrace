"""批量离线分析入口；只负责输入遍历、汇总及审计索引。"""
import collections
from .audit_rules import clause_catalog
from .ingestion import prepare, apply_human
from .analysis import analyze_case
from .llm.license_sources import is_lgpl_row
POLICY = {'id': 'AUDITABLE_DUAL_ENGINE_v1', 'input_trust': 'USER_AND_EXPERT_VERIFIED',
          'default_pass': False, 'unknown_facts': 'UNKNOWN',
          'constraint_modalities_are_not_case_verdicts': True,
          'note': '按意见.txt 修订，替代 v0.3 无明确违规则合规策略；不撤销 chain 的可信前提。'}


def run(payload, human=None, source='chain/result.json', license_cache=None):
    if not isinstance(payload, dict) or not isinstance(payload.get('rows'), list): raise ValueError('Expected rows array')
    human = {} if human is None else human
    if not isinstance(human, dict): raise ValueError('human input must be object')
    inventory = clause_catalog(); cases = []; excluded_lgpl_rows = []
    for i, row in enumerate(payload['rows']):
        required = ('github_repo', 'github_url', 'github_license', 'artifact_name', 'artifact_license', 'integration', 'modified')
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in required): raise ValueError(f'Invalid row {i+1}')
        if is_lgpl_row(row):
            excluded_lgpl_rows.append(i+1)
            continue
        case = prepare(row, i, source)
        inventory[case['source_ref']] = {'kind': 'TRUSTED_CHAIN_RECORD', 'row_number': i+1,
                                       'raw_record': row, 'trust': 'USER_AND_EXPERT_VERIFIED'}
        if case['case_id'] in human: apply_human(case, human[case['case_id']], inventory)
        cases.append(case)
    if set(human) - {c['case_id'] for c in cases}: raise ValueError('Unknown human case ID')
    results = [analyze_case(c, license_cache=license_cache) for c in cases]
    counts = collections.Counter(r['status'] for r in results)
    all_o = [o for r in results for o in r['obligations_by_activity']]
    return {'schema_version': '4.0', 'engine_version': '0.6.0', 'policy': POLICY,
            'summary': {'input_rows': len(payload['rows']), 'relations': len(cases),
                        'excluded_lgpl_rows': len(excluded_lgpl_rows),
                        'excluded_lgpl_source_row_numbers': excluded_lgpl_rows,
                        'statuses': dict(counts),
                        'LINK': sum(c['object_graph']['primary_relation'] == 'LINK' for c in cases),
                        'BUNDLE': sum(c['object_graph']['primary_relation'] == 'BUNDLE' for c in cases),
                        'behavior_violations': sum(len(r['license_behavior']['violations']) for r in results),
                        'license_comparisons': sum(len(r['license_license']['checks']) for r in results),
                        'potential_license_conflicts': sum(len(r['license_license']['potential_conflicts']) for r in results),
                        'confirmed_constraint_conflicts': sum(len(r['license_license']['confirmed_constraint_conflicts']) for r in results),
                        'active_obligations': sum(o['applicability'] is True for o in all_o),
                        'active_open_obligations': sum(o['applicability'] is True and o['fulfillment_status'] == 'UNKNOWN' for o in all_o),
                        'conditional_obligations': sum(o['applicability'] is None for o in all_o),
                        'cases_with_review_items': sum(bool(r['manual_review_items']) for r in results),
                        'whole_license_verifications_completed': 0,
                        'license_license_cache': license_cache.stats() if license_cache is not None else None},
            'license_license_cache': license_cache.stats() if license_cache is not None else None,
            'cases': cases, 'results': results, 'evidence_inventory': inventory,
            'limitations': ['许可证规则仍为部分覆盖；未宣称 216 条完成全面合规验证。',
                            '现有数据可信，未记录的分发、收费及履行状态仍未知。',
                            'LINK/BUNDLE 主类描述接入形式；发布物打包、许可适用范围分别判断。',
                            '布尔可满足性只覆盖已建模原子；复杂法律等价、例外、许可选择尚未全部实现。',
                            '没有调用 LLM；prompt 仅为后续集成模板。']}
