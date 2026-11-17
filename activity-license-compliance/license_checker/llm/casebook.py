"""将Figure10原始40条映射无损去重，并加载合成正反对照。"""
import copy
import json
from pathlib import Path
from ..asc import validate_triple

RESOURCES = Path(__file__).resolve().parents[1] / 'resources'


def compact_figure_cases(source):
    """每行保留条款引用；artifact用行内scope绑定，重复模板只发送一次。"""
    templates = {}
    identities = {}
    rows = []
    for case in source['cases']:
        bindings = []
        for term in case['asc_terms']:
            template = {k: copy.deepcopy(term[k]) for k in (
                'term_code', 'license_attribution', 'figure_clause_paraphrase', 'asc', 'mapping_notes')}
            template['asc']['S']['artifact'] = '$case_scope'
            identity = json.dumps(template, ensure_ascii=False, sort_keys=True)
            if identity not in identities:
                tid = f'T{len(identities)+1:02d}'
                identities[identity] = tid
                templates[tid] = template
            bindings.append({'term_id': term['id'], 'template_id': identities[identity]})
        rows.append({k: copy.deepcopy(case[k]) for k in (
            'case_id', 'combination', 'operation', 'normalized_operation', 'source_row')} | {
                'scope_binding': case['case_id'] + ':covered-artifact', 'term_bindings': bindings})
    return {
        'format': 'figure10-compact-2.0', 'source_sha256': source['source_sha256'],
        'warnings': source['warnings'],
        'binding_rule': '每个term_binding引用templates；将ASC.S.artifact的$case_scope替换为该行scope_binding即还原原始ASC。',
        'cases': rows, 'templates': templates,
        'teaching_note': '12行40条映射全部保留。频次不参与本任务判断。重复机械反条件由conflict_patterns中的正例/边界对照替代。'}


def load_patterns():
    data = json.loads((RESOURCES / 'conflict_patterns.json').read_text(encoding='utf-8'))
    seen = set()
    figure_ids = {f'figure10-{i:02d}' for i in range(1,13)}
    for pattern in data['patterns']:
        if pattern['pattern_id'] in seen or pattern['synthetic'] is not True:
            raise ValueError('Pattern IDs must be unique and examples explicitly synthetic')
        seen.add(pattern['pattern_id'])
        if not set(pattern['figure_case_refs']) <= figure_ids:
            raise ValueError('Unknown Figure10 case in conflict patterns')
        for variant in pattern['variants']:
            fields = ('upstream_asc','downstream_asc') if variant['task']=='LICENSE_LICENSE' else ('rule',)
            for field in fields:
                validate_triple(variant[field])
    return data


def compact_patterns(source):
    """对照场景使用规则引用，避免相同ASC在正反例里重复。"""
    rules, identities, patterns = {}, {}, []
    for original in source['patterns']:
        pattern = copy.deepcopy(original)
        for variant in pattern['variants']:
            for field in ('upstream_asc','downstream_asc','rule'):
                if field not in variant:
                    continue
                triple = variant.pop(field)
                identity = json.dumps(triple, ensure_ascii=False, sort_keys=True)
                if identity not in identities:
                    rid = f'R{len(identities)+1:02d}'
                    identities[identity] = rid
                    rules[rid] = triple
                variant[field + '_ref'] = identities[identity]
        patterns.append(pattern)
    return {'version': source['version'], 'format':'contrastive-cases-compact-2.0',
            'purpose': source['purpose'], 'rules': rules, 'patterns': patterns,
            'binding_rule':'variants里的rule_ref/upstream_asc_ref/downstream_asc_ref引用rules中的完整ASC；每个pattern都是独立合成场景。'}
