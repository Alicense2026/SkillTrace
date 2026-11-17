import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import time
import scripts.extract_segmented_asc as module
from scripts.extract_segmented_asc import paragraphs, check

class SegmentedASCTests(unittest.TestCase):
    def test_each_nonblank_line_exactly_once(self):
        lines=['Heading','','a'*4000,'b'*4000,'c','','Last']
        units=paragraphs(lines)
        covered=[i for u in units for i in range(u['start_line'],u['end_line']+1) if lines[i-1].strip()]
        self.assertEqual(covered,[1,3,4,5,7])

    def fixture(self):
        job={'lines':['Retain notices.'],'lo':1,'hi':1,'units':[{'unit_id':'P0001','start_line':1,'end_line':1}]}
        clause={'start_line':1,'end_line':1,'clause_label':'notices','activities':['Distribute'],'objects':['OriginalArtifact'],
                'C':{'kind':'CONDITIONALLY_PERMITTED','when':True,'requires':'notices_retained'},
                'actor_role':'licensee','scope_note':'Copies','condition_explanation':'Retain notices in copies',
                'obligation_items':[{'duty_type':'PERFORM','content':'Retain notices','actor':'licensee','object':'copies','trigger':'copies distributed'}]}
        data={'clauses':[clause],'coverage_notes':[], 'paragraph_audit':[{'unit_id':'P0001','status':'MODELED','clause_labels':['notices'],'reason':'Notice condition modeled'}]}
        return job,data

    def test_notice_condition_valid(self):
        j,d=self.fixture();check(d,j)

    def test_missing_paragraph_rejected(self):
        j,d=self.fixture();d['paragraph_audit']=[]
        with self.assertRaises(ValueError):check(d,j)

    def test_obligation_to_distribute_rejected(self):
        j,d=self.fixture();d['clauses'][0]['C']['kind']='OBLIGATORY'
        with self.assertRaises(ValueError):check(d,j)

    def test_missing_obligation_condition_rejected(self):
        j,d=self.fixture();del d['clauses'][0]['obligation_items'][0]['trigger']
        with self.assertRaises(ValueError):check(d,j)

    def test_failed_parent_recovers_by_validated_children(self):
        job,data=self.fixture()
        job.update(key='test',lines=['Retain notices.','','Retain notices.'],hi=3)
        job['units'].append({'unit_id':'P0002','start_line':3,'end_line':3})
        job['payload']={'target_units':job['units'],'chunk':'1: Retain notices.\n3: Retain notices.'}
        class Client:
            def __init__(self,config):pass
            def create(self,body):
                inp=json.JSONDecoder().raw_decode(body['input'])[0]
                if len(inp['target_units'])>1:raise ValueError('Synthetic oversized parent')
                u=inp['target_units'][0];d=json.loads(json.dumps(data))
                d['clauses'][0]['start_line']=u['start_line'];d['clauses'][0]['end_line']=u['end_line']
                d['paragraph_audit'][0]['unit_id']=u['unit_id']
                return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(d)}]}]}
        with TemporaryDirectory() as td,patch.object(module,'RUN',Path(td)),patch.object(module,'ResponsesClient',Client):
            merged=module.extract(job,SimpleNamespace(model='test'))
            self.assertEqual(len(merged['clauses']),2)
            self.assertEqual({a['unit_id'] for a in merged['paragraph_audit']},{'P0001','P0002'})
            self.assertEqual(len({c['clause_label'] for c in merged['clauses']}),2)
            self.assertEqual(json.loads((Path(td)/'validated/test.json').read_text())['recovery'],'validated child-segment composition')

    def test_concurrent_duplicate_job_calls_api_once(self):
        job,data=self.fixture();job.update(key='same-job',payload={'target_units':job['units']})
        calls=[]
        class Client:
            def __init__(self,config):pass
            def create(self,body):
                calls.append(1);time.sleep(0.05)
                return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(data)}]}]}
        with TemporaryDirectory() as td,patch.object(module,'RUN',Path(td)),patch.object(module,'ResponsesClient',Client):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:module.extract(job,SimpleNamespace(model='test')),range(2)))
            self.assertEqual(len(calls),1)
            self.assertEqual(results[0],results[1])

    def test_concurrent_save_keeps_valid_json(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'shared.json'
            with ThreadPoolExecutor(max_workers=10) as pool:
                list(pool.map(lambda n:module.save(p,{'value':n,'payload':'a'*10000}),range(40)))
            self.assertIn(json.loads(p.read_text())['value'],range(40))
            self.assertEqual(list(Path(td).glob('*.tmp')),[])

if __name__=='__main__':unittest.main()
