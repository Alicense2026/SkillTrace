"""Activity/Subject/Constraint calculus, independent of the decision policy.
Boolean expressions: bool, atom string, {all:[...]}, {any:[...]}, {not:...}.
Unknown is None. No unknown fact is converted to fulfilled or legally permitted.
"""
from itertools import product
from .taxonomy import normalize_activity

KINDS = {'PERMITTED', 'PROHIBITED', 'OBLIGATORY', 'CONDITIONALLY_PERMITTED',
         'CONDITIONALLY_PROHIBITED', 'UNSPECIFIED', 'AMBIGUOUS'}
OBJECTS = ('OriginalArtifact', 'ModifiedArtifact', 'DerivativeWork', 'CombinedProduct')


def atoms(expr):
    if isinstance(expr, bool): return set()
    if isinstance(expr, str) and expr: return {expr}
    if not isinstance(expr, dict) or len(expr) != 1:
        raise ValueError('Invalid condition expression')
    op, value = next(iter(expr.items()))
    if op == 'not': return atoms(value)
    if op not in {'all', 'any'} or not isinstance(value, list):
        raise ValueError('Conditions accept all/any arrays or not expression')
    return set().union(*(atoms(x) for x in value))


def evaluate(expr, facts):
    atoms(expr)  # Validate, including nested expressions.
    if isinstance(expr, bool): return expr
    if isinstance(expr, str): return facts.get(expr)
    op, value = next(iter(expr.items()))
    if op == 'not':
        result = evaluate(value, facts)
        return None if result is None else not result
    values = [evaluate(x, facts) for x in value]
    if op == 'all':
        return False if False in values else None if None in values else True
    return True if True in values else None if None in values else False


def relation(downstream, upstream):
    """D => U, and satisfiability of D AND U. Include a reproducible witness."""
    names = sorted(atoms(downstream) | atoms(upstream))
    if len(names) > 16:
        return {'inclusion': 'UNDECIDED', 'jointly_satisfiable': None, 'reason': 'More than 16 independent predicates'}
    counterexample = None
    joint = False
    down_sat = False
    for values in product((False, True), repeat=len(names)):
        env = dict(zip(names, values))
        d, u = evaluate(downstream, env), evaluate(upstream, env)
        down_sat |= d
        joint |= d and u
        if d and not u and counterexample is None: counterexample = env
    return {'inclusion': 'INCLUDED' if counterexample is None else 'NOT_INCLUDED',
            'jointly_satisfiable': joint, 'downstream_satisfiable': down_sat,
            'counterexample': counterexample}


def validate_triple(t):
    if not isinstance(t, dict) or set(t) != {'A', 'S', 'C'}:
        raise ValueError('Each triple must contain exactly A, S, C')
    if normalize_activity(t['A']) != t['A']:
        raise ValueError('ASC activities must use canonical names')
    if not isinstance(t['S'], dict) or set(t['S']) != {'artifact', 'kind'} or t['S']['kind'] not in OBJECTS or not isinstance(t['S']['artifact'], str) or not t['S']['artifact']:
        raise ValueError('S must contain artifact identity and object kind')
    c = t['C']
    if not isinstance(c, dict) or not isinstance(c.get('kind'), str) or c.get('kind') not in KINDS:
        raise ValueError('Invalid constraint modality')
    if set(c) - {'kind', 'when', 'requires'}:
        raise ValueError('C accepts kind, when and requires')
    atoms(c.get('when', True)); atoms(c.get('requires', True))
    if c['kind'].startswith('CONDITIONALLY_') and 'requires' not in c:
        raise ValueError('Conditional modality requires condition expression')


def permission(c):
    """Set of admissible states in which the activity may be performed."""
    k, gate, req = c['kind'], c.get('when', True), c.get('requires', True)
    if k in {'UNSPECIFIED', 'AMBIGUOUS'}: return None
    body = False if k == 'PROHIBITED' else {'not': req} if k == 'CONDITIONALLY_PROHIBITED' else req
    return {'any': [{'not': gate}, body]}


def compare(up, down, same_scope=False):
    validate_triple(up); validate_triple(down)
    base = {'A': up['A'], 'S_upstream': up['S'], 'S_downstream': down['S']}
    if normalize_activity(up['A']) != normalize_activity(down['A']):
        return dict(base, status='DIFFERENT_ACTIVITY')
    if up['S'] != down['S'] and not same_scope:
        return dict(base, status='SEPARATE_OBJECTS', reason='No declared licensing propagation to the same object')
    u, d = permission(up['C']), permission(down['C'])
    if u is None or d is None:
        return dict(base, status='UNSPECIFIED_OR_AMBIGUOUS', reason='No invented permission or prohibition')
    rel = relation(d, u)
    if rel['inclusion'] == 'UNDECIDED': status = 'UNDECIDED'
    elif rel['inclusion'] == 'INCLUDED': status = 'CONDITIONS_INCLUDED'
    elif not rel['jointly_satisfiable']: status = 'INCOMPATIBLE_IF_ACTIVITY_OCCURS'
    else: status = 'INHERIT_UPSTREAM_CONDITIONS'
    return dict(base, status=status, **rel,
                effective_condition={'all': [u, d]}, upstream_condition=u,
                downstream_condition=d)


def check(t, facts):
    validate_triple(t)
    if not isinstance(facts, dict) or any(v is not None and not isinstance(v, bool) for v in facts.values()):
        raise ValueError('Facts must be boolean or null')
    a, c = normalize_activity(t['A']), t['C']
    occurred = facts.get('activity:' + a)
    gate = evaluate(c.get('when', True), facts)
    req = evaluate(c.get('requires', True), facts)
    k = c['kind']
    result = {'A': a, 'S': t['S'], 'C': c, 'occurred': occurred,
              'condition_value': req, 'trigger_value': gate}
    if gate is False:
        status = 'NOT_APPLICABLE'
    elif k in {'UNSPECIFIED', 'AMBIGUOUS'}:
        status = k
    elif k == 'OBLIGATORY':
        if gate is None: status = 'NO_EXPLICIT_VIOLATION'
        elif occurred is False or (occurred is True and req is False): status = 'VIOLATION'
        elif occurred is True and req is True: status = 'SATISFIED'
        else: status = 'NO_EXPLICIT_VIOLATION'
    elif occurred is False:
        status = 'NOT_APPLICABLE'
    elif occurred is not True or gate is None:
        status = 'NO_EXPLICIT_VIOLATION'
    elif k == 'PROHIBITED' or (k == 'CONDITIONALLY_PROHIBITED' and req is True) or (k in {'PERMITTED', 'CONDITIONALLY_PERMITTED'} and req is False):
        status = 'VIOLATION'
    elif req is None:
        status = 'NO_EXPLICIT_VIOLATION'
    else:
        status = 'SATISFIED'
    return dict(result, status=status)
