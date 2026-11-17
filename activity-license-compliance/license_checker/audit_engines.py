"""Independent license/license, license/behavior and obligation engines (v0.4)."""
import hashlib
import json
from .asc import atoms, evaluate, relation, permission, validate_triple


def key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(key(value).encode()).hexdigest()[:16]


def normative(t):
    """Obligation means the action MUST happen; permission never means MUST."""
    c = t['C']; k = c['kind']; a = 'occurs:' + t['A']
    when, req = c.get('when', True), c.get('requires', True)
    if k in {'UNSPECIFIED', 'AMBIGUOUS'}: return None
    if k == 'OBLIGATORY': body = {'all': [a, req]}
    elif k == 'PROHIBITED': body = {'not': a}
    elif k == 'CONDITIONALLY_PROHIBITED': body = {'not': {'all': [a, req]}}
    else: body = {'any': [{'not': a}, req]}
    return {'any': [{'not': when}, body]}


def license_license(up, down, scope_shared=None, cache=None):
    """Compare abstract terms independently of observed behavior."""
    u, d = up['triple'], down['triple']
    validate_triple(u); validate_triple(d)
    out = {'activity': u['A'], 'subject_upstream': u['S'], 'subject_downstream': d['S'],
           'scope_shared': scope_shared, 'rule_refs': [up['rule_id'], down['rule_id']],
           'clause_evidence_refs': up['evidence_refs'] + down['evidence_refs']}
    cache_key = None
    core = None
    if cache is not None:
        from .license_pair_cache import comparison_key
        cache_key = comparison_key(up, down, scope_shared)
        core = cache.get(cache_key)
    if core is not None:
        return dict(out, **core)
    def finish(result):
        if cache is not None:
            reusable = {k: v for k, v in result.items() if k not in {
                'activity', 'subject_upstream', 'subject_downstream', 'scope_shared',
                'rule_refs', 'clause_evidence_refs'}}
            cache.put(cache_key, reusable)
        return result
    if u['A'] != d['A']: return finish(dict(out, status='DIFFERENT_ACTIVITY'))
    if scope_shared is False: return finish(dict(out, status='SCOPE_EXCLUDED_BY_CONFIRMATION'))
    ue, de = permission(u['C']), permission(d['C'])
    if ue is None or de is None:
        return finish(dict(out, status='UNMAPPED_OR_UNSPECIFIED', inclusion='UNDETERMINED',
                    jointly_satisfiable=None, next_action='完成该活动的条款映射，不由未映射推断允许。'))
    rel = relation(de, ue)
    joint = relation(True, {'all': [normative(u), normative(d)]})['jointly_satisfiable']
    action_joint = relation(True, {'all': [ue, de]})['jointly_satisfiable']
    symbolic = ('UNSATISFIABLE_OBLIGATIONS' if joint is False else
                'ACTIVITY_CONSTRAINT_CONFLICT' if action_joint is False and rel.get('downstream_satisfiable') else
                'CONDITIONS_INCLUDED' if rel['inclusion'] == 'INCLUDED' else 'JOINT_CONDITIONS_TO_INHERIT')
    status = symbolic if scope_shared is True else 'SCOPE_REVIEW_REQUIRED'
    return finish(dict(out, status=status, symbolic_result=symbolic, inclusion=rel['inclusion'],
                counterexample=rel.get('counterexample'), jointly_satisfiable=joint,
                activity_jointly_satisfiable=action_joint,
                joint_condition={'all': [ue, de]},
                next_action='确认两侧条款是否约束同一工件及同一权利范围。' if scope_shared is None else '保留并跟踪合并条件。'))


def license_behavior(rule, facts):
    """Facts are {predicate: {value, evidence_refs}}; missing is UNKNOWN."""
    t = rule['triple']; validate_triple(t)
    env = {k: v['value'] for k, v in facts.items()}
    if any(v is not None and not isinstance(v, bool) for v in env.values()): raise ValueError('Invalid fact value')
    c = t['C']; k = c['kind']
    gate = evaluate(c.get('when', True), env)
    occurred = env.get('activity:' + t['A'])
    applicable = gate if k == 'OBLIGATORY' else evaluate({'all': [c.get('when', True), 'activity:' + t['A']]}, env)
    requirement = {'all': ['activity:' + t['A'], c.get('requires', True)]} if k == 'OBLIGATORY' else c.get('requires', True)
    value = evaluate(requirement, env)
    used = atoms(c.get('when', True)) | atoms(requirement) | {'activity:' + t['A']}
    evidence = sorted({ref for a in used for ref in facts.get(a, {}).get('evidence_refs', [])})
    if applicable is False: status = 'NOT_APPLICABLE'
    elif k in {'UNSPECIFIED', 'AMBIGUOUS'}: status = 'UNMAPPED' if rule['coverage'] == 'UNMAPPED' else k
    elif applicable is None: status = 'APPLICABILITY_UNKNOWN'
    elif k == 'PROHIBITED' or (k == 'CONDITIONALLY_PROHIBITED' and value is True): status = 'VIOLATION'
    elif k in {'CONDITIONALLY_PERMITTED', 'PERMITTED', 'OBLIGATORY'} and value is False: status = 'VIOLATION'
    elif value is None: status = 'OBLIGATION_OPEN' if k != 'CONDITIONALLY_PROHIBITED' else 'CONDITION_UNKNOWN'
    else: status = 'SATISFIED_IN_MAPPED_SCOPE'
    return {'rule_id': rule['rule_id'], 'activity': t['A'], 'subject': t['S'],
            'constraint': k, 'applicability': applicable, 'occurred': occurred,
            'requirement_value': value, 'status': status,
            'clause_evidence_refs': rule['evidence_refs'], 'behavior_evidence_refs': evidence,
            'unknown_predicates': sorted(a for a in used if env.get(a) is None),
            'trace': {'when': c.get('when', True), 'when_value': gate, 'requirement': requirement}}


