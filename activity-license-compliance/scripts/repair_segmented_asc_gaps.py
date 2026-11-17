"""Additive, source-grounded gap repair; baseline artifacts are immutable.
Run --execute for API extraction, otherwise prepare/compile existing patches.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time
import fcntl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import extract_segmented_asc as base

RUN = ROOT/'runs/skill-asc-gap-repair-2026-11-14'
STATUSES = {'MODELED','CONTEXT','NONOPERATIVE','EXTERNAL_REFERENCE_EXCLUDED','OUTSIDE_ACTIVITY_SCOPE','UNRESOLVED'}
PROMPT = base.PROMPT.replace('MODELED|CONTEXT|NONOPERATIVE|UNRESOLVED', 'MODELED|CONTEXT|NONOPERATIVE|EXTERNAL_REFERENCE_EXCLUDED|OUTSIDE_ACTIVITY_SCOPE|UNRESOLVED').replace('UNRESOLVED means operative content remains missing or cannot be faithfully represented.', 'UNRESOLVED means a remaining in-scope extraction gap; use the explicit exclusion statuses for external files and unrepresentable activities.').replace('Source line ranges must be inside the target chunk, exact inclusive lines, max 12000 characters. Context is not citable.', 'Source line ranges may be anywhere in the supplied full original; exact inclusive lines, max 12000 characters.') + '''
REPAIR OVERRIDES: You are reviewing only target gap paragraphs, using the FULL numbered original as citable context. Earlier rules are immutable anchors, not to be regenerated. previous_gap_reasons are UNRELIABLE generated notes, not source evidence. They may falsely call headings or definitions operative, or describe the wrong paragraph. Read the exact original text of each target unit first; mark headings/definitions CONTEXT when appropriate. Return additions only in clauses, plus paragraph_audit for exactly the target units, coverage_notes, and anchor_review. Reuse existing anchor clause_labels when already sufficient. Add clauses with labels starting gap/. Every target unit must be examined in its full section context, including lists/conditions on either side of original chunk boundaries. You may cite any lines in the full original, but each added clause must overlap a target paragraph. When other sections provide conditions, record exact supporting_source_ranges [[start,end],...] on the clause. Preserve exceptions and OR alternatives. Do not re-extract unrelated parts of the original. Existing local incorporated license text is provided as context; cite its filename and section in condition_explanation, never its line numbers as main-source lines.
Existing activities must be used, NEVER extended. Express payment, deletion on termination, notices, security, and confidentiality as precise ancillary obligation_items on an appropriate existing action, only where legally faithful. Do not force unrelated dispute-resolution or provider powers into a fictitious Use permission. Where a genuinely operative rule cannot fit any existing action, mark OUTSIDE_ACTIVITY_SCOPE with the exact unmatched action and reason. Missing external referenced documents may be excluded by user policy: EXTERNAL_REFERENCE_EXCLUDED; do not infer their contents, permission, compliance or fulfillment. Full original sections present in supplied text are NOT missing external documents. Mixed paragraphs require extraction of every locally stated, expressible rule, even when external referenced content remains excluded. Exclusion statuses may reference clauses for these local portions. NONOPERATIVE is for headings/unrelated boilerplate, not a way to hide a missing rule. UNRESOLVED only for remaining genuine in-scope gaps.
anchor_review contains exactly one {clause_label, verdict:"SUPPORTED"|"QUESTIONABLE",reason} for every recovered_anchor label. These anchors were recovered from a raw response whose paragraph audit was invalid. Check their actual meaning against the original, not just schema. QUESTIONABLE requires a precise source-grounded explanation; do not silently drop it. Baseline anchors are already preserved mechanically. No wholesale rewrite.
CRITICAL SCHEMA EXAMPLE for arbitration-only target P0016:
{"clauses":[],"coverage_notes":[],"paragraph_audit":[{"unit_id":"P0016","status":"OUTSIDE_ACTIVITY_SCOPE","clause_labels":[],"reason":"Arbitration and procedural duties do not fit the fixed activity vocabulary."}],"anchor_review":[]}
OUTSIDE_ACTIVITY_SCOPE and EXTERNAL_REFERENCE_EXCLUDED are paragraph_audit.status values ONLY. They are NEVER activities and NEVER C.kind. Never create a placeholder Use/UNSPECIFIED clause for excluded material. A missing external policy alone uses paragraph_audit.status=EXTERNAL_REFERENCE_EXCLUDED, not UNRESOLVED. Existing local duties in the same paragraph still need real clauses. Never invent Transfer, Delete, Pay or any new activity. Account transfer restrictions can be conditions on Use of the account; if no faithful mapping, classify the specific unmatched action as OUTSIDE_ACTIVITY_SCOPE. A right to terminate a contract is not permission to Use; do not label termination as conditionally permitted Use. Payment for using a service IS a condition on Use and must not be excluded merely because Pay is not an activity. Output JSON only.
'''

def load(path):
    return json.loads(path.read_text())

def semantic_key(c):
    return json.dumps({k:v for k,v in c.items() if k!='clause_label'},sort_keys=True,ensure_ascii=False)

def valid_clause(c, job):
    base.check({'clauses':[c],'coverage_notes':[], 'paragraph_audit':[]}, {**job,'units':[]})
    return c

def prepare():
    RUN.mkdir(parents=True,exist_ok=True)
    snapshot=RUN/'baseline'
    if not (snapshot/'manifest.json').exists():
        hashes={}
        for p in [base.RUN/'inventory.json',base.RUN/'structured_asc.json',base.RUN/'summary.json',*sorted((base.RUN/'validated').glob('*.json'))]:
            rel=p.relative_to(base.RUN)
            base.save(snapshot/rel,load(p));hashes[str(rel)]=base.digest(p.read_bytes())
        base.save(snapshot/'manifest.json',hashes)
    inv=load(snapshot/'inventory.json')
    for source in inv['sources']:
        if base.digest((base.LICENSE_DIR/source['files'][0]).read_bytes()) != source['sha256']:
            raise ValueError('Original source changed since baseline: '+source['files'][0])
    jobs=base.make_jobs(inv);targets=[]
    for job in jobs:
        path=snapshot/'validated'/f"{job['key']}.json"
        previous=load(path)['data'] if path.exists() else {'clauses':[],'paragraph_audit':[],'coverage_notes':[]}
        gaps=[a for a in previous['paragraph_audit'] if a['status']=='UNRESOLVED']
        if not path.exists():gaps=[{'unit_id':u['unit_id'],'reason':'No valid parent output','status':'UNRESOLVED'} for u in job['units']]
        if not gaps:continue
        anchors=json.loads(json.dumps(previous['clauses']));recovered=[];recovery_file=None
        # Recover the known lossy Mistral repair from its best structurally valid raw clauses.
        if job['key']=='4f00a0042342233a-001':
            best=[]
            for p in sorted((base.RUN/'responses').glob(job['key']+'-*-attempt*.json')):
                try:
                    raw=base.extract_text(load(p)).strip()
                    if raw.startswith('```'):raw=raw.split('\n',1)[1].rsplit('```',1)[0]
                    candidate=json.loads(raw);good=[]
                    for c in candidate['clauses']:
                        try:good.append(valid_clause(c,job))
                        except (ValueError,KeyError,TypeError):pass
                    if len(good)>len(best):best=good;recovery_file=str(p)
                except (ValueError,KeyError,TypeError):continue
            seen={semantic_key(c) for c in anchors}
            for c in best:
                if semantic_key(c) in seen:continue
                c=json.loads(json.dumps(c));c['clause_label']='recovered/'+c['clause_label']
                recovered.append(c);anchors.append(c);seen.add(semantic_key(c))
        ids={a['unit_id'] for a in gaps}
        # Audit all units touched by recovered clauses, including previously modeled ones.
        for c in recovered:
            ids.update(u['unit_id'] for u in job['units'] if c['start_line']<=u['end_line'] and c['end_line']>=u['start_line'])
        target={**job,'units':[u for u in job['units'] if u['unit_id'] in ids],'lo':1,'hi':len(job['lines']),
                'anchors':anchors,'recovered':recovered,'previous':previous,'gaps':gaps,'recovery_file':recovery_file}
        targets.append(target)
    targets.sort(key=lambda j: (j['key'] != '4f00a0042342233a-001', bool(j['previous']['clauses'])))
    (RUN/'prompt.txt').write_text(PROMPT)
    base.save(RUN/'plan.json',[{'key':j['key'],'files':j['source']['files'],'units':j['units'],'gaps':j['gaps'], 'baseline_rules':len(j['previous']['clauses']),'recovered_rules':len(j['recovered']),'recovery_file':j['recovery_file']} for j in targets])
    return inv,targets

def normalize_patch_labels(data, job):
    """Mechanical label normalization only; never edit ASC meaning or disposition."""
    data=json.loads(json.dumps(data))
    # In this schema requires on a ban denotes the forbidden-conduct condition.
    # Preserve that condition, actor, exception text, citation and raw response;
    # normalize the modality tag rather than repeatedly regenerating all clauses.
    for c in data['clauses']:
        constraint=c.get('C',{})
        if constraint.get('kind')=='PROHIBITED' and constraint.get('requires',True) is not True:
            before=json.loads(json.dumps(constraint));constraint['kind']='CONDITIONALLY_PROHIBITED'
            data.setdefault('representation_normalizations',[]).append({'clause_label':c['clause_label'], 'before':before,'after':json.loads(json.dumps(constraint)),
                'reason':'Canonical modality normalization: preserve the model-supplied forbidden-conduct condition in requires; conditional bans use CONDITIONALLY_PROHIBITED.'})
    retained=[];removed=set()
    for c in data['clauses']:
        refs=[a for a in data['paragraph_audit'] if c['clause_label'] in a.get('clause_labels',[])]
        inside=any(c['start_line']<=u['end_line'] and c['end_line']>=u['start_line'] for u in job['units'])
        excluded_placeholder=c.get('C',{}).get('kind')=='UNSPECIFIED' and all(a['status'] in {'OUTSIDE_ACTIVITY_SCOPE','EXTERNAL_REFERENCE_EXCLUDED','NONOPERATIVE','CONTEXT'} for a in refs)
        if not inside or excluded_placeholder:
            field='out_of_target_candidates' if not inside else 'excluded_placeholder_candidates'
            data.setdefault(field,[]).append(c);removed.add(c['clause_label'])
        else:retained.append(c)
    data['clauses']=retained
    for a in data['paragraph_audit']:a['clause_labels']=[label for label in a['clause_labels'] if label not in removed]
    renamed={c['clause_label']:'gap/'+c['clause_label'] for c in data['clauses'] if not c['clause_label'].startswith('gap/')}
    for c in data['clauses']:c['clause_label']=renamed.get(c['clause_label'],c['clause_label'])
    for a in data['paragraph_audit']:a['clause_labels']=[renamed.get(label,label) for label in a['clause_labels']]
    expected={c['clause_label'] for c in job['recovered']}
    reviews=data.get('anchor_review',[])
    extra=[a for a in reviews if a['clause_label'] not in expected]
    if extra:data['additional_anchor_review']=extra
    data['anchor_review']=[a for a in reviews if a['clause_label'] in expected]
    return data

def validate_patch(data, job):
    added=data['clauses'];anchors=job['anchors'];labels={c['clause_label']:c for c in anchors}
    for c in added:
        if c['C']['kind']=='UNSPECIFIED':raise ValueError('Do not create UNSPECIFIED placeholder rules. Put excluded content only in paragraph_audit.status; retain real local duties in actual clauses.')
        if not c['clause_label'].startswith('gap/'):raise ValueError('New clause labels must start gap/')
        if not any(c['start_line']<=u['end_line'] and c['end_line']>=u['start_line'] for u in job['units']):raise ValueError('Added clause does not overlap a target gap')
        for a,b in c.get('supporting_source_ranges',[]):
            if type(a)!=int or type(b)!=int or not 1<=a<=b<=len(job['lines']):raise ValueError('Invalid supporting source range')
    combined=anchors+added
    audits=data['paragraph_audit']
    for a in audits:
        if a['status'] not in STATUSES:raise ValueError('Invalid gap disposition')
        if a['status']=='UNRESOLVED' and any(t in a['reason'].lower() for t in ('outside_activity_scope','outside the supplied activity','not available activities','actions outside','not faithfully representable with the available')):
            raise ValueError('Use OUTSIDE_ACTIVITY_SCOPE in paragraph_audit.status for unrepresentable actions; extract any expressible local duties first.')
    # Structural checks are strict; accepted exclusions remain explicit in the saved ledger.
    converted=[{**a,'status':'UNRESOLVED' if a['status'] in {'EXTERNAL_REFERENCE_EXCLUDED','OUTSIDE_ACTIVITY_SCOPE'} else a['status']} for a in audits]
    base.check({'clauses':combined,'coverage_notes':data['coverage_notes'],'paragraph_audit':converted},job)
    expected={c['clause_label'] for c in job['recovered']}
    reviews=data.get('anchor_review',[])
    if sorted(x['clause_label'] for x in reviews)!=sorted(expected):raise ValueError('anchor_review must contain exactly these recovered labels, no baseline labels: '+str(sorted(expected)))
    if any(x['verdict'] not in {'SUPPORTED','QUESTIONABLE'} or not x.get('reason') for x in reviews):raise ValueError('Invalid recovered anchor review')
    return data

def repair(job, config):
    key=job['key']
    incorporated={}
    text='\n'.join(job['lines'])
    for name,trigger in [('LICENSE-GPL-3.0.txt','GNU General Public License'),('LICENSE-APACHE.txt','Apache')]:
        p=base.LICENSE_DIR/name
        if p.exists() and name not in job['source']['files'] and trigger in text:
            incorporated[name]=p.read_text(encoding='utf-8-sig')
    payload={'source_files':job['source']['files'],'allowed_activities':base.ACTS,'allowed_objects':base.OBJECTS,'allowed_modalities':sorted(base.KINDS),
             'full_original':'\n'.join(f'{i}: {line}' for i,line in enumerate(job['lines'],1)),
             'local_incorporated_context':incorporated,'target_units':[{**u,'exact_numbered_text':'\n'.join(f'{i}: {job["lines"][i-1]}' for i in range(u['start_line'],u['end_line']+1))} for u in job['units']],'previous_gap_reasons':job['gaps'],
             'immutable_anchors':job['anchors'],'recovered_anchor_labels':[c['clause_label'] for c in job['recovered']]}
    body={'model':config.model,'instructions':PROMPT,'input':json.dumps(payload,ensure_ascii=False),'max_output_tokens':16000,'reasoning':{'effort':'medium'}}
    sig=base.digest(json.dumps(body,sort_keys=True,ensure_ascii=False).encode())
    cached=RUN/'validated'/f'{key}.json'
    if cached.exists():
        old=load(cached)
        try:valid=validate_patch(old['data'],job)
        except (ValueError,KeyError,TypeError):valid=None
        if valid is not None:
            unresolved=[a for a in valid['paragraph_audit'] if a['status']=='UNRESOLVED']
            if not unresolved:return valid
            if key.count('-remaining')<2:
                ids={a['unit_id'] for a in unresolved}
                child={**job,'key':key+'-remaining','units':[u for u in job['units'] if u['unit_id'] in ids],
                       'anchors':job['anchors']+valid['clauses'],'gaps':unresolved}
                followup=repair(child,config)
                replacement={a['unit_id']:a for a in followup['paragraph_audit']}
                merged={**valid,'clauses':valid['clauses']+followup['clauses'],
                        'paragraph_audit':[replacement.get(a['unit_id'],a) for a in valid['paragraph_audit']],
                        'coverage_notes':valid['coverage_notes']+followup['coverage_notes']}
                validate_patch(merged,job)
                base.save(RUN/'superseded'/f'{key}-{time.time_ns()}.json',old)
                base.save(RUN/'requests'/f'{key}.json',{'request_sha256':sig,'body':body})
                base.save(cached,{'request_sha256':sig,'data':merged,'recovery':'additive follow-up on remaining units only','child':child['key']})
                return merged
            return valid
        base.save(RUN/'superseded'/f'{key}-{time.time_ns()}.json',old)
        cached.unlink()
    base.save(RUN/'requests'/f'{key}.json',{'request_sha256':sig,'body':body})
    # Reuse a previously returned complete patch if only mechanical label validation failed.
    # The origin is explicit: this does not claim it was generated with the new prompt.
    for response_path in sorted((RUN/'responses').glob(key+'-*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        suffix=response_path.stem[len(key)+1:]
        if not suffix.split('-')[0].isdigit():continue
        try:
            text=base.extract_text(load(response_path)).strip()
            if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
            candidate=validate_patch(normalize_patch_labels(json.loads(text),job),job)
            if any(a['status']=='UNRESOLVED' for a in candidate['paragraph_audit']):continue
            base.save(cached,{'request_sha256':sig,'data':candidate,'recovery':'mechanical label normalization of preserved raw response','origin_response':str(response_path)})
            return candidate
        except (ValueError,KeyError,TypeError,RuntimeError):continue
    expanded=[];parents={}
    for u in job['units']:
        size=sum(len(line)+1 for line in job['lines'][u['start_line']-1:u['end_line']])
        if size<=2600 or u['start_line']==u['end_line']:
            expanded.append(u);parents[u['unit_id']]=u['unit_id'];continue
        start=u['start_line'];used=0;part=1
        for line_no in range(start,u['end_line']+1):
            width=len(job['lines'][line_no-1])+1
            if used and used+width>2400:
                uid=f"{u['unit_id']}.part{part}"
                expanded.append({'unit_id':uid,'start_line':start,'end_line':line_no-1});parents[uid]=u['unit_id']
                start=line_no;used=0;part+=1
            used+=width
        uid=f"{u['unit_id']}.part{part}"
        expanded.append({'unit_id':uid,'start_line':start,'end_line':u['end_line']});parents[uid]=u['unit_id']
    if len(expanded)>len(job['units']):
        virtual={**job,'key':key+'-subunits','units':expanded,'gaps':[{'unit_id':u['unit_id'],'reason':'Complete missing constraints in this bounded subunit'} for u in expanded]}
        data=repair(virtual,config);merged=json.loads(json.dumps(data));audits=[]
        for u in job['units']:
            children=[a for a in data['paragraph_audit'] if parents[a['unit_id']]==u['unit_id']]
            statuses={a['status'] for a in children}
            status=next(x for x in ('UNRESOLVED','EXTERNAL_REFERENCE_EXCLUDED','OUTSIDE_ACTIVITY_SCOPE','MODELED','CONTEXT','NONOPERATIVE') if x in statuses)
            audits.append({'unit_id':u['unit_id'],'status':status,'clause_labels':list(dict.fromkeys(label for a in children for label in a['clause_labels'])),
                           'reason':'Subunit review: '+'; '.join(a['unit_id']+': '+a['reason'] for a in children),'subunit_audit':children})
        merged['paragraph_audit']=audits;validate_patch(merged,job)
        base.save(cached,{'request_sha256':sig,'data':merged,'recovery':'bounded subunits preserve original paragraph accounting'})
        return merged
    if len(job['units'])>12:
        def run_batch(offset):
            units=job['units'][offset:offset+12];ids={u['unit_id'] for u in units}
            child={**job,'key':key+f'-batch{offset//12+1}', 'units':units,'gaps':[a for a in job['gaps'] if a['unit_id'] in ids]}
            part=json.loads(json.dumps(repair(child,config)))
            renamed={c['clause_label']:f"gap/batch{offset//12+1}/"+c['clause_label'].removeprefix('gap/') for c in part['clauses']}
            for c in part['clauses']:c['clause_label']=renamed[c['clause_label']]
            for a in part['paragraph_audit']:a['clause_labels']=[renamed.get(label,label) for label in a['clause_labels']]
            return part
        with ThreadPoolExecutor(max_workers=3) as pool:
            parts=list(pool.map(run_batch,range(0,len(job['units']),12)))
        merged={field:[item for part in parts for item in part[field]] for field in ('clauses','paragraph_audit','coverage_notes')}
        merged['anchor_review']=parts[0]['anchor_review']
        for field in ('out_of_target_candidates','excluded_placeholder_candidates','additional_anchor_review','representation_normalizations'):
            merged[field]=[x for part in parts for x in part.get(field,[])]
        validate_patch(merged,job)
        base.save(cached,{'request_sha256':sig,'data':merged,'recovery':'bounded batches of at most 12 target units'})
        return merged
    original=body['input'];invocation=time.time_ns()
    for n in range(1,4):
        aid=f'{key}-{invocation}-{n}'
        base.save(RUN/'requests'/f'{aid}.json',body)
        raw=''
        try:
            response=base.ResponsesClient(config).create(body);base.save(RUN/'responses'/f'{aid}.json',response)
            raw=base.extract_text(response).strip()
            if raw.startswith('```'):raw=raw.split('\n',1)[1].rsplit('```',1)[0]
            data=validate_patch(normalize_patch_labels(json.loads(raw),job),job)
            base.save(cached,{'request_sha256':sig,'data':data,'attempt':n})
            return data
        except Exception as e:
            error=f'{type(e).__name__}: {e}';base.save(RUN/'errors'/f'{aid}.json',{'error':error})
            body['input']=original+('\nPrevious patch to repair (not evidence):\n'+raw if raw else '')+'\nPrevious patch failed validation: '+error+'\nAllowed activities: '+str(base.ACTS)+'\nAllowed C.kind: '+str(sorted(base.KINDS))+'\nAll exclusion markers belong ONLY in paragraph_audit.status; clauses=[] is valid for excluded-only paragraphs. Produce a complete additions-only patch; immutable anchors are retained by code.'
            if 'HTTP 401' in error or 'HTTP 403' in error:break
            time.sleep(min(n*2,6))
    raise RuntimeError(error)

def as_rule(c,job):
    sha=job['source']['sha256']
    return {'rule_id':'gap-'+base.digest(json.dumps([sha,c],sort_keys=True,ensure_ascii=False).encode())[:24],
            'license_id':job['source']['files'][0],'source_aliases':job['source']['files'],'source_sha256':sha,
            'ASC':{'A':c['activities'][0],'S':{'artifact':'$LICENSED_MATERIAL','kind':c['objects'][0]},'C':c['C']},
            'source_lines':[c['start_line'],c['end_line']], 'source_excerpt':'\n'.join(job['lines'][c['start_line']-1:c['end_line']]),
            **{k:c[k] for k in ['clause_label','actor_role','scope_note','condition_explanation','obligation_items']},
            'supporting_source_ranges':c.get('supporting_source_ranges',[]),'repair_chunk':job['key']}

def compile_result(jobs):
    corpus=load(RUN/'baseline/structured_asc.json');baseline_rules=list(corpus['rules']);ledger=[];pending=[];reviews=[];additions=[]
    for j in jobs:
        p=RUN/'validated'/f"{j['key']}.json"
        if not p.exists():pending.append(j['key']);continue
        cached=load(p)
        if cached['request_sha256'] != load(RUN/'requests'/f"{j['key']}.json")['request_sha256']:
            pending.append(j['key']);continue
        try:data=validate_patch(cached['data'],j)
        except (ValueError,KeyError,TypeError):pending.append(j['key']);continue
        questionable={a['clause_label'] for a in data['anchor_review'] if a['verdict']=='QUESTIONABLE'}
        for c in j['recovered']:
            # Keep disputed recoveries in the ledger, not silently discard or activate them.
            reviews.append({'chunk':j['key'],'clause':c,'review':next(a for a in data['anchor_review'] if a['clause_label']==c['clause_label'])})
            if c['clause_label'] not in questionable:additions.append(as_rule(c,j))
        additions.extend(as_rule(c,j) for c in data['clauses'])
        ledger.extend({'chunk':j['key'],'source_files':j['source']['files'],**a} for a in data['paragraph_audit'])
    # Exact duplicate rules are suppressed; semantically different conditions are not collapsed mechanically.
    seen=set();unique=[]
    for r in additions:
        k=json.dumps({x:y for x,y in r.items() if x not in {'rule_id','clause_label','repair_chunk'}},sort_keys=True,ensure_ascii=False)
        if k not in seen:seen.add(k);unique.append(r)
    corpus['rules']=baseline_rules+unique;corpus['schema']='segmented-asc-v3-additive-repair'
    corpus['repair_ledger']='gap_ledger.json';corpus['recovered_anchor_review']='recovered_anchor_review.json'
    corpus['method']='Immutable baseline plus source-grounded LLM additions; explicit exclusions are not demonstrated semantic coverage.'
    for s in corpus['sources']:
        sj=[j for j in jobs if j['source']['sha256']==s['sha256']]
        relevant=[a for a in ledger if a['chunk'] in {j['key'] for j in sj}]
        unresolved=[a for a in relevant if a['status']=='UNRESOLVED']
        s['baseline_status']=s['status']
        s['baseline_paragraph_status_counts']=s.pop('paragraph_status_counts',{})
        s['pending_repair_chunks']=[j['key'] for j in sj if j['key'] in pending]
        s['repair_dispositions']=dict(Counter(a['status'] for a in relevant))
        s['status']='REPAIR_PENDING' if s['pending_repair_chunks'] else 'EXTRACTED_WITH_OPEN_GAPS' if unresolved else 'EXTRACTED_WITH_ACCEPTED_EXCLUSIONS' if any(a['status'] in {'EXTERNAL_REFERENCE_EXCLUDED','OUTSIDE_ACTIVITY_SCOPE'} for a in relevant) else 'EXTRACTED_SELF_CHECKED'
        if sj and not s['pending_repair_chunks']:s['pending_chunks']=[]
        source_rules=[r for r in corpus['rules'] if r['source_sha256']==s['sha256']]
        base.save(RUN/'licenses'/f"{s['sha256'][:16]}.asc.json",{**s,'rules':source_rules,'gap_ledger':relevant})
    unchanged=all(base.digest((base.RUN/rel).read_bytes())==sha for rel,sha in load(RUN/'baseline/manifest.json').items())
    assert corpus['rules'][:len(baseline_rules)]==baseline_rules,'Baseline rules changed'
    usage=Counter()
    for response in (RUN/'responses').glob('*.json'):
        u=load(response).get('usage',{})
        for field in ('input_tokens','output_tokens','total_tokens'):usage[field]+=u.get(field,0) or 0
    summary={'api_usage_all_attempts':dict(usage),'baseline_rules':len(baseline_rules),'added_rules':len(unique),'asc_rules':len(corpus['rules']), 'obligation_items':sum(len(r['obligation_items']) for r in corpus['rules']),
             'target_chunks':len(jobs),'completed_chunks':len(jobs)-len(pending),'pending_chunks':pending,'gap_dispositions':dict(Counter(a['status'] for a in ledger)),
             'recovered_anchor_reviews':dict(Counter(a['review']['verdict'] for a in reviews)), 'baseline_rules_preserved':True,'baseline_artifacts_unchanged':unchanged,
             'source_status':dict(Counter(s['status'] for s in corpus['sources'])), 'updated_unix':time.time(),
             'note':'Exclusions accepted by user are not semantic recall. Model self-review is not expert validation.'}
    base.save(RUN/'structured_asc.json',corpus);base.save(RUN/'gap_ledger.json',ledger);base.save(RUN/'recovered_anchor_review.json',reviews);base.save(RUN/'summary.json',summary)
    report = f'''# ASC 定向补提取结果（自动更新）

本轮基于 6,113 条供应链关系涉及的 67 份去重原文，补处理 {len(jobs)} 个分段。

|指标|数量/状态|
|---|---:|
|已完成补提取分段|{summary['completed_chunks']}|
|尚未完成分段|{len(pending)}|
|原有 ASC 条款|{len(baseline_rules)}|
|新增及恢复条款|{len(unique)}|
|当前 ASC 条款总数|{len(corpus['rules'])}|
|当前义务项|{summary['obligation_items']}|
|原有条款完整保留|{summary['baseline_rules_preserved']}|
|基线实验文件未改动|{unchanged}|

## 缺口处置

'''
    report += '\n'.join(f'- {k}: {v}' for k,v in summary['gap_dispositions'].items())
    report += '\n\nEXTERNAL_REFERENCE_EXCLUDED 为按用户要求排除的外部引用文件；OUTSIDE_ACTIVITY_SCOPE 为现有活动词表不能忠实表达的事项。两者均不表示相关行为获准或义务已履行，也不计为已建模条款。UNRESOLVED 仍是未解决缺口。这里只统计模型自检，不是人工审定覆盖率。\n\n原始请求与输出分别在 requests/、responses/；补丁在 validated/；逐段处置在 gap_ledger.json；历史条款恢复及语义核验在 recovered_anchor_review.json；完整增量语料在 structured_asc.json。原有条款不删除，恢复候选中被判 QUESTIONABLE 的条款仅保留在核验记录中，不作为已核验规则加入。\n'
    (RUN/'补提取结果.md').write_text(report)
    return summary

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--review-history',action='store_true');ap.add_argument('--workers',type=int,default=4);args=ap.parse_args()
    if args.review_history:
        from scripts.review_asc_regressions import main as review_main
        sys.argv.remove('--review-history');return review_main()
    RUN.mkdir(parents=True,exist_ok=True)
    with (RUN/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        inv,jobs=prepare();summary=compile_result(jobs)
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        if not args.execute:return
        cfg=replace(base.load_config(ROOT/'configs/experiment.toml'),timeout_seconds=300,max_retries=0)
        base.save(RUN/'execution_state.json',{'status':'RUNNING','pid':os.getpid(),'workers':args.workers,'model':cfg.model,'started_unix':time.time()})
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(repair,j,cfg):j for j in jobs}
            for f in as_completed(futures):
                j=futures[f]
                try:
                    data=f.result();state={'status':'SUCCESS','added':len(data['clauses']),'dispositions':dict(Counter(a['status'] for a in data['paragraph_audit']))}
                except Exception as e:state={'status':'FAILED','error':str(e)}
                base.save(RUN/'progress'/f"{j['key']}.json",state);print(json.dumps({'chunk':j['key'],**state},ensure_ascii=False),flush=True)
                summary=compile_result(jobs)
        base.save(RUN/'execution_state.json',{'status':'FINISHED_WITH_FAILURES' if summary['pending_chunks'] else 'FINISHED','pid':os.getpid(),'finished_unix':time.time()})
        print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
