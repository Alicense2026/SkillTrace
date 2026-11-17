import unittest
from copy import deepcopy
from scripts.extend_asc_corpus import chunks, validate
from license_checker.llm.license_sources import resolve_row_sources, source_manifest
from scripts.finalize_asc_extension import reviewed


class ExtensionTests(unittest.TestCase):
    def test_overlapping_chunks_cover_every_source_line(self):
        lines=['license line '+str(i) for i in range(300)]
        spans=list(chunks(lines, budget=500))
        covered={i for lo,hi in spans for i in range(lo,hi+1)}
        self.assertEqual(covered,set(range(1,301)))

    def test_model_cannot_cite_outside_supplied_chunk(self):
        data={'clauses':[{'start_line':1,'end_line':1,'clause_label':'grant',
                          'activities':['Use'],'objects':['OriginalArtifact'],
                          'C':{'kind':'PERMITTED'},'actor_role':'licensee',
                          'scope_note':'licensed program','condition_explanation':'unconditional'}],
              'coverage_notes':[]}
        validate(data,['grant','other'],1,1)
        invalid=deepcopy(data); invalid['clauses'][0]['end_line']=2
        with self.assertRaises(ValueError):validate(invalid,['grant','other'],1,1)
        invalid=deepcopy(data);invalid['clauses'][0]['C']={'kind':'CONDITIONALLY_PERMITTED'}
        with self.assertRaises(ValueError):validate(invalid,['grant'],1,1)

    def test_markdown_original_and_new_labels_are_resolved(self):
        rows=resolve_row_sources({'github_license':'Sustainable-Use','artifact_license':'LicenseRef-COCL-1.0'})
        self.assertEqual({r['file'] for r in rows},{'Sustainable+Use+License+v1.0.md','COCL-1.0.txt'})
        self.assertIn('Sustainable+Use+License+v1.0.md',{r['file'] for r in source_manifest()})

    def test_service_terms_do_not_replace_repository_license(self):
        self.assertEqual(resolve_row_sources({'github_license':'LicenseRef-Blockscout'}),[])

    def test_conditional_ban_does_not_become_blanket_ban(self):
        rule={'license_id':'example.txt','license_source_id':'src-test','clause_id':'L1-L2',
              'ASC':{'A':'ProvideNetworkService','S':{'artifact':'$LICENSED_MATERIAL','kind':'OriginalArtifact'},
                     'C':{'kind':'PROHIBITED','requires':'third_party_gets_substantial_features'}},
              'scope_note':'Only the specified hosted-service use is restricted.', 'condition_explanation':'The hosted-service trigger.'}
        out=reviewed(rule)
        self.assertEqual(out['ASC']['C']['kind'],'CONDITIONALLY_PROHIBITED')
        self.assertEqual(out['ASC']['C']['requires'],'third_party_gets_substantial_features')

    def test_cohere_api_excludes_partner_agreement(self):
        sources=resolve_row_sources({'artifact_license':'proprietary','artifact_url':'https://docs.cohere.com/docs/models'})
        self.assertEqual(len(sources),1)
        source=sources[0];lo,hi=source['applicable_line_range']
        self.assertEqual(source['text'].splitlines()[lo-1],'Commercial SaaS Agreement')
        self.assertGreater(lo,1)

if __name__=='__main__':unittest.main()
