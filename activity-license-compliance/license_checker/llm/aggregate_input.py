"""Adapt the repository-agnostic license-combination CSV to experiment cases."""
import json
import re
from pathlib import Path

from .license_sources import resolve_row_sources
from .prompting import ASC_CORPUS_PATH


AGGREGATE_COLUMNS = {
    'GitHub许可证', '资产许可证原文标题/标签', '调用方式（代码修改）', '数量'
}

PROVIDER_TITLES = {
    'cohere commercial saas agreement': ('cohere', 'https://docs.cohere.com/'),
    'kimi 模型服务协议（用户协议）': ('kimi', 'https://platform.moonshot.cn/'),
    '百度智能云用户服务协议': ('ernie', 'https://cloud.baidu.com/'),
    'openai services agreement': ('openai', 'https://platform.openai.com/docs/models'),
    'anthropic commercial terms of service': ('claude', 'https://docs.anthropic.com/en/docs/about-claude/models'),
    'gemini api additional terms of service': ('gemini', 'https://ai.google.dev/gemini-api/docs/models'),
    'deepseek open platform terms of service': ('deepseek', 'https://api-docs.deepseek.com/quick_start/pricing'),
    '阿里云百炼服务特别说明': ('qwen', 'https://help.aliyun.com/zh/model-studio/models'),
    '智谱开放平台用户协议': ('zhipu glm', 'https://open.bigmodel.cn/dev/api'),
    'mistral ai commercial terms of service': ('mistral', 'https://docs.mistral.ai/getting-started/models/'),
}


def _asset_identity(label):
    folded = re.sub(r'\s+', ' ', label.strip()).casefold()
    if folded in PROVIDER_TITLES:
        name, url = PROVIDER_TITLES[folded]
        return 'proprietary', name, url, None
    if 'llama' in folded:
        # The user explicitly directs unresolved Llama versions to Llama 4.
        match = re.search(r'llama\s*(4|3\.3|3\.2|3\.1|3|2)', folded)
        if match:
            version = match.group(1)
            return 'proprietary', 'llama ' + version, 'https://www.llama.com/models/', None
        if '版本未识别' in label or 'unidentified' in folded:
            return 'proprietary', 'llama 4', 'https://www.llama.com/models/', None
    if label.casefold().startswith('proprietary'):
        return label, label, '', '该 proprietary 资产未匹配到本地许可证原文'
    return label, label, '', None


def _integration(value):
    value = (value or '').strip()
    if value.startswith('远程服务调用'):
        return '远程服务调用', '\\'
    match = re.fullmatch(r'代码层面集成（修改：(是|否|无法确定)）', value)
    if match:
        return '代码层面集成', match.group(1)
    return '', '',


def _included_sources():
    data = json.loads(ASC_CORPUS_PATH.read_text(encoding='utf-8'))
    return {source['filename'] for source in data['sources'] if source.get('status') == 'INCLUDED'}


def adapt_aggregate_rows(rows, source_path):
    """Return normalized rows while marking rows lacking usable ASC originals."""
    included = _included_sources()
    adapted = []
    for index, row in enumerate(rows, 1):
        github_license = (row.get('GitHub许可证') or '').strip()
        asset_label = (row.get('资产许可证原文标题/标签') or '').strip()
        integration, modified = _integration(row.get('调用方式（代码修改）'))
        skip_reason = None
        try:
            weight = int(row.get('数量', ''))
            if weight < 1:
                raise ValueError
        except (TypeError, ValueError):
            weight = 0
            skip_reason = '数量列不是正整数'
        if not github_license or not asset_label:
            skip_reason = skip_reason or '许可证单元格为空'
        if not integration:
            skip_reason = skip_reason or '调用方式/修改状态无法识别'

        asset_license, asset_name, asset_url, identity_skip = _asset_identity(asset_label)
        skip_reason = skip_reason or identity_skip
        normalized = {
            'github_repo': f'license-combination-row-{index:04d}',
            'github_url': '',
            'github_license': github_license,
            'artifact_name': asset_name,
            'artifact_url': asset_url,
            'artifact_license': asset_license,
            'integration': integration,
            'modified': modified,
            '_aggregate_weight': weight,
            '_aggregate_group_row': index,
            '_aggregate_source_path': str(source_path),
            '_aggregate_original_asset_label': asset_label,
            '_aggregate_original_call_label': row.get('调用方式（代码修改）', ''),
            '_aggregate_prompt_row': {
                'GitHub许可证': github_license,
                '资产许可证原文标题/标签': asset_label,
                '调用方式（代码修改）': row.get('调用方式（代码修改）', ''),
                '数量': str(weight),
            },
        }

        # A judgment requires a mapped ASC source on both sides, and every
        # branch of a compound OR label must have a source in the corpus.
        if not skip_reason:
            resolved = resolve_row_sources(normalized)
            for side, license_value in (('upstream', asset_license), ('downstream', github_license)):
                expected = len(re.split(r'\s+OR\s+', license_value, flags=re.IGNORECASE))
                side_sources = [source for source in resolved if source.get('side') == side]
                if len(side_sources) != expected or any(source.get('file') not in included for source in side_sources):
                    skip_reason = f'{side}许可证没有完整、已纳入的结构化 ASC 原文'
                    break
        normalized['_aggregate_skip_reason'] = skip_reason
        adapted.append(normalized)
    return adapted
