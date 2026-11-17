"""稳定案例 ID；原始行号及内容摘要保持与 v0.3/v0.4 一致。"""
import hashlib
import json

def case_id(row, i):
    digest = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    return f'chain-{i+1:04d}-{digest}'
