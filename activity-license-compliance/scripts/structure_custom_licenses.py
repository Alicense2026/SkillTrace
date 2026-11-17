"""Extract repository-scoped custom license ASC; preserve originals, requests and source spans."""
import argparse,json,sys
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import extend_asc_corpus as ext
from license_checker.llm.config import load_config
RUN=ROOT/'runs/custom-asc-2026-11-12'
INDEX=ROOT/'data/custom_license_registry.json'
INPUT=ROOT/'许可证原文/_licenseref_full/licenseref_full.json'

def prepare():
    records=json.loads(INPUT.read_text(encoding='utf-8-sig'))
    base=json.loads(ext.CORPUS.read_text());known={s['sha256']:s for s in base['sources']};registry=[];sources={}
    for r in records:
        text=r['完整原文'];sha=ext.digest(text.encode());repo=r['仓库'].strip().strip('/').casefold()
        if text and not sha.startswith(r['sha256前16位']):raise ValueError('Original hash mismatch: '+repo)
        existing=known.get(sha)
        filename=existing['filename'] if existing else '_licenseref_full/texts/'+sha+'.txt'
        item={'repository':repo,'license_label':r['许可证'],'sha256':sha,'filename':filename,
              'evidence_file':r['证据文件'],'acquisition':r['获取方式'],'status':'AVAILABLE' if text.strip() else 'EMPTY_ORIGINAL'}
        registry.append(item)
        if not text.strip():continue
        path=ROOT/'许可证原文'/filename
        if not existing:
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists():assert path.read_bytes()==text.encode()
            else:path.write_bytes(text.encode())
        if not existing:sources.setdefault(filename,{'sha256':sha,'lines':text.splitlines(),'bytes':len(text.encode())})
    assert len({r['repository'] for r in registry})==len(registry)
    ext.save(INDEX,{'schema_version':'custom-license-registry-1','mapping_file':str(INPUT),'mapping_sha256':ext.digest(INPUT.read_bytes()),'records':registry})
    return base,registry,sources

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--workers',type=int,default=4);args=ap.parse_args()
    base,registry,sources=prepare()
    if not sources:
        print('No new custom originals; existing ASC and coverage notes preserved.',flush=True);return
    ext.RUN=RUN
    ext.PROMPT+='\nCustom license rule: extract only the supplied original. A bare license name or external-terms URL does not supply its full conditions; record this in coverage_notes, never reconstruct unseen clauses. No-grant language is UNSPECIFIED for absent grants, not a blanket prohibition on unrelated artifacts. Preserve the repository material versus third-party dependencies, licensor versus downstream recipient, and private versus public uses. An empty clauses list is allowed when the supplied original contains no operative clause.\n'
    jobs=[]
    for name,s in sources.items():
        for lo,hi in ext.chunks(s['lines']):jobs.append((s['sha256'][:12]+f'-L{lo}-L{hi}',name,s['lines'],lo,hi))
    if not (RUN/'before_extension.json').exists():ext.save(RUN/'before_extension.json',base)
    manifest={'mapping_sha256':ext.digest(INPUT.read_bytes()),'sources':list(sources),'jobs':[j[0] for j in jobs],'model':'gpt-6-luna'}
    ext.save(RUN/'manifest.json',manifest)
    print(json.dumps({'mapping_records':len(registry),'new_unique_sources':len(sources),'chunks':len(jobs),'empty_originals':sum(r['status']=='EMPTY_ORIGINAL' for r in registry),'execute':args.execute}),flush=True)
    config=replace(load_config(ROOT/'configs/experiment.toml'),max_retries=1)
    outcomes={};errors=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(ext.extract,j,config,args.execute):j for j in jobs}
        for f in as_completed(futures):
            j=futures[f]
            try:k,data=f.result();outcomes[k]=data
            except Exception as exc:errors.append({'chunk':j[0],'source':j[1],'error':str(exc)})
            ext.save(RUN/'progress.json',{'completed':len(outcomes),'total':len(jobs),'errors':errors})
            print(json.dumps({'processed':len(outcomes)+len(errors),'total':len(jobs),'errors':len(errors),'chunk':j[0]},ensure_ascii=False),flush=True)
    if not args.execute:return
    additions=[];new_sources=[];notes=json.loads((ROOT/'data/structured_asc_custom_v1.json').read_text()).get('coverage_notes',{}) if (ROOT/'data/structured_asc_custom_v1.json').exists() else {};counts={}
    for name,s in sources.items():
        js=[j for j in jobs if j[1]==name]
        if any(not outcomes.get(j[0]) for j in js):continue
        sid='custom-src-'+s['sha256'][:16];seen=set();notes[name]=[]
        for j in js:
            data=outcomes[j[0]];notes[name]+=data['coverage_notes']
            for cl in data['clauses']:
                lo,hi=cl['start_line'],cl['end_line']
                for act in dict.fromkeys(cl['activities']):
                    for obj in dict.fromkeys(cl['objects']):
                        triple={'A':act,'S':{'artifact':'$LICENSED_MATERIAL','kind':obj},'C':cl['C']}
                        signature=json.dumps([lo,hi,triple,cl['actor_role'],cl['scope_note']],sort_keys=True,ensure_ascii=False)
                        if signature in seen:continue
                        seen.add(signature)
                        additions.append({'rule_id':sid+f'-L{lo}-L{hi}-'+ext.digest(signature.encode())[:12],
                            'license_source_id':sid,'license_id':name,'clause_id':f'L{lo}-L{hi}','clause_label':cl['clause_label'],
                            'ASC':triple,'actor_role':cl['actor_role'],'scope_note':cl['scope_note'],'condition_explanation':cl['condition_explanation'],
                            'source_excerpt':'\n'.join(s['lines'][lo-1:hi]),'extraction_status':'LLM_EXTRACTED_SOURCE_VALIDATED',
                            'extraction_method':'gpt-6-luna; full-text source-line extraction; repository mapping preserved'})
        counts[name]=len(seen)
        new_sources.append({'source_id':sid,'filename':name,'sha256':s['sha256'],'bytes':s['bytes'],
                            'first_nonempty_line':next((line for line in s['lines'] if line.strip()),'')[:240],
                            'family':'repository_custom','status':'INCLUDED' if seen else 'INCLUDED_NO_RULE_MATCHED'})
    current=json.loads(ext.CORPUS.read_text());filenames={s['filename'] for s in current['sources']}
    fresh=[s for s in new_sources if s['filename'] not in filenames];fresh_ids={s['source_id'] for s in fresh};newrules=[r for r in additions if r['license_source_id'] in fresh_ids]
    current['sources']+=fresh;current['rules']+=newrules
    if fresh:current.setdefault('extensions',[]).append({'run':str(RUN.relative_to(ROOT)),'sources':len(fresh),'rules':len(newrules),'method':'Repository-scoped custom ASC from supplied exact fulltext; no human legal certification'})
    ext.save(ext.CORPUS,current)
    custom_names={r['filename'] for r in registry if r['status']=='AVAILABLE'}
    custom_sources=[s for s in current['sources'] if s['filename'] in custom_names];custom_ids={s['source_id'] for s in custom_sources}
    custom_rules=[r for r in current['rules'] if r['license_source_id'] in custom_ids]
    ext.save(ROOT/'data/structured_asc_custom_v1.json',{'schema_version':'asc-corpus-1.0','sources':custom_sources,'rules':custom_rules,'registry':registry,'coverage_notes':notes})
    for s in custom_sources:ext.save(RUN/'by_license'/(s['sha256']+'.json'),{'source':s,'repositories':[r['repository'] for r in registry if r['filename']==s['filename']],'rules':[r for r in custom_rules if r['license_source_id']==s['source_id']]})
    summary={'mapping_records':len(registry),'structured_unique_sources':len(custom_sources),'new_unique_sources':len(fresh),'custom_rules':len(custom_rules),'new_rules':len(newrules),'empty_originals':sum(r['status']=='EMPTY_ORIGINAL' for r in registry),'zero_rule_sources':[s['filename'] for s in custom_sources if s['status']!='INCLUDED'],'errors':errors}
    ext.save(RUN/'summary.json',summary)
    ext.save(ROOT/'data/structured_asc_v1_summary.json',{'source_count':len(current['sources']),'rule_count':len(current['rules']),'included_sources':sum(s['status']=='INCLUDED' for s in current['sources']),'rules_per_source':dict(Counter(r['license_id'] for r in current['rules']))})
    print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