def conjuncts(expr):
    """Split only AND. OR/NOT must remain intact to preserve alternatives."""
    if isinstance(expr, dict) and set(expr) == {'all'}:
        return [part for child in expr['all'] for part in conjuncts(child)]
    return [] if expr is True else [expr]


def aggregate_obligations(rules, facts_by_subject):
    items = {}
    for rule in rules:
        t = rule['triple']; c = t['C']
        if c['kind'] not in {'OBLIGATORY', 'CONDITIONALLY_PERMITTED'}: continue
        facts = facts_by_subject[key(t['S'])]
        check = license_behavior(rule, facts)
        if check['applicability'] is False: continue
        parts = conjuncts(c.get('requires', True))
        if c['kind'] == 'OBLIGATORY': parts = ['activity:' + t['A']] + parts
        for expr in parts:
            ident = key([t['A'], t['S'], expr])
            env = {k: v['value'] for k, v in facts.items()}
            fulfilled = evaluate(expr, env)
            refs = sorted({r for a in atoms(expr) for r in facts.get(a, {}).get('evidence_refs', [])})
            item = items.setdefault(ident, {'obligation_id': 'obligation-' + digest(ident),
                'activity': t['A'], 'subject': t['S'], 'requirement_expression': expr,
                'requirement': describe(expr), 'sources': [], 'trigger_conditions': [],
                'applicability': check['applicability'],
                'fulfillment_status': 'FULFILLED' if fulfilled is True else 'NOT_FULFILLED' if fulfilled is False else 'UNKNOWN',
                'evidence_refs': refs, 'trigger_evidence_refs': [],
                'next_action': '确认该活动是否发生；若发生，' + action(expr) if check['applicability'] is None else action(expr)})
            # Applicability of duplicate equivalent obligations is the OR of their triggers.
            if check['applicability'] is True: item['applicability'] = True; item['next_action'] = action(expr)
            source = dict(rule['source'])
            if source.get('license') == 'Apache-2.0':
                names = atoms(expr)
                clause = ('4(a)' if 'include_license:Apache-2.0' in names else
                          '4(b)' if 'mark_changes' in names else
                          '4(c)' if 'retain_applicable_source_notices' in names else
                          '4(d)' if 'include_applicable_notice' in names else None)
                if clause:
                    source['clause_id'] = clause
                    source['excerpt_refs'] = ['clause:Apache-2.0:' + clause]
            item['sources'].append({'rule_id': rule['rule_id'], **source})
            item['trigger_conditions'].append(check['trace']['when'] if c['kind'] == 'OBLIGATORY' else {'all': [check['trace']['when'], 'activity:' + t['A']]})
            item['trigger_evidence_refs'] = sorted(set(item['trigger_evidence_refs']) | set(check['behavior_evidence_refs']))
    obligations = list(items.values())
    groups = {}
    for item in obligations:
        group = key([item['activity'], item['subject']])
        groups.setdefault(group, []).append(item)
    joint = []
    for group in groups.values():
        active = [i for i in group if i['applicability'] is True]
        expr = {'all': [i['requirement_expression'] for i in active]}
        possible = {'all': [i['requirement_expression'] for i in group]}
        joint.append({'activity': group[0]['activity'], 'subject': group[0]['subject'],
                      'obligation_ids': [i['obligation_id'] for i in group],
                      'active_obligations_jointly_satisfiable': relation(True, expr)['jointly_satisfiable'],
                      'all_candidates_jointly_satisfiable': relation(True, possible)['jointly_satisfiable'],
                      'meaning': '仅对同一对象上已激活的义务判定冲突；候选义务不一定同时适用。'})
    return obligations, joint


def describe(expr):
    known = {'preserve_copyright': '保留适用的版权声明', 'mark_changes': '标明修改的文件',
             'network_source_offer_available': '向与修改版交互的用户提供对应源码获取途径',
             'corresponding_source_available': '按适用条款提供对应源码',
             'retain_applicable_source_notices': '在分发源码中保留适用声明',
             'include_applicable_notice': '随衍生作品提供适用的 NOTICE 归属声明'}
    if isinstance(expr, str):
        if expr.startswith('include_license:'): return '提供/保留 ' + expr.split(':', 1)[1] + ' 许可文本'
        if expr.startswith('activity:'): return '实施 ' + expr.split(':', 1)[1] + ' 行为'
        return known.get(expr, expr)
    return key(expr)


def action(expr):
    return '核对“' + describe(expr) + '”的履行情况并记录证据引用。'
