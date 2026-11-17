"""统一入口：audit（离线）、experiment（默认 dry-run）、cases（核验案例）。"""
import argparse
import json
from .audit_cli import main as audit_main
from .llm.experiment import run_experiment
from .llm.prompting import load_cases


def main(argv=None):
    parser=argparse.ArgumentParser(description='Activity license compliance audit and LLM experiments')
    sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('audit');a.add_argument('--input',required=True);a.add_argument('--output-dir',required=True);a.add_argument('--human-input')
    a.add_argument('--license-cache',default='cache/license_license.sqlite3');a.add_argument('--no-license-cache',action='store_true')
    e=sub.add_parser('experiment');e.add_argument('--input',required=True);e.add_argument('--output-dir',required=True)
    e.add_argument('--config',default='configs/experiment.toml');e.add_argument('--limit',type=int,default=1);e.add_argument('--offset',type=int,default=0)
    e.add_argument('--execute',action='store_true',help='Actually send requests to the configured relay; otherwise dry-run')
    sub.add_parser('cases')
    args=parser.parse_args(argv)
    try:
        if args.command=='audit':
            opts=['--input',args.input,'--output-dir',args.output_dir]
            if args.human_input:opts+=['--human-input',args.human_input]
            if args.no_license_cache:opts+=['--no-license-cache']
            else:opts+=['--license-cache',args.license_cache]
            return audit_main(opts)
        if args.command=='cases':
            d=load_cases();print(json.dumps({'version':d['version'],'cases':len(d['cases']),'asc_terms':sum(len(c['asc_terms']) for c in d['cases'])},ensure_ascii=False));return
        result=run_experiment(args.input,args.output_dir,args.config,args.limit,args.offset,args.execute)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result['errors']:raise SystemExit(1)
    except (ValueError,OSError) as exc:
        parser.error(str(exc))
