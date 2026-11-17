import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import review_asc_regressions as r

def response(data):
    return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(data)}]}]}

class HistoricalReviewTests(unittest.TestCase):
    def test_unknown_covered_rule_cannot_hide_lost_candidate(self):
        clause={'start_line':1,'end_line':1,'clause_label':'grant','activities':['Use'],'objects':['OriginalArtifact'],
                'C':{'kind':'PERMITTED'},'actor_role':'licensee','scope_note':'software','condition_explanation':'express grant','obligation_items':[]}
        job={'key':'test','source':{'sha256':'testsha','files':['test.txt']},'lines':['You may use this software.'],'lo':1,'hi':1,'units':[]}
        class Client:
            def __init__(self,cfg):pass
            def create(self,body):return response({'decisions':[{'candidate_id':'C001','decision':'COVERED','covered_rule_ids':['nonexistent'],'reason':'claimed coverage','corrected_clause':None}]})
        with TemporaryDirectory() as td,patch.object(r,'RUN',Path(td)/'review'),patch.object(r.base,'ResponsesClient',Client):
            raw=Path(td)/'raw.json';raw.write_text(json.dumps(response({'clauses':[clause]})))
            with self.assertRaisesRegex(RuntimeError,'valid same-license'):
                r.review_job({'response':str(raw)},job,{'rules':[]},SimpleNamespace(model='test'))
            self.assertEqual(len(list((Path(td)/'review/responses').glob('*.json'))),3)

    def test_exact_existing_rule_overrides_false_add_without_duplicate(self):
        clause={'start_line':1,'end_line':1,'clause_label':'grant','activities':['Use'],'objects':['OriginalArtifact'],
                'C':{'kind':'PERMITTED'},'actor_role':'licensee','scope_note':'software','condition_explanation':'express grant','obligation_items':[]}
        job={'key':'test','source':{'sha256':'testsha','files':['test.txt']},'lines':['You may use this software.'],'lo':1,'hi':1,'units':[]}
        existing=r.repair.as_rule(clause,job)
        class Client:
            def __init__(self,cfg):pass
            def create(self,body):return response({'decisions':[{'candidate_id':'C001','decision':'ADD','covered_rule_ids':[],'reason':'mistaken omission claim','corrected_clause':None}]})
        with TemporaryDirectory() as td,patch.object(r,'RUN',Path(td)/'review'),patch.object(r.base,'ResponsesClient',Client):
            raw=Path(td)/'raw.json';raw.write_text(json.dumps(response({'clauses':[clause]})))
            data,additions=r.review_job({'response':str(raw)},job,{'rules':[existing]},SimpleNamespace(model='test'))
            self.assertEqual(additions,[])
            self.assertEqual(data['decisions'][0]['decision'],'COVERED')
            self.assertEqual(data['decisions'][0]['covered_rule_ids'],[existing['rule_id']])

if __name__=='__main__':unittest.main()
