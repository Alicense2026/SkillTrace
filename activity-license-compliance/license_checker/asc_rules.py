"""Versioned, deliberately bounded rule abstractions; provenance is outside ASC.
Names such as Other/proprietary remain unmapped, never interpreted as permission.
"""
from .asc import OBJECTS
from .taxonomy import TAXONOMY, normalize_activity
ACTIVITIES = tuple(dict.fromkeys(normalize_activity(a) for xs in TAXONOMY.values() for a in xs))
SOURCES = {
 'MIT': ('https://opensource.org/license/mit', 'permission grant; notice condition'),
 'Apache-2.0': ('https://www.apache.org/licenses/LICENSE-2.0', '2; 4(a)-(d); 6'),
 'BSD-3-Clause': ('https://opensource.org/license/bsd-3-clause', '1-3'),
 'GPL-3.0': ('https://opensource.org/license/gpl-3.0', '2; 4-6; 10'),
 'AGPL-3.0': ('https://www.gnu.org/licenses/agpl-3.0.en.html', '2; 4-6; 10; 13'),
 'CC-BY-SA-4.0': ('https://creativecommons.org/licenses/by-sa/4.0/legalcode.en', '2(a); 3(a)-(b)'),
 'CC-BY-NC-SA-4.0': ('https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en', '2(a); 3(a)-(b)'),
 'CC0-1.0': ('https://creativecommons.org/publicdomain/zero/1.0/legalcode.en', '2-4'),
}
ALIASES = {x.lower(): x for x in SOURCES}

def normalize_license(value):
    return ALIASES.get(value.lower(), value)


def constraint(license_name, a, obj):
    name = normalize_license(license_name)
    c = {'kind': 'UNSPECIFIED'}
    def allow(*conditions):
        return {'kind': 'CONDITIONALLY_PERMITTED' if conditions else 'PERMITTED',
                'requires': {'all': list(conditions)} if conditions else True}
    changed = obj in {'ModifiedArtifact', 'DerivativeWork'}
    reproduction = {'Copy', 'Modify', 'CreateDerivative', 'Distribute', 'SellCopies'}
    if name == 'MIT':
        if a in reproduction | {'Sublicense', 'Bundle', 'Combine'}:
            return allow('preserve_copyright', 'include_license:MIT')
        if a in {'Use', 'CommercialUse', 'Charge'}: return allow()
    elif name == 'Apache-2.0':
        if a in {'Distribute', 'SellCopies'}:
            cond = ['include_license:Apache-2.0']
            if changed:
                cond += ['mark_changes', {'any': [{'not': 'distributed_as_source'}, 'retain_applicable_source_notices']},
                         {'any': [{'not': 'upstream_has_notice'}, 'include_applicable_notice']}]
            return allow(*cond)
        if a in {'Copy', 'Modify', 'CreateDerivative', 'Sublicense', 'CommercialUse', 'Charge'}: return allow()
    elif name == 'BSD-3-Clause':
        if a in {'Distribute', 'SellCopies'}:
            return allow('preserve_copyright', 'include_license:BSD-3-Clause', 'retain_disclaimer')
        if a in {'Use', 'Copy', 'Modify', 'CreateDerivative', 'CommercialUse', 'Charge'}: return allow()
    elif name in {'GPL-3.0', 'AGPL-3.0'}:
        if a in {'Use', 'Copy', 'Modify', 'CreateDerivative', 'CommercialUse', 'Charge'}: return allow()
        if a in {'Distribute', 'SellCopies'}:
            cond = ['preserve_copyright', 'include_license:' + name, 'no_further_restrictions',
                    {'any': [{'not': 'distributed_as_binary'}, 'corresponding_source_available']}]
            if changed: cond += ['mark_changes', 'whole_work_license:' + name]
            return allow(*cond)
        if name == 'AGPL-3.0' and a == 'ProvideSource':
            return {'kind': 'OBLIGATORY', 'when': {'all': ['activity:Modify', 'users_interact_with_modified_program']},
                    'requires': 'network_source_offer_available'}
    elif name.startswith('CC-BY-'):
        # CC governs licensed rights, not every commercial activity of a user.
        nc = [{'not': 'commercial_purpose'}] if name == 'CC-BY-NC-SA-4.0' else []
        if a in {'Copy', 'Modify', 'CreateDerivative'}: return allow(*nc)
        if a in {'Distribute', 'SellCopies'}:
            cond = nc + ['retain_supplied_attribution', 'include_license_link', 'indicate_changes_if_any', 'no_extra_restrictions']
            if changed: cond += ['compatible_adapter_license:' + name]
            return allow(*cond)
    elif name == 'CC0-1.0':
        if a in reproduction | {'Use', 'CommercialUse', 'Charge'}: return allow()
    return c


def model(license_name, artifact):
    return [{'A': a, 'S': {'artifact': artifact, 'kind': obj}, 'C': constraint(license_name, a, obj)}
            for obj in OBJECTS for a in ACTIVITIES]


def catalog():
    return {name: {'model': model(name, '$ARTIFACT'), 'source_url': url, 'clauses': clause,
                   'coverage': 'PARTIAL_ACTIVITY_ABSTRACTION',
                   'note': 'UNSPECIFIED 表示本活动规则层未给出明确约束，不宣称已穷尽许可全文。'}
            for name, (url, clause) in SOURCES.items()}
