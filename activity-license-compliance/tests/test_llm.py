"""Network-free Responses protocol, prompt, resume and validation tests."""
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from license_checker.asc import permission, relation
from license_checker.llm.config import ExperimentConfig, load_config
from license_checker.llm.prompting import load_cases, build_request
from license_checker.llm.casebook import compact_figure_cases, load_patterns, compact_patterns
from license_checker.llm.client import ResponsesClient, APIError, extract_text
from license_checker.llm.schema import parse_result
from license_checker.llm.experiment import run_experiment, prepare_llm_case
from license_checker.input_files import load_input

ROOT=Path(__file__).resolve().parents[1]

def answer(cid):
    return {'case_id':cid,'asc_rules':[],'license_license_findings':[],
            'license_behavior_findings':[],'obligations':[],'review_items':['Incomplete mapping'],
            'overall_status':'INCOMPLETE_ANALYSIS','limitations':['Mock output only.']}

class FakeClient:
    def __init__(self):self.calls=[]
    def create(self,body):
        self.calls.append(copy.deepcopy(body))
        user=json.loads(body['input'][0]['content'][0]['text'])
        assert len(user['figure10_cases']['cases'])==12
        return {'id':'mock-response','status':'completed','model':body['model'],
                'usage':{'input_tokens':100,'output_tokens':20},
                'output':[{'type':'reasoning','summary':[]},{'type':'message','content':[
                    {'type':'output_text','text':json.dumps(answer(user['task']['case_id']))}]}]}

class LLMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload=json.loads((ROOT/'examples/audit_distribution_case.json').read_text())
        source=ROOT/'examples/audit_distribution_case.json'
        cls.case=prepare_llm_case(cls.payload['rows'][0],0,str(source))
        cls.inventory={cls.case['source_ref']:{'kind':'TRUSTED_CHAIN_RECORD','raw_record':cls.case['row']}}

    def request(self,config=None):
        return build_request(config or ExperimentConfig(),self.case,copy.deepcopy(self.inventory))

    def test_12_cases_40_counterexamples(self):
        d=load_cases();self.assertEqual(len(d['cases']),12)
        self.assertEqual(sum(len(c['asc_terms']) for c in d['cases']),40)
        self.assertEqual([c['occurrences'] for c in d['cases']],[14873,5082,261,1569,525,111,84,37,34,2417,465,249])
        for c in d['cases']:
            for term in c['asc_terms']:
                u=term['asc'];v=term['counterexample']['downstream_asc']
                joint={'all':[u['C']['when'],permission(u['C']),permission(v['C'])]}
                self.assertFalse(relation(True,joint)['jointly_satisfiable'],term['id'])

    def test_full_examples_in_every_request(self):
        body,m=self.request();user=json.loads(body['input'][0]['content'][0]['text'])
        self.assertEqual(user['figure10_cases'],compact_figure_cases(load_cases()));self.assertEqual(m['example_count'],12)
        self.assertEqual(user['conflict_patterns'],compact_patterns(load_patterns()));self.assertEqual(m['pattern_count'],12)
        self.assertTrue(user['task']['structured_asc_rules'])
        compact_rules=user['task']['structured_asc_rules']
        self.assertEqual(sum(len(group['terms']) for group in compact_rules),m['structured_asc_rule_count'])
        self.assertTrue(all('source_excerpt' in group and group['terms'] for group in compact_rules))
        self.assertTrue(all('text' not in source and source['text_included'] is False
                            for source in user['task']['license_sources']))
        self.assertEqual(user['task']['structured_asc_corpus']['schema_version'],'asc-corpus-1.0')
        self.assertNotIn('checked_license_pairs',user['task'])
        self.assertNotIn('known_partial_rules',user['task'])
        self.assertEqual(body['model'],'gpt-6-luna');self.assertFalse(body['store'])
        self.assertEqual(self.request()[1]['request_sha256'],m['request_sha256'])
        with self.assertRaisesRegex(ValueError,'no cases were silently truncated'):
            self.request(ExperimentConfig(max_input_chars=10))

    def test_contract_identity_and_evidence(self):
        _,m=self.request();d=answer(m['case_id'])
        parse_result(json.dumps(d),m['case_id'],m['allowed_subjects'],m['allowed_refs'])
        marked=answer(m['case_id']);marked['schema_version']='llm-analysis-2.0'
        self.assertNotIn('schema_version',parse_result(json.dumps(marked),m['case_id'],m['allowed_subjects'],m['allowed_refs']))
        marked_missing_id=answer(m['case_id']);marked_missing_id.pop('case_id');marked_missing_id['schema_version']='llm-analysis-2.0'
        self.assertEqual(parse_result(json.dumps(marked_missing_id),m['case_id'],m['allowed_subjects'],m['allowed_refs'])['case_id'],m['case_id'])
        bad=answer(m['case_id']);bad['overall_status']=[]
        with self.assertRaises(ValueError):parse_result(json.dumps(bad),m['case_id'],m['allowed_subjects'],m['allowed_refs'])
        bad=answer(m['case_id']);bad['license_license_findings']=[{'activity':[], 'status':'POTENTIAL_CONFLICT','reason':'x','source_refs':[],'figure_case_refs':[]}]
        with self.assertRaises(ValueError):parse_result(json.dumps(bad),m['case_id'],m['allowed_subjects'],m['allowed_refs'])
        d['case_id']='wrong'
        with self.assertRaises(ValueError):parse_result(json.dumps(d),m['case_id'],m['allowed_subjects'],m['allowed_refs'])
        d=answer(m['case_id']);d['license_license_findings']=[{'activity':'Copy','status':'POTENTIAL_CONFLICT','reason':'x','source_refs':['invented'],'figure_case_refs':[]}]
        with self.assertRaises(ValueError):parse_result(json.dumps(d),m['case_id'],m['allowed_subjects'],m['allowed_refs'])
        for text in ('{"case_id":"a","case_id":"b"}','```json\n{}\n```'):
            with self.assertRaises(ValueError):parse_result(text,m['case_id'],[],[])

    def test_responses_content_and_incomplete(self):
        body,_=self.request();self.assertIn('case_id',extract_text(FakeClient().create(body)))
        for response in ({'status':'incomplete','output':[]},{'status':'completed','output':[]},
                         {'status':'completed','output':[None]},
                         {'status':'completed','output':[{'type':'message','content':[None]}]},
                         {'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]}):
            with self.assertRaises(APIError):extract_text(response)

    def test_http_auth_retry_and_path(self):
        class Opener:
            def __init__(self):self.calls=[]
            def open(self,request,timeout):
                self.calls.append(request)
                if len(self.calls)==1:raise HTTPError(request.full_url,429,'busy',{},io.BytesIO(b'private'))
                return io.BytesIO(b'{"status":"completed","output":[]}')
        o=Opener();wait=[]
        with patch.dict(os.environ,{'LICENSE_API_KEY':'TEST_SECRET_ONLY'}):
            ResponsesClient(ExperimentConfig(),opener=o,sleep=wait.append).create({})
        self.assertEqual(len(o.calls),2);self.assertEqual(wait,[1])
        self.assertEqual(o.calls[0].full_url,'https://api.example.invalid/responses')
        self.assertEqual(o.calls[0].get_header('Authorization'),'Bearer TEST_SECRET_ONLY')

    def test_auth_error_not_retried_or_echoed(self):
        class Opener:
            calls=0
            def open(self,request,timeout):
                self.calls+=1
                raise HTTPError(request.full_url,401,'TEST_SECRET_ONLY',{},io.BytesIO(b'TEST_SECRET_ONLY'))
        o=Opener()
        with patch.dict(os.environ,{'LICENSE_API_KEY':'TEST_SECRET_ONLY'}):
            with self.assertRaises(APIError) as err:ResponsesClient(ExperimentConfig(),o).create({})
        self.assertEqual(o.calls,1);self.assertNotIn('TEST_SECRET_ONLY',str(err.exception))

    def test_http_error_only_exposes_sanitized_service_code(self):
        class Opener:
            def open(self,request,timeout):
                body=b'{"code":"UPSTREAM_BUSY","message":"TEST_SECRET_ONLY"}'
                raise HTTPError(request.full_url,503,'busy',{},io.BytesIO(body))
        with patch.dict(os.environ,{'LICENSE_API_KEY':'TEST_SECRET_ONLY'}):
            with self.assertRaises(APIError) as err:ResponsesClient(ExperimentConfig(),Opener(),sleep=lambda _:None).create({})
        self.assertIn('UPSTREAM_BUSY',str(err.exception))
        self.assertNotIn('TEST_SECRET_ONLY',str(err.exception))

    def test_config_validation(self):
        self.assertEqual(load_config(ROOT/'configs/experiment.toml').model,'gpt-6-luna')
        for cfg in (ExperimentConfig(base_url='http://example.com'),ExperimentConfig(base_url='https://u:p@example.com'),ExperimentConfig(max_retries=-1)):
            with self.assertRaises(ValueError):cfg.validate()

    def test_local_api_key_file_fallback_and_env_priority(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);key_file=d/'api.rtf';key_file.write_text(r'{\\rtf1 sk-test_key_012345678901234567890123456789}',encoding='utf-8')
            cfg=ExperimentConfig(api_key_file=str(key_file)).validate()
            with patch.dict(os.environ,{},clear=True):
                self.assertEqual(cfg.api_key(),'sk-test_key_012345678901234567890123456789')
            with patch.dict(os.environ,{'LICENSE_API_KEY':'sk-env_012345678901234567890123456789'},clear=True):
                self.assertEqual(cfg.api_key(),'sk-env_012345678901234567890123456789')
            key_file.write_text('two sk-test_key_012345678901234567890123456789 sk-other_key_012345678901234567890123456789',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'multiple candidate tokens'):
                cfg.api_key()

    def test_dry_live_resume_and_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'input.json';source.write_text(json.dumps(self.payload));out=Path(d)/'run'
            config=ROOT/'configs/experiment.toml'
            self.assertEqual(run_experiment(source,out,config)['dry_run'],1)
            self.assertFalse((out/'responses').exists())
            fake=FakeClient();self.assertEqual(run_experiment(source,out,config,execute=True,client=fake)['success'],1)
            cid=json.loads((out/'summary.json').read_text())['records'][0]['case_id']
            for folder in ('license_license','license_activity','obligations'):
                self.assertTrue((out/'three_outputs'/folder/(cid+'.json')).exists())
            self.assertIn('成功：1', (out/'final_report.md').read_text())
            self.assertEqual(run_experiment(source,out,config,execute=True,client=fake)['resumed'],1)
            self.assertEqual(len(fake.calls),1)
            with self.assertRaises(ValueError):run_experiment(source,out,config,limit=2)
            self.assertFalse(json.loads(next((out/'results').glob('*.json')).read_text())['auto_applied'])

    def test_prompt_overflow_is_recorded_without_aborting_batch(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);cfg=d/'config.toml'
            cfg.write_text('[experiment]\nmax_input_chars=10\n',encoding='utf-8')
            summary=run_experiment(ROOT/'examples/audit_distribution_case.json',d/'run',cfg,limit=1)
            self.assertEqual(summary['errors'],1)
            result=next((d/'run'/'results').glob('*.json'))
            self.assertEqual(json.loads(result.read_text())['stage'],'PROMPT_PREPARATION')

    def test_invalid_json_logged_as_failure(self):
        class Bad(FakeClient):
            def create(self,body):
                r=super().create(body);r['output'][-1]['content'][0]['text']='not JSON';return r
        with tempfile.TemporaryDirectory() as d:
            r=run_experiment(ROOT/'examples/audit_distribution_case.json',Path(d)/'run',ROOT/'configs/experiment.toml',execute=True,client=Bad())
            self.assertEqual(r['errors'],1);self.assertEqual(r['success'],0)
            self.assertEqual(len(list((Path(d)/'run/responses').glob('*.json'))),1)

    @unittest.skipUnless((ROOT/'Figure 10.pdf').exists(), 'Original identifying PDF is excluded from the public archive')
    def test_pdf_fingerprint(self):
        import hashlib
        self.assertEqual(load_cases()['source_sha256'],hashlib.sha256((ROOT/'Figure 10.pdf').read_bytes()).hexdigest())

    def test_csv_adapter(self):
        import csv
        from license_checker.input_files import CSV_COLUMNS
        row=self.payload['rows'][0]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.csv'
            with p.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(CSV_COLUMNS));w.writeheader();w.writerow({h:row.get(k,'') for h,k in CSV_COLUMNS.items()})
            data,_=load_input(p)
            self.assertEqual(data['rows'][0]['integration'],row['integration'])
            self.assertEqual(data['rows'][0]['artifact_name'],row['artifact_name'])
            self.assertEqual(data['rows'][0]['artifact_kind'],'unspecified')

    def test_license_combination_csv_adapter_skips_unknown_and_maps_unversioned_llama4(self):
        import csv
        fields=['GitHub许可证','资产许可证原文标题/标签','调用方式（代码修改）','数量']
        source_rows=[
            {'GitHub许可证':'Apache-2.0','资产许可证原文标题/标签':'Llama（版本未识别；本地原文未匹配）',
             '调用方式（代码修改）':'远程服务调用（修改不适用）','数量':'7'},
            {'GitHub许可证':'unknown','资产许可证原文标题/标签':'MIT',
             '调用方式（代码修改）':'代码层面集成（修改：是）','数量':'3'},
        ]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'许可证组合统计.csv'
            with p.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(source_rows)
            data,_=load_input(p)
        self.assertEqual(data['summary']['input_format'],'license_combination_csv')
        self.assertEqual(data['summary']['represented_relationships'],10)
        llama,unknown=data['rows']
        self.assertEqual(llama['artifact_name'],'llama 4')
        self.assertEqual(llama['_aggregate_weight'],7)
        self.assertIsNone(llama['_aggregate_skip_reason'])
        self.assertTrue(unknown['_aggregate_skip_reason'])

    def test_offset_preserves_original_case_id(self):
        payload={'rows':[self.payload['rows'][0]]*3}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.json';p.write_text(json.dumps(payload))
            r=run_experiment(p,Path(d)/'run',ROOT/'configs/experiment.toml',offset=2)
            self.assertTrue(r['records'][0]['case_id'].startswith('chain-0003-'))


class PromptV2Tests(unittest.TestCase):
    def test_compaction_restores_all_40_asc_terms(self):
        source=load_cases(); compact=compact_figure_cases(source)
        restored={}
        for row in compact['cases']:
            for binding in row['term_bindings']:
                t=copy.deepcopy(compact['templates'][binding['template_id']]['asc'])
                t['S']['artifact']=row['scope_binding']
                restored[binding['term_id']]=t
        original={t['id']:t['asc'] for c in source['cases'] for t in c['asc_terms']}
        self.assertEqual(restored,original)
        self.assertEqual(len(restored),40)

    def test_all_synthetic_pairs_and_boundary_variants(self):
        from license_checker.audit_engines import license_license, license_behavior
        def rule(t):return {'triple':t,'rule_id':'synthetic','evidence_refs':['synthetic'],'coverage':'MAPPED_PARTIAL'}
        variants=0
        for pattern in load_patterns()['patterns']:
            for v in pattern['variants']:
                variants+=1
                with self.subTest(pattern=pattern['pattern_id'],variant=v['id']):
                    if v['task']=='LICENSE_LICENSE':
                        result=license_license(rule(v['upstream_asc']),rule(v['downstream_asc']),v['scope_shared'])
                    else:
                        fs={k:{'value':x,'evidence_refs':['synthetic']} for k,x in v['facts'].items()}
                        result=license_behavior(rule(v['rule']),fs)
                    self.assertEqual(result['status'],v['expected_engine_status'])
        self.assertEqual(variants,32)

    def test_conditional_obligation_without_manual_review(self):
        d=answer('example');d['review_items']=[];d['overall_status']='OBLIGATIONS_OPEN'
        s={'artifact':'example:upstream','kind':'OriginalArtifact'}
        d['obligations']=[{'activity':'Use','subject':s,'requirement':'Use only under the noncommercial condition',
          'trigger':'activity:Use','applicability':True,'fulfillment_status':'UNKNOWN',
          'unresolved_predicates':['commercial_use'],'source_refs':['rule:example']}]
        result=parse_result(json.dumps(d),'example',[s],['rule:example'])
        self.assertEqual(result['review_items'],[])
        self.assertEqual(result['obligations'][0]['fulfillment_status'],'UNKNOWN')
        d['obligations'][0]['applicability']='true'
        with self.assertRaises(ValueError):parse_result(json.dumps(d),'example',[s],['rule:example'])

    def test_prompt_change_invalidates_run_manifest(self):
        from license_checker.llm import experiment
        with tempfile.TemporaryDirectory() as d:
            source=ROOT/'examples/audit_distribution_case.json';config=ROOT/'configs/experiment.toml'
            run_experiment(source,d,config)
            changed=copy.deepcopy(load_patterns());changed['version']='changed'
            with patch.object(experiment,'load_patterns',return_value=changed):
                with self.assertRaisesRegex(ValueError,'changed'):
                    run_experiment(source,d,config)

    def test_compact_contrastive_cases_are_lossless(self):
        raw=load_patterns();compact=compact_patterns(raw)
        restored=copy.deepcopy(compact['patterns'])
        for pattern in restored:
            for variant in pattern['variants']:
                for field in ('upstream_asc','downstream_asc','rule'):
                    ref=variant.pop(field+'_ref',None)
                    if ref is not None:variant[field]=compact['rules'][ref]
        self.assertEqual(restored,raw['patterns'])
