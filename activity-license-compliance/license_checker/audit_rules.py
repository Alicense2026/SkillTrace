"""Provenance for bounded clause mappings; gaps are coverage, not legal UNSPECIFIED."""
from .asc_rules import model, normalize_license, SOURCES
from .audit_engines import digest
RULE_VERSION = 'activity-rules-0.4.0'

# Short source excerpts, stored once in the evidence catalog, not repeated per finding.
EXCERPTS = {
 'MIT:notice': ('notice condition', 'included in all copies or substantial portions of the Software.'),
 'Apache-2.0:4(a)': ('4(a)', 'a copy of this License'),
 'Apache-2.0:4(b)': ('4(b)', 'prominent notices stating that You changed'),
 'Apache-2.0:4(c)': ('4(c)', 'retain, in the Source form'),
 'Apache-2.0:4(d)': ('4(d)', 'a readable copy of the attribution notices'),
}


def source_for(name, t):
    a, obj = t['A'], t['S']['kind']
    clause, excerpt_refs = 'UNMAPPED', []
    if name == 'MIT':
        clause = 'permission grant' if t['C']['kind'] == 'PERMITTED' else 'notice condition'
        if clause == 'notice condition': excerpt_refs = ['clause:MIT:notice']
    elif name == 'Apache-2.0':
        if a in {'Distribute', 'SellCopies'}:
            clause = '4(a)-(d)' if obj in {'ModifiedArtifact', 'DerivativeWork'} else '4(a)'
            excerpt_refs = ['clause:Apache-2.0:'+x for x in (['4(a)', '4(b)', '4(c)', '4(d)'] if clause == '4(a)-(d)' else ['4(a)'])]
        else: clause = '2 (bounded abstraction)'
    elif name in SOURCES: clause = SOURCES[name][1] + ' (legacy partial mapping; per-rule annotation pending)'
    return {'license': name, 'license_version': {'MIT': 'unversioned', 'Apache-2.0': '2.0'}.get(name, name),
            'clause_id': clause, 'source_ref': SOURCES.get(name, (None, None))[0],
            'rule_version': RULE_VERSION, 'excerpt_refs': excerpt_refs}


def rules_for(name, artifact, objects):
    name = normalize_license(name)
    result = []
    for t in model(name, artifact):
        if t['S']['kind'] not in objects: continue
        mapped = t['C']['kind'] != 'UNSPECIFIED'
        source = source_for(name, t)
        # Non-mapped slots don't assert that the original text is silent.
        coverage = 'MAPPED_PARTIAL' if mapped else 'UNMAPPED'
        result.append({'rule_id': 'rule-' + digest([RULE_VERSION, name, t]), 'triple': t,
                       'coverage': coverage, 'mapping_quality': 'CLAUSE_REFERENCED' if name in {'MIT', 'Apache-2.0'} and mapped else 'LEGACY_PARTIAL' if mapped else 'NO_MAPPING',
                       'source': source, 'evidence_refs': source['excerpt_refs'] or (['license:' + name] if name in SOURCES else [])})
    return result


def clause_catalog():
    result = {'license:' + name: {'kind': 'LICENSE_REFERENCE', 'url': url,
                                 'clauses': clauses, 'rule_version': RULE_VERSION,
                                 'full_text_snapshot_available': False}
              for name, (url, clauses) in SOURCES.items()}
    for ident, (clause, excerpt) in EXCERPTS.items():
        name = ident.split(':')[0]
        result['clause:' + ident] = {'kind': 'CLAUSE_EXCERPT', 'license': name, 'clause_id': clause,
                                     'excerpt': excerpt, 'url': SOURCES[name][0],
                                     'rule_version': RULE_VERSION, 'scope': 'standard text; asset label accepted from chain'}
    return result
