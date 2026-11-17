"""Resolve local license originals for each trusted chain row.

Provider-specific proprietary text is selected from the asset URL/name. SPDX
texts are selected from the license label. Missing originals stay missing; the
generic `proprietary` label is never treated as a license.
"""
import hashlib
import re
from pathlib import Path

LICENSE_DIR = Path(__file__).resolve().parents[2] / '许可证原文'

SPDX_FILES = {
    '0bsd': '0BSD.txt',
    'bsl-1.0': 'BSL-1.0.txt', 'boost-1.0': 'BSL-1.0.txt',
    'mit': 'LICENSE-MIT.txt', 'mit-0': 'LICENSE-MIT-0.txt',
    'apache-2.0': 'LICENSE-APACHE.txt', 'bsd-2-clause': 'LICENSE-BSD 2-Clause.txt',
    'bsd-3-clause': 'LICENSE-BSD 3-Clause.txt', 'isc': 'LICENSE-ISC.txt',
    'gpl-3.0': 'LICENSE-GPL-3.0.txt', 'gpl-3.0-only': 'LICENSE-GPL-3.0.txt',
    'agpl-3.0': 'LICENSE-AGPL-3.0-only.txt', 'agpl-3.0-only': 'LICENSE-AGPL-3.0-only.txt',
    'agpl-3.0-or-later': 'LICENSE-AGPL-3.0-or-later.txt',
    'mpl-2.0': 'LICENSE-MPL-2.0.txt', 'epl-2.0': 'LICENSE-EPL-2.0.txt',
    'eupl-1.2': 'LICENSE-EUPL-1.2.txt', 'wtfpl': 'LICENSE-WTFPL.txt',
    'postgresql': 'PostgreSQL License.txt', 'postgresql-license': 'PostgreSQL License.txt',
    'cc0-1.0': 'LICENSE-CC0-1.0.txt', 'cc-by-4.0': 'LICENSE-CC-BY-4.0.txt',
    'cc-by-sa-4.0': 'LICENSE-CC-BY-SA-4.0.txt', 'cc-by-nc-4.0': 'CC-BY-NC-4.0.txt',
    'cc-by-nc-sa-4.0': 'LICENSE-CC-BY-NC-SA-4.0.txt',
    'openrail-m': 'CreativeML-OpenRAIL-M.txt', 'openrail++-m': 'openRAIL++-M License.txt',
    # User-supplied expert confirmation: openrail++ denotes openRAIL++-M.
    'openrail++': 'openRAIL++-M License.txt',
    'baichuan2-community-license': 'Baichuan2-community-license.txt',
    'busl-1.1': 'BUSL-1.1.txt', 'elastic-2.0': 'ELASTIC-LICENSE-2.0.txt',
    'gpl-2.0': 'GPL-2.0-or-later.txt', 'gpl-2.0-only': 'GPL-2.0-or-later.txt',
    'gpl-2.0-or-later': 'GPL-2.0-or-later.txt',
    'mulanpsl-2.0': 'MulanPSL-2.0.txt',
    'polyform-internal-use-1.0.0': 'PolyForm+Internal+Use+1.0.0.txt',
    'polyform-noncommercial-1.0.0': 'PolyForm+NonCommercial+1.0.0.txt',
    'polyform-perimeter-1.0.1': 'PolyForm+Perimeter+1.0.1.txt',
    'polyform-small-business-1.0.0': 'PolyForm+Small+Business+1.0.0.txt',
    'sustainable-use': 'Sustainable+Use+License+v1.0.md',
    'cdla-permissive-2.0': 'CDLA-Permissive-2.0.txt',
    'cc-by-nc-nd-4.0': 'CC-BY-NC-ND-4.0.txt',
    'odc-by': 'ODC-By-1.0.txt', 'odc-by-1.0': 'ODC-By-1.0.txt',
    'licenseref-cocl-1.0': 'COCL-1.0.txt',
    'creativeml-openrail-m': 'CreativeML-OpenRAIL-M.txt',
    # Do not map LicenseRef-Blockscout to blockscout.txt: the supplied file
    # is hosted-service Terms of Use, not an identified repository license.
}

