"""单案例编排：独立运行两个引擎，聚合义务和复核事项。"""
import copy
import collections
from .asc_rules import ACTIVITIES
from .audit_engines import key, license_license, license_behavior, aggregate_obligations
from .audit_rules import RULE_VERSION


def analyze_case(case, license_cache=None):
    checks = [license_behavior(r, case['facts_by_subject'][key(r['triple']['S'])]) for r in case['rules']]
    up = {r['triple']['A']: r for r in case['rules'] if r['triple']['S'] == {'artifact': case['upstream_id'], 'kind': 'OriginalArtifact'}}
    down = {r['triple']['A']: r for r in case['rules'] if r['triple']['S']['artifact'] == case['downstream_id']}
    pairs = [license_license(up[a], down[a], case['object_graph']['scope_shared'], cache=license_cache) for a in ACTIVITIES]
    obligation_rules = list(case['rules'])
    if case['object_graph']['scope_shared'] is True:
        # Only explicit shared-scope confirmation permits downstream terms to be
        # projected onto the same component for joint obligation aggregation.
        for r in down.values():
            projected = copy.deepcopy(r)
            projected['triple']['S'] = {'artifact': case['upstream_id'], 'kind': 'OriginalArtifact'}
            projected['rule_id'] += ':shared-scope-projection'
            obligation_rules.append(projected)
    obligations, joint = aggregate_obligations(obligation_rules, case['facts_by_subject'])
    violations = [x for x in checks if x['status'] == 'VIOLATION']
    conflicts = [x for x in pairs if x.get('symbolic_result') in {'UNSATISFIABLE_OBLIGATIONS', 'ACTIVITY_CONSTRAINT_CONFLICT'}]
    active_open = [o for o in obligations if o['applicability'] is True and o['fulfillment_status'] == 'UNKNOWN']
    active_joint_conflicts = [j for j in joint if j['active_obligations_jointly_satisfiable'] is False]
    coverage = collections.Counter(r['coverage'] for r in case['rules'])
    reviews = []
    if coverage['UNMAPPED']:
        reviews.append({'type': 'RULE_COVERAGE', 'owner': 'RULE_MAINTAINER', 'priority': 'P0',
                        'question': '完成未映射的活动/条款，或明确其不适用；不得按 UNSPECIFIED 自动放行。',
                        'rule_ids': [r['rule_id'] for r in case['rules'] if r['coverage'] == 'UNMAPPED']})
    if case['object_graph']['scope_shared'] is None:
        reviews.append({'type': 'OBJECT_SCOPE', 'owner': 'LEGAL_REVIEWER', 'priority': 'P1',
                        'question': '确认 API/代码关系中两侧许可是否约束同一对象及同一权利；不重新质疑已核验关系。',
                        'evidence_refs': [case['source_ref']]})
    unknown_active = [x for x in checks if x['applicability'] is True and x['status'] in {'OBLIGATION_OPEN', 'CONDITION_UNKNOWN'}]
    if unknown_active:
        reviews.append({'type': 'FULFILLMENT', 'owner': 'PRODUCT_REVIEWER', 'priority': 'P1',
                        'question': '确认已触发条件的履行状态，可填写人工声明或材料引用。',
                        'obligation_ids': [o['obligation_id'] for o in active_open]})
    unperformed = sorted({x['activity'] for x in checks if x['status'] == 'APPLICABILITY_UNKNOWN'})
    if unperformed:
        reviews.append({'type': 'ACTIVITY_FACTS', 'owner': 'PRODUCT_REVIEWER', 'priority': 'P2',
                        'question': '按适用规则确认相关活动；不以空值替代 false。', 'activities': unperformed})
    if any(r['mapping_quality'] == 'LEGACY_PARTIAL' for r in case['rules']):
        reviews.append({'type': 'CLAUSE_ANNOTATION', 'owner': 'RULE_MAINTAINER', 'priority': 'P1',
                        'question': '细化旧版抽象的逐条出处和适用条件；当前未宣称完整审阅。'})
    confirmed = [p for p in conflicts if p['scope_shared'] is True]
    status = 'VIOLATION' if violations else 'CONSTRAINT_CONFLICT' if confirmed or active_joint_conflicts else 'OBLIGATIONS_OPEN' if active_open else 'INCOMPLETE_ANALYSIS' if reviews else 'NO_CONFLICT_IN_CHECKED_SCOPE'
    return {'case_id': case['case_id'], 'row_number': case['row_number'], 'repo': case['row']['github_repo'],
            'asset': case['row']['artifact_name'], 'status': status,
            'primary_relation': case['object_graph']['primary_relation'],
            'license_license': {'checks': pairs, 'potential_conflicts': conflicts,
                                'confirmed_constraint_conflicts': [p for p in conflicts if p['scope_shared'] is True],
                                'complete': not any(p['status'] in {'SCOPE_REVIEW_REQUIRED', 'UNMAPPED_OR_UNSPECIFIED'} for p in pairs)},
            'license_behavior': {'checks': checks, 'violations': violations,
                                 'complete': not any(x['status'] in {'UNMAPPED', 'AMBIGUOUS', 'UNSPECIFIED', 'APPLICABILITY_UNKNOWN', 'OBLIGATION_OPEN', 'CONDITION_UNKNOWN'} for x in checks)},
            'obligations_by_activity': obligations, 'joint_obligation_analysis': joint,
            'active_joint_conflicts': active_joint_conflicts, 'manual_review_items': reviews,
            'rule_coverage': {'counts': dict(coverage), 'whole_license_coverage': 'PARTIAL',
                              'version': RULE_VERSION},
            'trace': {'input_ref': case['source_ref'], 'object_graph': case['object_graph'],
                      'rule_version': RULE_VERSION, 'engines': ['LicenseLicense', 'LicenseBehavior', 'ObligationAggregation']}}
