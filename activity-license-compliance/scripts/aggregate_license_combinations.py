"""Reproduce the 16927 license-combination table using the stated study conventions."""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = {
    'openai.com': 'OpenAI Services Agreement',
    'anthropic.com': 'Anthropic Commercial Terms of Service',
    'ai.google.dev': 'Gemini API Additional Terms of Service',
    'deepseek.com': 'DeepSeek Open Platform Terms of Service',
    'aliyun.com': '阿里云百炼服务特别说明',
    'bigmodel.cn': '智谱开放平台用户协议',
    'mistral.ai': 'Mistral AI Commercial Terms of Service',
    'moonshot.cn': 'Kimi 模型服务协议（用户协议）',
    'cohere.com': 'Cohere Commercial SaaS Agreement',
    'cloud.baidu.com': '百度智能云用户服务协议',
}
HEADERS = ['GitHub许可证', '资产许可证原文标题/标签', '调用方式（代码修改）', '数量']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'aggregate_all_16927/result.csv')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or args.input.with_name('许可证组合统计.csv')
    with args.input.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    # Prefer an existing mixed/uppercase SPDX spelling over its lowercase alias.
    labels = {row[key].strip() for row in rows for key in ('GitHub许可证', '资产许可证')}
    canonical = {}
    for label in sorted(labels, key=lambda s: (s == s.lower(), s)):
        canonical.setdefault(label.casefold(), label)
    canonical.update({'gemma': 'Apache-2.0', 'odc-by': 'ODC-BY-1.0'})
    groups, excluded, changes, modes, provider_counts = (Counter() for _ in range(5))
    audit = []
    defaults = 0
    for row_number, row in enumerate(rows, 2):
        pair = [row[k].strip() for k in ('GitHub许可证', '资产许可证')]
        reasons = []
        if any(re.search(r'(?<![a-z])gpl-2\.0(?:\b|$)', value, re.I) for value in pair):
            reasons.append('GPL-2.0系列')
        if any('lgpl' in value.casefold() for value in pair):
            reasons.append('LGPL系列')
        if reasons:
            excluded['、'.join(reasons)] += 1
            audit.append({'CSV行号': row_number, '处理': '排除', '说明': '、'.join(reasons)})
            continue
        github, asset = [canonical[value.casefold()] for value in pair]
        for old, new in zip(pair, (github, asset)):
            if old != new:
                changes[f'{old} → {new}'] += 1
        if asset.casefold() == 'proprietary':
            host = (urlparse(row['资产URL']).hostname or '').lower()
            if host == 'llama.com' or host.endswith('.llama.com'):
                name = row['AI模型/数据集/工具名'].casefold()
                match = re.search(r'llama[-_\s]*(3[._]?[123]|[234])(?=$|[^0-9])', name)
                version = match.group(1).replace('_', '.') if match else '4'
                if version in ('31', '32', '33'):
                    version = version[0] + '.' + version[1]
                if not match:
                    defaults += 1
                    audit.append({'CSV行号': row_number, '处理': 'Llama默认4', '说明': row['AI模型/数据集/工具名']})
                asset = f'LLAMA {version} COMMUNITY LICENSE AGREEMENT'
            else:
                matches = [title for domain, title in PROVIDERS.items() if host == domain or host.endswith('.' + domain)]
                if len(matches) != 1:
                    raise ValueError(f'Unmapped proprietary URL at CSV line {row_number}: {host}')
                asset = matches[0]
            provider_counts[asset] += 1
        call = row['调用方式'].strip()
        if call == '远程服务调用':
            mode = '远程服务调用（修改不适用）'
        elif call == '代码层面集成' and row['代码集成是否修改'].strip() in ('是', '否', '无法确定'):
            mode = f'代码层面集成（修改：{row["代码集成是否修改"].strip()}）'
        else:
            raise ValueError(f'Unknown integration mode at CSV line {row_number}')
        groups[(github, asset, mode)] += 1
        modes[mode] += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        for key, count in sorted(groups.items(), key=lambda item: (-item[1], item[0])):
            writer.writerow([*key, count])
    retained = sum(groups.values())
    assert retained + sum(excluded.values()) == len(rows)
    summary = {'input': str(args.input), 'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
               'input_rows': len(rows), 'retained_rows': retained, 'groups': len(groups),
               'excluded': dict(excluded), 'normalizations': dict(changes),
               'integration_counts': dict(modes), 'proprietary_titles': dict(provider_counts),
               'llama_default_4_rows': defaults,
               'conventions': ['按用户实验口径排除GPL-2.0系列和LGPL系列，并非法律效力判断',
                   'Gemma主许可按Apache-2.0；ODC-BY按1.0；BUSL-1.1保留按模板分析',
                   '忽略仓库名称，合并许可证大小写别名；直接标注的Llama许可证标签沿用原标签',
                   'proprietary按资产URL匹配原文标题；Llama按资产名识别版本，无法识别按4',
                   '保留unknown、other、Unlicense和自定义标签；此表是统计输入，不是合规结论',
                   'Cohere选API适用Commercial SaaS Agreement；百度原文还含线上订购协议']}
    output.with_suffix('.summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with output.with_name(output.stem + '_处理记录.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['CSV行号', '处理', '说明'])
        writer.writeheader()
        writer.writerows(audit)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
