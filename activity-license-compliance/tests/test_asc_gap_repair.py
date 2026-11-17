import copy
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from scripts import repair_segmented_asc_gaps as r

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.c={'start_line':1,'end_line':1,'clause_label':'old','activities':['Use'],'objects':['OriginalArtifact'],'C':{'kind':'PERMITTED'},'actor_role':'licensee','scope_note':'software','condition_explanation':'express grant','obligation_items':[]}
        self.j={'lines':['Permission to use','Maintain notices'],'lo':1,'hi':2,'units':[{'unit_id':'P1','start_line':1,'end_line':1}],'anchors':[self.c],'recovered':[]}
        self.data={'clauses':[],'coverage_notes':[],'paragraph_audit':[{'unit_id':'P1','status':'MODELED','clause_labels':['old'],'reason':'Existing grant'}],'anchor_review':[]}
    def test_existing_anchor_need_not_be_regenerated(self):
        before=copy.deepcopy(self.j['anchors']);r.validate_patch(self.data,self.j);self.assertEqual(before,self.j['anchors'])
    def test_missing_recovered_review_rejected(self):
        self.j['recovered']=[self.c]
        with self.assertRaises(ValueError):r.validate_patch(self.data,self.j)
    def test_activity_extension_rejected(self):
        c={**self.c,'clause_label':'gap/new','activities':['Delete']};self.data['clauses']=[c]
        with self.assertRaises(ValueError):r.validate_patch(self.data,self.j)
    def test_external_exclusion_remains_explicit(self):
        self.data['paragraph_audit'][0]['status']='EXTERNAL_REFERENCE_EXCLUDED'
        r.validate_patch(self.data,self.j)
        self.assertEqual(self.data['paragraph_audit'][0]['status'],'EXTERNAL_REFERENCE_EXCLUDED')
    def test_cross_section_support_validated(self):
        self.data['clauses']=[{**self.c,'clause_label':'gap/a','supporting_source_ranges':[[2,2]]}]
        r.validate_patch(self.data,self.j)
        self.data['clauses'][0]['supporting_source_ranges']=[[2,3]]
        with self.assertRaises(ValueError):r.validate_patch(self.data,self.j)
    def test_repair_retains_clause_even_if_prior_paragraph_audit_failed(self):
        prior=[]
        broken={'clauses':[self.c],'coverage_notes':[],'paragraph_audit':[]}
        r.base.retain_valid_clauses(broken,prior,self.j)
        result=r.base.retain_valid_clauses({'clauses':[],'coverage_notes':[],'paragraph_audit':[]},prior,self.j)
        self.assertEqual(result['clauses'],[self.c])
    def test_repair_retains_distinct_content_on_label_collision(self):
        prior=[copy.deepcopy(self.c)]
        changed={**self.c,'C':{'kind':'PROHIBITED'}}
        result=r.base.retain_valid_clauses({'clauses':[changed],'coverage_notes':[],'paragraph_audit':[]},prior,self.j)
        self.assertEqual(len(result['clauses']),2)
        self.assertNotEqual(result['clauses'][0]['clause_label'],result['clauses'][1]['clause_label'])
    def test_batched_repair_keeps_all_original_units(self):
        job={**self.j,'key':'test','source':{'files':['test.txt']},'lines':['Permission']*13,
             'units':[{'unit_id':f'P{i}','start_line':i,'end_line':i} for i in range(1,14)],'hi':13,'anchors':[],'gaps':[]}
        fixture=copy.deepcopy(self.c);calls=[]
        class Client:
            def __init__(self,cfg):pass
            def create(self,body):
                inp=json.JSONDecoder().raw_decode(body['input'])[0];calls.append(len(inp['target_units']))
                clauses=[];audits=[]
                for u in inp['target_units']:
                    label='gap/'+u['unit_id'];clauses.append({**fixture,'clause_label':label,'start_line':u['start_line'],'end_line':u['end_line']})
                    audits.append({'unit_id':u['unit_id'],'status':'MODELED','clause_labels':[label],'reason':'Express grant'})
                d={'clauses':clauses,'paragraph_audit':audits,'coverage_notes':[],'anchor_review':[]}
                return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(d)}]}]}
        with TemporaryDirectory() as td,patch.object(r,'RUN',Path(td)),patch.object(r.base,'ResponsesClient',Client):
            result=r.repair(job,SimpleNamespace(model='test'))
            self.assertEqual(len(result['clauses']),13)
            self.assertEqual(len(result['paragraph_audit']),13)
            self.assertEqual(sorted(calls),[1,12])
    def test_conditional_ban_normalization_preserves_condition_and_records_change(self):
        c={**self.c,'clause_label':'gap/ban','C':{'kind':'PROHIBITED','when':True,'requires':'service_used_for_spam'}}
        data={**self.data,'clauses':[c]}
        result=r.normalize_patch_labels(data,self.j)
        self.assertEqual(result['clauses'][0]['C'],{'kind':'CONDITIONALLY_PROHIBITED','when':True,'requires':'service_used_for_spam'})
        self.assertEqual(result['representation_normalizations'][0]['before']['kind'],'PROHIBITED')
        self.assertEqual(data['clauses'][0]['C']['kind'],'PROHIBITED')
    def test_anchor_overwrite_rejected(self):
        self.data['clauses']=[self.c]
        with self.assertRaises(ValueError):r.validate_patch(self.data,self.j)

if __name__=='__main__':unittest.main()
