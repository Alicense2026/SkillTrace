"""离线审计命令行参数和文件 I/O。"""
import argparse
import json
import hashlib
from pathlib import Path
from .input_files import load_input
from .pipeline import run
from .reporting import write_outputs
from .license_pair_cache import LicensePairCache


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True, type=Path); p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--human-input', type=Path)
    p.add_argument('--license-cache', type=Path, default=Path('cache/license_license.sqlite3'))
    p.add_argument('--no-license-cache', action='store_true')
    args=p.parse_args(argv)
    payload,source=load_input(args.input)
    cache = None if args.no_license_cache else LicensePairCache(args.license_cache)
    result=run(payload,
               json.loads(args.human_input.read_text(encoding='utf-8')) if args.human_input else None, str(source), cache)
    result['input_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    write_outputs(result,args.output_dir); print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
