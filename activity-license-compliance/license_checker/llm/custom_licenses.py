"""Resolve custom licenses by exact repository identity, never by generic LicenseRef alone."""
import json
from pathlib import Path
from urllib.parse import urlsplit
REGISTRY=Path(__file__).resolve().parents[2]/'data/custom_license_registry.json'

def repository_id(value):
    value=(value or '').strip()
    if '://' in value:
        parsed=urlsplit(value)
        if parsed.hostname not in {'github.com','www.github.com'}:return None
        value=parsed.path
    bits=value.strip('/').split('/')
    if len(bits)!=2 or not all(bits):return None
    return '/'.join(bits).removesuffix('.git').casefold()

def resolve_custom_source(row,side):
    url=row.get('github_url','') if side=='downstream' else row.get('artifact_url','')
    repo=repository_id(url)
    label=row.get('github_license','') if side=='downstream' else row.get('artifact_license','')
    if not repo or not REGISTRY.exists():return None
    data=json.loads(REGISTRY.read_text(encoding='utf-8'))
    matches=[r for r in data['records'] if r['repository']==repo and r['license_label'].casefold()==label.strip().casefold()]
    if len(matches)!=1:return None
    return matches[0]
