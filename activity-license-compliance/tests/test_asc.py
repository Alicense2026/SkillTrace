import copy
import json
import unittest
import tempfile
from pathlib import Path
from license_checker.asc import check, compare, relation, evaluate, validate_triple
from license_checker.asc_rules import constraint


def triple(kind, req=True, when=True, a='Copy', artifact='U'):
    return {'A': a, 'S': {'artifact': artifact, 'kind': 'OriginalArtifact'},
            'C': {'kind': kind, 'requires': req, 'when': when}}

class ASCTests(unittest.TestCase):
    def test_boolean_logic(self):
        self.assertIsNone(evaluate({'all': ['a', 'b']}, {'a': True}))
        self.assertFalse(evaluate({'all': ['a', 'b']}, {'a': False}))
        self.assertTrue(evaluate({'any': ['a', 'b']}, {'a': True}))
        self.assertIsNone(evaluate({'not': 'a'}, {}))

    def test_inclusion_direction_and_witness(self):
        self.assertEqual(relation({'all': ['notice', 'source']}, 'notice')['inclusion'], 'INCLUDED')
        r = relation('notice', {'all': ['notice', 'source']})
        self.assertEqual(r['inclusion'], 'NOT_INCLUDED')
        self.assertEqual(r['counterexample'], {'notice': True, 'source': False})
        self.assertTrue(r['jointly_satisfiable'])

    def test_all_seven_modalities(self):
        facts = {'activity:Copy': True, 'notice': False}
        expectations = {'PERMITTED': 'SATISFIED', 'PROHIBITED': 'VIOLATION',
                        'OBLIGATORY': 'SATISFIED', 'CONDITIONALLY_PERMITTED': 'VIOLATION',
                        'CONDITIONALLY_PROHIBITED': 'SATISFIED',
                        'UNSPECIFIED': 'UNSPECIFIED', 'AMBIGUOUS': 'AMBIGUOUS'}
        for k, expected in expectations.items():
            req = 'notice' if k.startswith('CONDITIONALLY_') else True
            self.assertEqual(check(triple(k, req), facts)['status'], expected, k)
        self.assertEqual(check(triple('CONDITIONALLY_PROHIBITED', 'notice'),
                               {'activity:Copy': True, 'notice': True})['status'], 'VIOLATION')

    def test_obligatory_is_required_action_not_trigger_action(self):
        t = triple('OBLIGATORY', when='activity:Distribute', a='ProvideSource')
        self.assertEqual(check(t, {'activity:Distribute': True, 'activity:ProvideSource': False})['status'], 'VIOLATION')
        self.assertEqual(check(t, {'activity:Distribute': False, 'activity:ProvideSource': False})['status'], 'NOT_APPLICABLE')

    def test_missing_condition_not_fulfilled_or_violation(self):
        self.assertEqual(check(triple('CONDITIONALLY_PERMITTED', 'notice'), {'activity:Copy': True})['status'], 'NO_EXPLICIT_VIOLATION')

    def test_inheritance_and_incompatibility(self):
        u = triple('CONDITIONALLY_PERMITTED', 'notice')
        self.assertEqual(compare(u, triple('PERMITTED'))['status'], 'INHERIT_UPSTREAM_CONDITIONS')
        self.assertEqual(compare(u, triple('CONDITIONALLY_PERMITTED', {'not': 'notice'}))['status'], 'INCOMPATIBLE_IF_ACTIVITY_OCCURS')
        self.assertEqual(compare(triple('PROHIBITED'), triple('PROHIBITED'))['status'], 'CONDITIONS_INCLUDED')

    def test_different_objects_and_explicit_projection(self):
        u = triple('PROHIBITED')
        d = triple('PERMITTED', artifact='P')
        self.assertEqual(compare(u, d)['status'], 'SEPARATE_OBJECTS')
        self.assertEqual(compare(u, d, same_scope=True)['status'], 'INCOMPATIBLE_IF_ACTIVITY_OCCURS')

    def test_unknown_is_not_permission(self):
        self.assertEqual(compare(triple('UNSPECIFIED'), triple('PERMITTED'))['status'], 'UNSPECIFIED_OR_AMBIGUOUS')

    def test_exact_asc_and_invalid_conditions(self):
        t = triple('PERMITTED'); t['extra'] = True
        with self.assertRaises(ValueError): validate_triple(t)
        with self.assertRaises(ValueError): evaluate({'eval': 'danger'}, {})
        with self.assertRaises(ValueError): check(triple('PERMITTED'), {'activity:Copy': 'false'})

    def test_cc_nc_does_not_prohibit_all_charging(self):
        self.assertEqual(constraint('cc-by-nc-sa-4.0', 'Charge', 'OriginalArtifact')['kind'], 'UNSPECIFIED')
        self.assertEqual(constraint('cc-by-nc-sa-4.0', 'Copy', 'OriginalArtifact')['requires'], {'all': [{'not': 'commercial_purpose'}]})

