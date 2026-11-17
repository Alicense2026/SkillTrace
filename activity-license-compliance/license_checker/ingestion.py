"""可信 chain 输入、对象图和人工回填。无需网络。"""
from .asc import atoms, validate_triple
from .asc_rules import ACTIVITIES
from .audit_engines import key, digest
from .audit_rules import rules_for
from .identity import case_id


def fact(value=None, refs=(), derivation='NOT_PROVIDED'):
    return {'value': value, 'evidence_refs': list(refs), 'derivation': derivation}


def prepare(row, i, source):
    cid = case_id(row, i); ref = f'{source}#/rows/{i}'
    modified = row['modified'] == '是'
    remote = row['integration'] == '远程服务调用'
    if row['integration'] not in {'远程服务调用', '代码层面集成'}: raise ValueError('Unsupported integration')
    up_id, down_id = cid + ':upstream', cid + ':downstream'
    objects = ['OriginalArtifact'] + (['ModifiedArtifact'] if modified else [])
    rules = rules_for(row['artifact_license'], up_id, objects) + rules_for(row['github_license'], down_id, ['CombinedProduct'])
    subjects = {key(r['triple']['S']): r['triple']['S'] for r in rules}
    facts = {s: {'activity:' + a: fact() for a in ACTIVITIES} for s in subjects}
    original = key({'artifact': up_id, 'kind': 'OriginalArtifact'})
    f = facts[original]
    f['activity:Use'] = fact(True, [ref], 'TRUSTED_CHAIN_USE')
    if remote:
        f['activity:RemoteInteraction'] = fact(True, [ref], 'TRUSTED_REMOTE_CALL')
        f['activity:Link'] = fact(True, [ref], 'API_LINK_RELATION_NOT_LEGAL_DERIVATION')
    else:
        f['activity:Copy'] = fact(True, [ref], 'SOURCE_INCORPORATION')
        # Source incorporation != inclusion in an actual release artifact.
    if modified: f['activity:Modify'] = fact(True, [ref], 'TRUSTED_MODIFIED_COPY')
    elif row['modified'] == '否': f['activity:Modify'] = fact(False, [ref], 'TRUSTED_UNMODIFIED')
    elif row['modified'] not in {'\\', '', '未知', '无法确定'}: raise ValueError('Unsupported modified value')
    tags = {'LINK': True if remote else None, 'REMOTE_CALL': True if remote else None,
            'DEPENDENCY': None, 'BUNDLE': None, 'MODIFIED_COPY': True if modified else None,
            'COMBINED_PRODUCT': True if not remote else None}
    graph = {'primary_relation': 'LINK' if remote else 'BUNDLE',
             'primary_relation_meaning': 'API调用/加载关系' if remote else '代码纳入关系（不等于已发布打包物）',
             'nodes': list(subjects.values()),
             'edges': [{'from': down_id, 'to': up_id, 'type': t, 'status': v,
                        'evidence_refs': [ref] if v is not None else []} for t, v in tags.items()],
             'scope_shared': None,
             'scope_note': 'API/代码纳入均不直接证明两份许可约束同一对象；所有活动仍进行条件性条款比较。'}
    return {'case_id': cid, 'row_number': i+1, 'row': row, 'source_ref': ref,
            'upstream_id': up_id, 'downstream_id': down_id, 'rules': rules,
            'facts_by_subject': facts, 'object_graph': graph, 'human_history': []}


def apply_human(case, entry, inventory):
    if not isinstance(entry, dict) or not isinstance(entry.get('reviewer'), str) or not entry['reviewer'].strip():
        raise ValueError('Human entry requires reviewer')
    if set(entry) - {'reviewer', 'facts', 'scope_shared', 'rules'}: raise ValueError('Unknown human field')
    href = 'human:' + case['case_id']
    inventory[href] = {'kind': 'HUMAN_DECLARATION', 'reviewer': entry['reviewer'], 'record': entry}
    rules = entry.get('rules', [])
    if not isinstance(rules, list): raise ValueError('rules must be array')
    for r in rules:
        if not isinstance(r, dict) or set(r) != {'triple', 'source'}: raise ValueError('Human rule requires triple and source')
        t = r['triple']; validate_triple(t)
        src = r['source']
        if not isinstance(src, dict) or any(not isinstance(src.get(k), str) or not src[k] for k in ('license', 'license_version', 'clause_id', 'source_ref', 'rule_version')):
            raise ValueError('Rule source needs license, license_version, clause_id, source_ref, rule_version')
        sk = key(t['S'])
        if sk not in case['facts_by_subject']: raise ValueError('Unknown subject; cross-case rules prohibited')
        rid = 'rule-' + digest([t, src])
        case['rules'] = [old for old in case['rules'] if not (old['triple']['A'] == t['A'] and old['triple']['S'] == t['S'])]
        case['rules'].append({'rule_id': rid, 'triple': t, 'source': src,
                              'coverage': 'MAPPED_PARTIAL', 'mapping_quality': 'HUMAN_CLAUSE_MAPPING', 'evidence_refs': [href]})
    allowed = {'activity:' + a for a in ACTIVITIES}
    for r in case['rules']:
        allowed |= atoms(r['triple']['C'].get('requires', True)) | atoms(r['triple']['C'].get('when', True))
    updates = entry.get('facts', {})
    if not isinstance(updates, dict): raise ValueError('facts must be object')
    for side, scopes in updates.items():
        if side not in {'upstream', 'downstream'} or not isinstance(scopes, dict): raise ValueError('Invalid side')
        for obj, values in scopes.items():
            sk = key({'artifact': case[side + '_id'], 'kind': obj})
            if sk not in case['facts_by_subject'] or not isinstance(values, dict): raise ValueError('Invalid object scope')
            for name, value in values.items():
                if name not in allowed: raise ValueError('Unknown predicate: ' + name)
                if isinstance(value, dict):
                    if set(value) != {'value', 'evidence_refs'} or not isinstance(value['evidence_refs'], list) or not all(isinstance(x, str) for x in value['evidence_refs']): raise ValueError('Invalid fact record')
                    v, refs = value['value'], value['evidence_refs']
                else: v, refs = value, []
                if v is not None and not isinstance(v, bool): raise ValueError('Fact must be true/false/null')
                for ref in refs:
                    if ref not in inventory: inventory[ref] = {'kind': 'HUMAN_REFERENCED_MATERIAL', 'verified_by_tool': False}
                case['facts_by_subject'][sk][name] = fact(v, refs + [href], 'HUMAN_CONFIRMATION')
    if 'scope_shared' in entry:
        if entry['scope_shared'] is not None and not isinstance(entry['scope_shared'], bool): raise ValueError('scope_shared must be boolean/null')
        case['object_graph']['scope_shared'] = entry['scope_shared']
        case['object_graph']['scope_evidence_refs'] = [href]
    case['human_history'].append(entry)
