import copy
import json
import tempfile
import unittest
from pathlib import Path
from html.parser import HTMLParser
from license_checker.audit_chain import run, write_outputs
from license_checker.audit_engines import license_license, license_behavior, aggregate_obligations, key
from license_checker.asc_rules import constraint


def rule(activity='Copy', kind='CONDITIONALLY_PERMITTED', req='notice', when=True, artifact='U', rid='one'):
    return {'rule_id': rid, 'triple': {'A': activity, 'S': {'artifact': artifact, 'kind': 'OriginalArtifact'},
              'C': {'kind': kind, 'requires': req, 'when': when}}, 'coverage': 'MAPPED_PARTIAL',
              'evidence_refs': ['clause:fixture'], 'source': {'license': 'fixture', 'clause_id': '1',
              'source_ref': 'fixture:license', 'license_version': '1', 'rule_version': 'test'}}


def facts(**kwargs):
    return {k: {'value': v, 'evidence_refs': ['fixture:'+k]} for k,v in kwargs.items()}

class AuditEngineTests(unittest.TestCase):
    def test_permission_does_not_require_action(self):
        a=rule(kind='PERMITTED', req=True); b=rule(kind='PROHIBITED',req=True,rid='two')
        r=license_license(a,b,True)
        self.assertTrue(r['jointly_satisfiable'])  # Both respected by not acting.

    def test_required_action_and_prohibition_incompatible_without_behavior(self):
        a=rule(kind='OBLIGATORY',req=True); b=rule(kind='PROHIBITED',req=True,rid='two')
        r=license_license(a,b,True)
        self.assertFalse(r['jointly_satisfiable'])
        self.assertEqual(r['symbolic_result'],'UNSATISFIABLE_OBLIGATIONS')

    def test_unknown_scope_still_compares(self):
        r=license_license(rule(),rule(req={'not':'notice'}),None)
        self.assertEqual(r['status'],'SCOPE_REVIEW_REQUIRED')
        self.assertFalse(r['activity_jointly_satisfiable'])
        self.assertIsNotNone(r['counterexample'])

    def test_known_scope_exclusion_requires_explicit_confirmation(self):
        self.assertEqual(license_license(rule(),rule(),False)['status'],'SCOPE_EXCLUDED_BY_CONFIRMATION')

    def test_unknown_activity_and_missing_fulfillment_are_distinct(self):
        self.assertEqual(license_behavior(rule(),{})['status'],'APPLICABILITY_UNKNOWN')
        self.assertEqual(license_behavior(rule(),facts(**{'activity:Copy':True}))['status'],'OBLIGATION_OPEN')
        self.assertEqual(license_behavior(rule(),facts(**{'activity:Copy':True,'notice':False}))['status'],'VIOLATION')

    def test_obligatory_record_is_not_dropped_when_required_action_missing(self):
        r=rule(activity='ProvideSource',kind='OBLIGATORY',req=True,when='activity:Distribute')
        f=facts(**{'activity:Distribute':True})
        out,joint=aggregate_obligations([r],{key(r['triple']['S']):f})
        self.assertEqual(len(out),1)
        self.assertTrue(out[0]['applicability'])
        self.assertEqual(out[0]['fulfillment_status'],'UNKNOWN')
        self.assertEqual(out[0]['requirement_expression'],'activity:ProvideSource')

    def test_dedup_preserves_sources_and_evidence(self):
        r=rule(); r2=rule(rid='two')
        f=facts(**{'activity:Copy':True,'notice':True})
        out,joint=aggregate_obligations([r,r2],{key(r['triple']['S']):f})
        self.assertEqual(len(out),1); self.assertEqual(len(out[0]['sources']),2)
        self.assertEqual(out[0]['evidence_refs'],['fixture:notice'])
        self.assertEqual(out[0]['fulfillment_status'],'FULFILLED')

    def test_objects_never_dedup_together(self):
        r=rule(); r2=rule(artifact='P',rid='two')
        out,_=aggregate_obligations([r,r2],{key(r['triple']['S']):{},key(r2['triple']['S']):{}})
        self.assertEqual(len(out),2)

    def test_or_is_not_split_into_two_mandatory_actions(self):
        r=rule(req={'any':['source_copy','written_offer']})
        out,_=aggregate_obligations([r],{key(r['triple']['S']):facts(**{'activity:Copy':True,'written_offer':True})})
        self.assertEqual(len(out),1); self.assertEqual(out[0]['fulfillment_status'],'FULFILLED')

    def test_joint_active_and_candidate_constraints(self):
        r=rule();r2=rule(req={'not':'notice'},when='other_trigger',rid='two')
        out,joint=aggregate_obligations([r,r2],{key(r['triple']['S']):facts(**{'activity:Copy':True})})
        self.assertTrue(joint[0]['active_obligations_jointly_satisfiable'])
        self.assertFalse(joint[0]['all_candidates_jointly_satisfiable'])

class AuditPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload=json.loads((Path(__file__).parent/'fixtures/chain_216.json').read_text())
        cls.result=run(cls.payload)
        cls.vendor=next(c for c in cls.result['cases'] if c['row']['integration']=='代码层面集成')

    def test_current_data_has_no_default_compliant(self):
        s=self.result['summary']
        self.assertEqual(s['statuses'],{'INCOMPLETE_ANALYSIS':215,'OBLIGATIONS_OPEN':1})
        self.assertEqual((s['LINK'],s['BUNDLE'],s['active_open_obligations']),(215,1,4))
        self.assertEqual(s['license_comparisons'],3456)
        self.assertEqual(s['behavior_violations'],0)

    def test_source_inclusion_not_release_bundle(self):
        f=self.vendor['facts_by_subject'][key({'artifact':self.vendor['upstream_id'],'kind':'OriginalArtifact'})]
        self.assertTrue(f['activity:Copy']['value'])
        self.assertIsNone(f['activity:Bundle']['value'])
        self.assertIsNone(f['activity:Distribute']['value'])

    def test_human_fulfillment_closes_only_open_obligations(self):
        cid=self.vendor['case_id']
        h={cid:{'reviewer':'test','facts':{'upstream':{'OriginalArtifact':{
            'preserve_copyright':True,'include_license:MIT':{'value':True,'evidence_refs':['fixture:license-copy']}}}}}}
        result=run(self.payload,h)
        r=next(r for r in result['results'] if r['case_id']==cid)
        self.assertEqual(r['status'],'INCOMPLETE_ANALYSIS')  # Coverage not magically complete.
        self.assertTrue(all(o['fulfillment_status']=='FULFILLED' for o in r['obligations_by_activity'] if o['applicability'] is True))
        self.assertIn('fixture:license-copy',result['evidence_inventory'])

    def test_false_fulfillment_is_violation(self):
        cid=self.vendor['case_id']
        h={cid:{'reviewer':'test','facts':{'upstream':{'OriginalArtifact':{'include_license:MIT':False}}}}}
        self.assertEqual(run(self.payload,h)['summary']['behavior_violations'],2)

    def test_distribution_clause_fulfillment_evidence_chain(self):
        p={'rows':[dict(self.vendor['row'],artifact_license='Apache-2.0')]}
        first=run(p);c=first['cases'][0]
        h={c['case_id']:{'reviewer':'synthetic-test','facts':{'upstream':{'ModifiedArtifact':{
            'activity:Distribute':{'value':True,'evidence_refs':['fixture:release']},
            'include_license:Apache-2.0':True,'mark_changes':True,'distributed_as_source':True,
            'retain_applicable_source_notices':True,'upstream_has_notice':True,'include_applicable_notice':True}}}}}
        result=run(p,h);r=result['results'][0]
        obs=[o for o in r['obligations_by_activity'] if o['activity']=='Distribute' and o['applicability'] is True]
        self.assertEqual(len(obs),4)
        self.assertEqual({s['clause_id'] for o in obs for s in o['sources']},{'4(a)','4(b)','4(c)','4(d)'})
        self.assertTrue(all(o['fulfillment_status']=='FULFILLED' for o in obs))
        self.assertTrue(all('fixture:release' in o['trigger_evidence_refs'] for o in obs))
        self.assertTrue(all(o['evidence_refs'] for o in obs))

    def test_evidence_refs_resolve(self):
        inventory=self.result['evidence_inventory']
        for r in self.result['results']:
            for c in r['license_behavior']['checks']:
                for ref in c['behavior_evidence_refs']+c['clause_evidence_refs']:
                    self.assertIn(ref,inventory)

    def test_outputs_and_human_edits_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'human_input.json').write_text('{"existing":"edit"}')
            write_outputs(run({'rows':[self.vendor['row']]}),out)
            self.assertEqual(json.loads((out/'human_input.json').read_text()),{'existing':'edit'})
            for name in ('license_license.json','license_behavior.json','obligations_by_activity.json','review_tasks.json','evidence_inventory.json'):
                self.assertTrue((out/name).exists())

    def test_invalid_human_values_rejected(self):
        with self.assertRaises(ValueError):run(self.payload,{'unknown':{'reviewer':'test'}})
        with self.assertRaises(ValueError):run(self.payload,{self.vendor['case_id']:{'reviewer':'test','scope_shared':'true'}})

    def test_shared_scope_merges_sources_without_merging_behavior_facts(self):
        p={'rows':[self.vendor['row']]}; c=run(p)['cases'][0]
        u=rule(artifact=c['upstream_id']); d=rule(artifact=c['downstream_id'],rid='two')
        d['triple']['S']['kind']='CombinedProduct'
        h={c['case_id']:{'reviewer':'test','scope_shared':True,'rules':[
            {'triple':r['triple'],'source':r['source']} for r in [u,d]]}}
        r=run(p,h)['results'][0]
        merged=[o for o in r['obligations_by_activity'] if o['activity']=='Copy' and o['subject']['artifact']==c['upstream_id'] and o['requirement_expression']=='notice']
        self.assertEqual(len(merged),1);self.assertEqual(len(merged[0]['sources']),2)
        self.assertTrue(merged[0]['applicability'])
        downstream=next(x for x in r['license_behavior']['checks'] if x['activity']=='Copy' and x['subject']['artifact']==c['downstream_id'])
        self.assertIsNone(downstream['occurred'])

    def test_confirmed_normative_conflict_is_separate_from_violation(self):
        p={'rows':[self.payload['rows'][0]]};c=run(p)['cases'][0]
        u=rule(kind='PROHIBITED',req=True,artifact=c['upstream_id'])
        d=rule(kind='OBLIGATORY',req=True,artifact=c['downstream_id'])
        d['triple']['S']['kind']='CombinedProduct'
        h={c['case_id']:{'reviewer':'test','scope_shared':True,'rules':[
            {'triple':r['triple'],'source':r['source']} for r in [u,d]]}}
        r=run(p,h)['results'][0]
        self.assertEqual(r['status'],'CONSTRAINT_CONFLICT')
        self.assertTrue(r['license_license']['confirmed_constraint_conflicts'])
        self.assertEqual(r['license_behavior']['violations'],[])

    def test_report_template_does_not_expand_status_or_user_text(self):
        payload={'rows':[dict(self.vendor['row'], artifact_name='@@ROWS@@ <script>bad()</script>')]}
        result=run(payload)
        with tempfile.TemporaryDirectory() as folder:
            write_outputs(result,Path(folder))
            page=Path(folder,'report.html').read_text()
            self.assertNotIn('<script>bad()</script>',page)
            self.assertIn('@@ROWS@@',page)
            self.assertIn('OBLIGATIONS_OPEN',page)
            class Counter(HTMLParser):
                count=0
                def handle_starttag(self,tag,attrs):
                    if tag=='tr':self.count+=1
            p=Counter();p.feed(page)
            self.assertEqual(p.count,7)  # Two headers + four obligations + one case.
