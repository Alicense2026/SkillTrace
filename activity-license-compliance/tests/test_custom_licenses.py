import unittest
from license_checker.llm.custom_licenses import repository_id,resolve_custom_source
from license_checker.llm.license_sources import resolve_row_sources

class CustomLicenseTests(unittest.TestCase):
    def test_identity_exact_not_short_name(self):
        self.assertEqual(repository_id('https://github.com/FIM-AI/FIM-ONE.git'),'fim-ai/fim-one')
        self.assertIsNone(repository_id('fim-one'))
        self.assertIsNone(repository_id('https://other.example/fim-ai/fim-one'))
        self.assertIsNone(repository_id('https://github.com/fim-ai/fim-one/tree/main'))
    def test_same_label_different_repositories(self):
        def row(repo):return {'github_url':'https://github.com/'+repo,'github_license':'LicenseRef-Custom'}
        a=resolve_row_sources(row('0xchrisskr/go2-agent-lab'))
        b=resolve_row_sources(row('AbhishekS04/Portfolioo'))
        self.assertNotEqual(a[0]['sha256'],b[0]['sha256'])
        self.assertIn('_licenseref_full/texts/',a[0]['file'])
    def test_fork_not_inferred(self):
        row={'github_url':'https://github.com/unregistered-test-fork/claude-code','github_license':'LicenseRef-Custom'}
        self.assertIsNone(resolve_custom_source(row,'downstream'))
        self.assertEqual(resolve_row_sources(row),[])
    def test_empty_original_is_not_resolved(self):
        row={'github_url':'https://github.com/phamdo627/ai-detection-bypass-gptzero-turnitin','github_license':'LicenseRef-Custom'}
        self.assertEqual(resolve_custom_source(row,'downstream')['status'],'EMPTY_ORIGINAL')
        self.assertEqual(resolve_row_sources(row),[])
    def test_label_must_match_repository(self):
        row={'github_url':'https://github.com/fim-ai/fim-one','github_license':'LicenseRef-Custom'}
        self.assertEqual(resolve_row_sources(row),[])
    def test_exact_existing_source_reused(self):
        row={'github_url':'https://github.com/cognis-digital/localmcphub','github_license':'LicenseRef-Custom'}
        self.assertEqual(resolve_row_sources(row)[0]['file'],'COCL-1.0.txt')
