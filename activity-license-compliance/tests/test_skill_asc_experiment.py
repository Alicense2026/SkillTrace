import json
import unittest
from scripts import run_skill_asc_experiment as r

class SkillExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ctx=r.context()
    def test_frozen_row_mapping_and_exact_excerpt_references(self):
        t=r.make_task(self.ctx,0)
        self.assertEqual(t['case_id'],'skill-00001')
        self.assertEqual(t['source_excel_row'],'14')
        self.assertEqual({s['source_file'] for s in t['license_sources']},{'OpenAI.txt','LICENSE-ISC.txt'})
        for rule in t['structured_asc_rules']:
            self.assertIn(rule['source_excerpt_ref'],t['clause_excerpts'])
            self.assertIn('obligation_items',rule)
            self.assertEqual(rule['triple']['S']['artifact'],t['case_id']+':'+rule['side'])
    def test_missing_rule_audit_rejected(self):
        t=r.make_task(self.ctx,0)
        data={'case_id':t['case_id'],'asc_rules':[],'license_license_findings':[],'license_behavior_findings':[],
              'obligations':[],'review_items':[],'overall_status':'NO_CONFLICT_IN_CHECKED_SCOPE','limitations':[], 'rule_obligation_audit':[]}
        with self.assertRaisesRegex(ValueError,'every rule_ref'):r.validate(json.dumps(data),t)
    def test_included_obligation_needs_matching_source(self):
        t=r.make_task(self.ctx,0);rules=t['structured_asc_rules']
        data={'case_id':t['case_id'],'asc_rules':[],'license_license_findings':[],'license_behavior_findings':[],
              'obligations':[{'activity':'Use','subject':rules[0]['triple']['S'],'requirement':'condition','trigger':True,'applicability':None,'fulfillment_status':'UNKNOWN','unresolved_predicates':[],'source_refs':[]}],
              'review_items':[],'overall_status':'OBLIGATIONS_OPEN','limitations':[],
              'rule_obligation_audit':[{'rule_ref':x['rule_ref'],'status':'NO_OBLIGATION','obligation_indices':[],'reason':'test'} for x in rules]}
        data['rule_obligation_audit'][0].update(status='INCLUDED',obligation_indices=[0])
        with self.assertRaisesRegex(ValueError,'source inconsistent'):r.validate(json.dumps(data),t)

if __name__=='__main__':unittest.main()
