"""Versioned AGPL full-text extraction. Never merge before source review.

python3 scripts/reextract_agpl.py --execute
python3 scripts/reextract_agpl.py --merge  # only after reviewing candidate
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.extend_asc_corpus import PROMPT, ACTS, validate, save, digest
from license_checker.asc import OBJECTS, KINDS, validate_triple
from license_checker.llm.client import ResponsesClient, extract_text
from license_checker.llm.config import load_config

RUN = ROOT / 'runs/agpl-fulltext-repair-2026-11-13'
CORPUS = ROOT / 'data/structured_asc_v1.json'
NAMES = ['LICENSE-AGPL-3.0-only.txt', 'LICENSE-AGPL-3.0-or-later.txt']
CHECKLIST = ROOT / 'output/expert-review-asc/coverage-review/coverage_review.json'
RANGES = [(58,78),(80,115),(117,156),(158,179)]
GUIDANCE = '''
AGPL source-first extraction repair. Previous sparse extraction is NOT supplied as a target.
Read every operative paragraph of sections 2 through 14. Definitions in sections 0/1
are binding context, not grants by themselves. Exclude preamble, generic warranty/
liability clauses and how-to-apply instructions with an explicit coverage note.
Preserve permissions as well as restrictions. Do not confuse conveyance with remote
interaction, aggregate with a combined derivative work, sale of copies with charging
for license rights, or a licensee's choice with an affirmative duty.
Model notice/copy/date/whole-work/source duties as conditions on Distribute, NOT as
OBLIGATORY Distribute. Only use OBLIGATORY when A is the actual required action,
with explicit when and requires. Section 13 requires ProvideSource when a modified
version supports remote interaction and users interact with it remotely; it does
not require operating a network service. Preserve no-charge access, all interacting
users, corresponding-source scope, and combined GPLv3 source inclusion.
Encode material triggers, AND/OR alternatives, numerical deadlines, exceptions and
separately obtained permissions in C, not solely in notes. Explain every predicate.
For complex section 6 alternatives, separate paths rather than require all paths.
Sections 4/5/6 are cumulative where expressly referenced; state dependencies.
Represent source-output scope and extra permissions as conditional bounds, not
blanket grants or prohibitions. A prohibition on extra restrictions applies to
conveyance with those restrictions, not all conveyance or all charging.
Represent restoration provisions under their precise holder/notice/cure conditions;
do not invent a new permission solely from termination language. Use UNSPECIFIED or
document a representation limit when canonical A/S cannot faithfully express a clause.
For each supplied review_unit, add coverage_audit entry {unit:integer,
status:"MODELED"|"PARTIAL"|"OUT_OF_SCOPE", clause_labels:[exact clause_label strings],
explanation:"what is covered and any missing elements"}. Do not claim completeness
merely by citing a paragraph. This is extraction self-assessment, not expert approval.
Do not emit duplicate Cartesian products across unrelated objects/actions.
'''

def check(data, lines, lo, hi, units):
    validate(data, lines, lo, hi)
    labels = {c['clause_label'] for c in data['clauses']}
    audit = data.get('coverage_audit', [])
    if sorted(x['unit'] for x in audit) != sorted(x['unit'] for x in units):
        raise ValueError('Coverage ledger must account for every review unit once')
    for a in audit:
        if a['status'] not in {'MODELED','PARTIAL','OUT_OF_SCOPE'} or not a.get('explanation'):
            raise ValueError('Invalid coverage assessment')
        if set(a['clause_labels']) - labels:
            raise ValueError('Unknown coverage clause label')
        if a['status']=='MODELED' and not a['clause_labels']:
            raise ValueError('Modeled unit must reference clauses')
    for c in data['clauses']:
        constraint=c['C']
        if constraint['kind']=='OBLIGATORY':
            if not {'when','requires'} <= set(constraint):
                raise ValueError('Obligation missing trigger/content')
            if set(c['activities']) - {'ProvideSource'}:
                raise ValueError('AGPL obligation action must be actual ProvideSource; encode ancillary duties as permission conditions')
        if constraint['kind']=='PROHIBITED' and constraint.get('requires',True) is not True:
            raise ValueError('PROHIBITED ignores requires; use conditional prohibition')
    return data

def extract(bounds, config, lines, checklist):
    lo, hi=bounds; key=f'L{lo}-L{hi}'
    units=[{'unit':x['unit'],'topic':x['topic'],'lines':x['lines']} for x in checklist
           if lo <= int(x['lines'].split('-')[0][1:]) <= hi]
    body={'model':config.model,'instructions':PROMPT+GUIDANCE,
          'input':json.dumps({'filename':NAMES[0], 'allowed_activities':ACTS,
              'allowed_objects':OBJECTS, 'allowed_modalities':sorted(KINDS),
              'definitions_context_not_citable':'\n'.join(lines[27:57]),
              'full_license_context_not_citable':'\n'.join(lines),
              'review_units':units,
              'chunk':'\n'.join(f'{i}: {lines[i-1]}' for i in range(lo,hi+1))},ensure_ascii=False),
          'max_output_tokens':16000,'reasoning':{'effort':'medium'}}
    request_hash=digest(json.dumps(body,sort_keys=True).encode())
    save(RUN/'requests'/f'{key}.json',{'request_sha256':request_hash,'body':body})
    cached=RUN/'validated'/f'{key}.json'
    if cached.exists():
        old=json.loads(cached.read_text())
        if old['request_sha256']==request_hash:return check(old['data'],lines,lo,hi,units)
    for attempt in range(1,4):
        save(RUN/'requests'/f'{key}-attempt{attempt}.json',body)
        response=ResponsesClient(config).create(body)
        save(RUN/'responses'/f'{key}-attempt{attempt}.json',response)
        try:
            text=extract_text(response).strip()
            if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
            data=check(json.loads(text),lines,lo,hi,units)
            save(cached,{'request_sha256':request_hash,'data':data})
            return data
        except (ValueError, KeyError, TypeError) as e:
            save(RUN/'errors'/f'{key}-attempt{attempt}.json',{'error':str(e)})
            if attempt==3:raise
            body['input'] += '\nPrevious response:\n'+extract_text(response)+'\nValidation feedback: '+str(e)+'\nReturn a complete corrected object.'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--merge',action='store_true');args=ap.parse_args()
    if args.execute and args.merge:raise ValueError('Extract and review before merging')
    corpus=json.loads(CORPUS.read_text())
    files=[ROOT/'许可证原文'/n for n in NAMES]
    if files[0].read_bytes()!=files[1].read_bytes():raise ValueError('AGPL alias texts differ; extract separately')
    lines=files[0].read_text().splitlines()
    if args.merge:
        reviewed_path=RUN/'reviewed_candidate.json'
        if not reviewed_path.exists():raise ValueError('Reviewed candidate required before merge')
        candidate=json.loads(reviewed_path.read_text())
        before=json.loads((RUN/'before_corpus.json').read_text())
        if corpus!=before:raise ValueError('Corpus changed since extraction; reconcile before merging')
        for source in candidate['sources']:
            if digest((ROOT/'许可证原文'/source['filename']).read_bytes())!=source['sha256']:
                raise ValueError('Original changed after extraction')
        assert set(r['license_id'] for r in candidate['rules'])==set(NAMES)
        for r in candidate['rules']:
            validate_triple(r['ASC'])
            assert r['source_excerpt'] in files[0].read_text()
        retained=[r for r in corpus['rules'] if r['license_id'] not in NAMES]
        corpus['rules']=retained+candidate['rules']
        assert len({r['rule_id'] for r in candidate['rules']})==len(candidate['rules'])
        corpus.setdefault('extensions',[]).append({'run':str(RUN.relative_to(ROOT)),
            'method':'AGPL full-text LLM re-extraction with recorded assistant review; no independent expert validation',
            'replaced_sources':NAMES,'replaced_rules':12,'new_rules':len(candidate['rules'])})
        save(CORPUS,corpus)
        summary_path=ROOT/'data/structured_asc_v1_summary.json'
        summary=json.loads(summary_path.read_text())
        save(RUN/'before_corpus_summary.json',summary)
        from collections import Counter
        summary.update(rule_count=len(corpus['rules']),rules_per_source=dict(Counter(r['license_id'] for r in corpus['rules'])))
        summary['latest_revision']=str(RUN.relative_to(ROOT))
        save(summary_path,summary)
        save(RUN/'merge_manifest.json',{'before_rules':len(before['rules']),'after_rules':len(corpus['rules']),
            'unchanged_other_rules':retained==[r for r in before['rules'] if r['license_id'] not in NAMES],
            'new_corpus_sha256':digest(CORPUS.read_bytes()),'conflict_results_rerun':False})
        print('Merged reviewed AGPL rules; historical runs unchanged.');return
    if not args.execute:
        print(json.dumps({'sources':NAMES,'chunks':RANGES,'output':str(RUN)},ensure_ascii=False));return
    if not (RUN/'before_corpus.json').exists():save(RUN/'before_corpus.json',corpus)
    checklist=[x for x in json.loads(CHECKLIST.read_text())['items'] if x['license']=='AGPL-3.0-only']
    config=replace(load_config(ROOT/'configs/experiment.toml'),max_retries=0,timeout_seconds=180)
    outcomes={};errors=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(extract,b,config,lines,checklist):b for b in RANGES}
        for fut in as_completed(jobs):
            b=jobs[fut]
            try:outcomes[b]=fut.result();print(json.dumps({'chunk':b,'clauses':len(outcomes[b]['clauses'])}),flush=True)
            except Exception as e:errors.append({'chunk':b,'error':str(e)});print(json.dumps(errors[-1]),flush=True)
    save(RUN/'progress.json',{'completed':[list(b) for b in outcomes],'errors':errors})
    if errors:return 1
    rules=[]
    for name in NAMES:
        sid=next(s['source_id'] for s in corpus['sources'] if s['filename']==name)
        for bounds in RANGES:
            for c in outcomes[bounds]['clauses']:
                lo,hi=c['start_line'],c['end_line']
                for a in dict.fromkeys(c['activities']):
                    for o in dict.fromkeys(c['objects']):
                        asc={'A':a,'S':{'artifact':'$LICENSED_MATERIAL','kind':o},'C':c['C']}
                        sig=json.dumps([name,lo,hi,asc,c['actor_role'],c['scope_note']],sort_keys=True)
                        rules.append({'rule_id':f'{sid}-agpl-v2-'+digest(sig.encode())[:16],
                            'license_source_id':sid,'license_id':name,'clause_id':f'L{lo}-L{hi}',
                            'clause_label':c['clause_label'],'ASC':asc,'actor_role':c['actor_role'],
                            'scope_note':c['scope_note'],'condition_explanation':c['condition_explanation'],
                            'source_excerpt':'\n'.join(lines[lo-1:hi]),
                            'extraction_status':'LLM_EXTRACTED_SOURCE_VALIDATED',
                            'extraction_method':'gpt-6-luna; section-complete AGPL repair; raw responses retained'})
    # Collapse exact generated rules only; no rule-ID overwrite.
    unique={json.dumps(r,sort_keys=True):r for r in rules}
    save(RUN/'candidate.json',{'sources':[s for s in corpus['sources'] if s['filename'] in NAMES],
         'rules':list(unique.values()),'model_coverage_audit':{str(b):outcomes[b]['coverage_audit'] for b in RANGES},
         'coverage_notes':{str(b):outcomes[b]['coverage_notes'] for b in RANGES}})
    print(json.dumps({'candidate_rules':len(unique),'merged':False}))

if __name__=='__main__':sys.exit(main())