PROVIDERS = (
    ('openai', ('platform.openai.com', 'openai.com'), ('openai', 'gpt-', 'chatgpt'), 'OpenAI.txt'),
    ('anthropic', ('anthropic.com',), ('anthropic', 'claude'), 'ANTHROPIC.txt'),
    ('deepseek', ('deepseek.com',), ('deepseek',), 'DeepSeek.txt'),
    ('mistral', ('mistral.ai',), ('mistral',), 'mistral+license.txt'),
    ('google-gemini', ('ai.google.dev',), ('gemini',), 'Gemini API Additional Terms of Serv.txt'),
    ('aliyun-bailian', ('aliyun.com',), ('aliyun', 'qwen', 'dashscope'), 'aliyun.txt'),
    ('zhipu-bigmodel', ('bigmodel.cn',), ('bigmodel', 'zhipu', 'glm-'), 'bigmodel 智谱用户协议.txt'),
    ('moonshot', ('moonshot.cn',), ('moonshot', 'kimi'), 'Kimi+%E5%BC%80%E6%94%BE%E5%B9%B3%E5%8F%B0%E6%9C%8D%E5%8A%A1%E5%8D%8F%E8%AE%AE.txt'),
    ('baidu-cloud', ('cloud.baidu.com',), ('ernie', 'wenxin'), '百度智能云.txt'),
    ('cohere-api', ('cohere.com',), ('cohere',), 'Cohere+Legal+Terms+%26amp%3Bamp%3B+Policies.txt'),
)

LLAMA_FILES = {
    'llama 2': 'LLAMA 2 COMMUNITY LICENSE AGREEMENT.txt',
    'llama2': 'LLAMA 2 COMMUNITY LICENSE AGREEMENT.txt',
    'llama 3.1': 'LLAMA 3.1 COMMUNITY LICENSE AGREEMENT.txt',
    'llama3.1': 'LLAMA 3.1 COMMUNITY LICENSE AGREEMENT.txt',
    'llama 3.2': 'LLAMA 3.2 COMMUNITY LICENSE AGREEMENT.txt',
    'llama3.2': 'LLAMA 3.2 COMMUNITY LICENSE AGREEMENT.txt',
    'llama 3.3': 'LLAMA 3.3 COMMUNITY LICENSE AGREEMENT.txt',
    'llama3.3': 'LLAMA 3.3 COMMUNITY LICENSE AGREEMENT.txt',
    'llama 4': 'LLAMA 4 COMMUNITY LICENSE AGREEMENT.txt',
    'llama4': 'LLAMA 4 COMMUNITY LICENSE AGREEMENT.txt',
    'llama 3': 'LLAMA 3 COMMUNITY LICENSE AGREEMENT.txt',
    'llama3': 'LLAMA 3 COMMUNITY LICENSE AGREEMENT.txt',
}


def is_lgpl_row(row):
    return any('lgpl' in str(row.get(k, '')).casefold()
               for k in ('artifact_license', 'github_license'))


def _read(path):
    path = LICENSE_DIR / path
    if not path.is_file():
        return None
    raw = path.read_bytes()
    return {'file': path.relative_to(LICENSE_DIR).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'text': raw.decode('utf-8-sig', errors='replace')}


