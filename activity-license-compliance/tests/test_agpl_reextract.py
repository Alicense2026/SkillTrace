"""Regression checks for the sparse AGPL extractor's lost obligation payload."""
import copy
import unittest
from scripts.reextract_agpl import check


class AGPLExtractionContractTests(unittest.TestCase):
    def setUp(self):
        self.data = {'clauses':[{'start_line':1,'end_line':1,'clause_label':'Network source',
            'activities':['ProvideSource'],'objects':['ModifiedArtifact'],
            'C':{'kind':'OBLIGATORY','when':{'all':['modified','remote_users']},
                 'requires':{'all':['all_users_offered_source','network_access_no_charge']}},
            'actor_role':'licensee','scope_note':'Modified version corresponding source',
            'condition_explanation':'Only when a modified version is used remotely.'}],
            'coverage_notes':[], 'coverage_audit':[{'unit':19,'status':'MODELED',
                'clause_labels':['Network source'],'explanation':'Conditional source offer.'}]}
        self.units=[{'unit':19}]

    def run_check(self, data):
        return check(data,['Network source provision'],1,1,self.units)

    def test_trigger_and_content_preserved(self):
        self.assertEqual(self.run_check(self.data),self.data)

    def test_sparse_obligation_rejected(self):
        d=copy.deepcopy(self.data);d['clauses'][0]['C']={'kind':'OBLIGATORY'}
        with self.assertRaisesRegex(ValueError,'missing trigger'): self.run_check(d)

    def test_no_obligation_to_host(self):
        d=copy.deepcopy(self.data);d['clauses'][0]['activities']=['ProvideNetworkService']
        with self.assertRaisesRegex(ValueError,'actual ProvideSource'): self.run_check(d)

    def test_unaccounted_source_unit_rejected(self):
        d=copy.deepcopy(self.data);d['coverage_audit']=[]
        with self.assertRaisesRegex(ValueError,'every review unit'): self.run_check(d)

    def test_conditional_ban_cannot_become_absolute(self):
        d=copy.deepcopy(self.data);d['clauses'][0]['C']={'kind':'PROHIBITED','requires':'extra_restrictions'}
        with self.assertRaisesRegex(ValueError,'ignores requires'): self.run_check(d)


if __name__=='__main__':unittest.main()
