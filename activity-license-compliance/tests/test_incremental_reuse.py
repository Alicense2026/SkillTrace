import importlib.util
import unittest
import tempfile
import json
from pathlib import Path
from license_checker.llm.aggregate_input import _asset_identity

spec=importlib.util.spec_from_file_location('incremental',Path(__file__).resolve().parents[1]/'scripts/run_combination_incremental.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class IncrementalReuseTests(unittest.TestCase):
    def test_reuse_requires_direction_hash_and_behavior(self):
        def task(up='u',down='d',sha='1',mode='远程服务调用（修改不适用）'):
            return {'license_sources':[{'side':'upstream','file':up,'sha256':sha},{'side':'downstream','file':down,'sha256':'2'}],'trusted_row':{'调用方式（代码修改）':mode}}
        self.assertNotEqual(module.key(task()),module.key(task(up='d',down='u')))
        self.assertNotEqual(module.key(task()),module.key(task(sha='changed')))
        self.assertNotEqual(module.key(task()),module.key(task(mode='代码层面集成（修改：是）')))
    def test_remapping_keeps_original(self):
        original={'case_id':'old','subject':{'artifact':'old:upstream'},'refs':['ref-old']}
        changed=module.remap(original,{'old':'new'})
        self.assertEqual(changed['subject']['artifact'],'new:upstream')
        self.assertEqual(original['subject']['artifact'],'old:upstream')
    def test_new_provider_titles_are_routable(self):
        for label in ('Cohere Commercial SaaS Agreement','Kimi 模型服务协议（用户协议）','百度智能云用户服务协议'):
            license,name,url,reason=_asset_identity(label)
            self.assertEqual(license,'proprietary');self.assertTrue(url);self.assertIsNone(reason)

    def test_report_deduplicates_groups_and_weight(self):
        finding={'status':'POTENTIAL_CONFLICT','activity':'Use','reason':'test'}
        entry={'case_id':'case','status':'SUCCESS','origin':'NEW','aggregate_count':10,
               'combination':{'GitHub许可证':'MIT','资产许可证原文标题/标签':'MIT','调用方式（代码修改）':'远程服务调用'},
               'analysis':{'license_license_findings':[finding,finding], 'license_behavior_findings':[],
                           'overall_status':'OBLIGATIONS_OPEN','review_items':[], 'obligations':[], 'limitations':[]}}
        with tempfile.TemporaryDirectory() as temp:
            module.report(Path(temp),[entry])
            metrics=json.loads(Path(temp,'conflict_statistics.json').read_text())
            metric=next(m for m in metrics if m['category']=='License–License' and m['status']=='POTENTIAL_CONFLICT')
            self.assertEqual((metric['findings'],metric['groups'],metric['relationships']),(2,1,10))