def _provider(row):
    name = str(row.get('artifact_name', '')).casefold()
    url = str(row.get('artifact_url', '')).casefold()
    # Prefer the explicit asset URL. Fall back to the asset name only for a
    # provider-specific name, never for the generic proprietary label.
    for provider, domains, names, filename in PROVIDERS:
        if any(domain in url for domain in domains):
            return provider, filename
    for provider, domains, names, filename in PROVIDERS:
        if any(token in name for token in names):
            return provider, filename
    if 'llama' in name or 'llama.com' in url:
        normalized = re.sub(r'[^a-z0-9]+', '', name)
        for version in ('4', '3.3', '3.2', '3.1', '3', '2'):
            if 'llama' + version.replace('.', '') in normalized:
                marker = 'llama ' + version
                return 'meta-' + marker.replace(' ', '-').replace('.', '-'), LLAMA_FILES[marker]
    return None


def resolve_row_sources(row):
    """Return source records and source hashes for the two sides of a row."""
    resolved = []
    for side, field in (('upstream', 'artifact_license'), ('downstream', 'github_license')):
        label = str(row.get(field, '')).strip()
        if 'lgpl' in label.casefold():
            continue
        labels = re.split(r'\s+OR\s+', label, flags=re.IGNORECASE)
        for source_label in labels:
            candidate = None
            provider = None
            custom_mapping = None
            if side == 'upstream' and source_label.casefold() == 'proprietary':
                match = _provider(row)
                if match:
                    provider, filename = match
                    candidate = _read(filename)
            elif source_label.casefold().startswith('licenseref-') and (row.get('github_url') if side == 'downstream' else row.get('artifact_url')):
                from .custom_licenses import resolve_custom_source
                custom_mapping = resolve_custom_source(row, side)
                if custom_mapping and custom_mapping['status'] == 'AVAILABLE':
                    candidate = _read(custom_mapping['filename'])
                    if candidate and candidate['sha256'] != custom_mapping['sha256']:
                        raise ValueError('Custom original changed after repository mapping')
            else:
                filename = SPDX_FILES.get(source_label.casefold())
                if filename:
                    candidate = _read(filename)
                elif source_label.casefold() in {'llama2', 'llama3', 'llama3.1', 'llama3.2', 'llama3.3', 'llama4'}:
                    filename = LLAMA_FILES.get(source_label.casefold())
                    if filename:
                        candidate = _read(filename)
            ref = f'license-text:{side}:{hashlib.sha256((source_label + "|" + str(row.get("artifact_name", ""))).encode()).hexdigest()[:16]}'
            if candidate:
                if provider == 'cohere-api':
                    # This supplied compilation also contains partner-installed
                    # product/North terms, which must not govern direct API use.
                    lines = candidate['text'].splitlines()
                    starts = [n for n,line in enumerate(lines,1) if line.strip() == 'Commercial SaaS Agreement']
                    if len(starts) != 1:
                        raise ValueError('Cohere source requires an unambiguous Commercial SaaS Agreement section')
                    candidate['applicable_line_range'] = [starts[0], len(lines)]
                    candidate['scope_note'] = 'Direct API: Commercial SaaS Agreement only; excludes partner Client License Agreement and North schedule.'
                resolved.append({'side': side, 'license_label': source_label, 'provider_match': provider,
                                 'source_ref': ref, 'file': candidate['file'],
                                 'sha256': candidate['sha256'], 'text': candidate['text'],
                                 **({'repository_mapping':custom_mapping['repository'],'original_license_label':custom_mapping['license_label']} if custom_mapping else {}),
                                 **{k:candidate[k] for k in ('applicable_line_range','scope_note') if k in candidate}})
            elif source_label.casefold() == 'proprietary':
                resolved.append({'side': side, 'license_label': source_label, 'provider_match': provider,
                                 'source_ref': ref, 'file': None, 'sha256': None,
                                 'text': None, 'missing': True})
    return resolved


def source_manifest():
    result = []
    if not LICENSE_DIR.is_dir():
        return result
    for path in sorted(p for p in LICENSE_DIR.rglob('*') if p.is_file() and p.suffix.lower() in {'.txt', '.md'}):
        raw = path.read_bytes()
        result.append({'file': path.relative_to(LICENSE_DIR).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest()})
    return result
