"""Recorded assistant source review of the AGPL repair; not human adjudication.

Raw API responses remain immutable, including the section 6/7 response that failed
the obligation-action contract after three attempts. Every correction is logged.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.reextract_agpl import RUN, NAMES, RANGES, CORPUS, save, digest, check, CHECKLIST
from license_checker.llm.client import extract_text
from license_checker.asc import validate_triple

def review(c):
    """Apply source-specific corrections; return one or more reviewed clauses."""
    c=deepcopy(c);lo=c['start_line'];label=c['clause_label'];a=c['activities'];C=c['C']
    def setc(kind,req=None,when=None):
        c['C']={'kind':kind}
        if req is not None:c['C']['requires']=req
        if when is not None:c['C']['when']=when
    def allof(*xs):return {'all':list(xs)}
    if lo==60:
        first=deepcopy(c);first['activities']=['Copy','Modify','Use']
        first['clause_label']=label+' / nonconveyed'
        first['C']={'kind':'CONDITIONALLY_PERMITTED','when':'covered_work_not_conveyed',
                    'requires':'license_otherwise_in_force'}
        c['activities']=['Distribute'];c['clause_label']=label+' / exclusive contractor'
        setc('CONDITIONALLY_PERMITTED',C['requires']['any'][1])
        return [first,c]
    if lo==62:
        c['activities']=['Distribute'];c['clause_label']=label+' / conveyance'
        ban=deepcopy(c);ban['activities']=['Sublicense'];ban['clause_label']=label+' / sublicense ban'
        ban['C']={'kind':'PROHIBITED'}
        ban['scope_note']='Sublicensing covered works is not allowed. Automatic original-licensor grants under section 10 make sublicensing unnecessary.'
        ban['condition_explanation']='This is a prohibition on sublicensing, not a prohibition on authorized conveyance.'
        return [c,ban]
    if lo==69:c['activities']=['Distribute']
    if lo==70:
        c['activities']=['Charge','SellCopies']
        support=deepcopy(c);support['activities']=['Charge'];support['clause_label']=label+' / support fee'
        support['C']={'kind':'PERMITTED','when':'fee_for_support_or_warranty_protection'}
        return [c,support]
    if lo==73:
        c['activities']=['Distribute']
        c['C']['when']='conveying_modified_work_in_source_code_form_under_agpl'
        req=c['C']['requires']['all']
        req[4]={'any':['license_entire_work_as_a_whole_under_this_license_to_copy_possessors',
                       'separately_received_permission_validly_authorizes_other_licensing']}
        req[5]={'any':['work_has_no_interactive_user_interfaces',
                       'every_interactive_interface_displays_appropriate_legal_notices',
                       'original_program_interfaces_did_not_display_appropriate_legal_notices']}
        c['condition_explanation']='Conveyance conditions, not restrictions on private modification. Section 4 conditions and 5(a)-(d) are cumulative as applicable. The interface exception is explicit. This license does not grant alternative licensing, but does not invalidate independently received permission; the scope of that independent permission must be checked separately.'
    if lo==78:
        c['activities']=['Distribute'];c['objects']=['CombinedProduct']
        c['C']['requires']['all'].append('applicable_agpl_conveyance_conditions_satisfied_for_covered_component_only')
        c['scope_note']+=' This rule imposes no AGPL terms on the independent other parts of an aggregate and gives no permission to distribute third-party components without their own authorization.'
    if lo==81:
        c['activities']=['Distribute']
        req=c['C']['requires']['all']
        if '6(a)' in label:req.append('object_code_in_or_embodied_in_physical_product_or_distribution_medium')
        if '6(b)' in label:
            req[-1]['any'][0]=allof('source_copy_on_durable_medium_customarily_used_for_software_interchange',req[-1]['any'][0])
        if '6(c)' in label:req.append('accompany_each_individual_object_code_copy_with_copy_of_section_6b_written_offer')
        if '6(d)' in label:
            req.remove('offer_equivalent_corresponding_source_access_through_same_place_at_no_further_charge')
            req.append({'any':['equivalent_source_access_same_place_same_way_no_further_charge',
                allof('object_code_on_network_server','source_on_different_server_with_equivalent_copying_facilities',
                      'clear_source_directions_next_to_object_code','source_access_no_further_charge')]})
            req.append('ensure_source_remains_available_as_long_as_requirements_demand')
            c['condition_explanation']+=' The equivalent different-server path is an alternative, not a violation of the same-place path; recipients need not copy source along with object code.'
        c['scope_note']+=' Corresponding Source has the section 1 meaning, including build/install/run/modify scripts and specifically required linked source, excluding System Libraries and specified general-purpose tools.'
    if lo==87:
        c['activities']=['Distribute'];c['C']['when']='invoking_section_6_system_library_exclusion'
        c['C']['requires']['all'].append('other_applicable_section_6_conditions_satisfied')
    if lo==93:
        c['activities']=['ProvideSource']
        c['C']['when']['all'].append({'not':'neither_licensee_nor_any_third_party_retains_ability_to_install_modified_object_code_on_user_product'})
        c['C']['requires']=allof('corresponding_source_accompanied_by_installation_information',
            'installation_information_sufficient_to_install_and_execute_modified_work_in_user_product')
        c['condition_explanation']+=' The ROM/no-retained-installation-ability exception gates applicability; it is not the content of the obligation. User Product and Installation Information have the definitions in lines 89-91.'
    if lo==95:
        c['activities']=['ProvideNetworkService']
        setc('UNSPECIFIED',when='considering_network_access_after_recipient_modification')
        c['condition_explanation']='Representation limit: canonical activities lack DenyNetworkAccess. The text permits denial when the modification materially adversely affects network operation or breaches communication rules, and does not require continued support/warranty/updates. This rule intentionally grants no new hosting permission; those boundaries remain in scope_note.'
    if lo==113:
        c['activities']=['Modify'];setc('CONDITIONALLY_PERMITTED',C['requires'],C['when'])
        c['scope_note']+=' Here Modify is adding section 7 terms, not an obligation to modify software.'
    if lo==118:c['activities']=['Copy','Distribute','Modify']
    if lo==120:
        setc('CONDITIONALLY_PERMITTED',allof('comply_with_other_applicable_agpl_activity_conditions',
            {'any':[{'not':'particular_holder_has_explicitly_and_finally_terminated_license'},
                    'particular_holder_failed_to_notify_by_reasonable_means_before_60_days_after_cessation']}),
            'all_violations_ceased_and_invoking_particular_holder_reinstatement')
        c['condition_explanation']='After all violations cease, provisional reinstatement lasts unless and until that holder explicitly finally terminates; non-notification before 60 days gives permanent reinstatement. The conditions above express alternative availability of restored rights, not a duty to attain a reinstatement status. Restored rights remain subject to applicable activity conditions.'
    if lo==122:
        c['C']['requires']='comply_with_other_applicable_agpl_activity_conditions'
        c['scope_note']+=' Reinstatement is a consequence of the stated trigger, not a separate duty to make the license reinstated.'
    if lo==124:
        c['actor_role']='downstream_recipient';setc('CONDITIONALLY_PERMITTED','comply_with_applicable_agpl_conditions',
            allof('received_copy_or_rights_under_agpl_from_upstream','upstream_licensee_rights_terminated'))
        c['scope_note']='Termination of upstream rights does not terminate previously granted downstream licenses. This grants no new license to the terminated upstream party. That party cannot receive new section 10 licenses for the same material until permanent reinstatement; canonical A lacks ReceiveLicense, so that eligibility consequence remains a recorded representation limitation.'
        c['condition_explanation']='The actor is a prior downstream recipient, not the terminated party. Previously received rights survive subject to this license; new-license eligibility for the terminated party is not modeled as permission to Use.'
    if lo==127:
        c['activities']=['Modify','Distribute','Copy']
        setc('CONDITIONALLY_PERMITTED','accept_agpl_and_comply_with_applicable_activity_conditions',
             'modifying_or_propagating_other_than_ancillary_peer_to_peer_receipt')
        c['scope_note']+=' Receiving/running a copy does not require acceptance. This clause is only an acceptance boundary; it does not independently grant permissions absent the operative grants.'
    if lo==132:
        c['activities']=['Use','Modify','Distribute'];c['actor_role']='entity_transaction_party_receiving_copy'
        setc('CONDITIONALLY_PERMITTED','within_predecessor_licenses_and_comply_with_their_applicable_conditions',
             'propagation_results_from_entity_transaction_and_party_receives_copy')
        c['scope_note']+=' The right to source possession is recorded here as a beneficiary right, not an obligation on this recipient to provide source.'
    if lo==134:
        c['activities']=['Distribute','Charge']
        setc('CONDITIONALLY_PROHIBITED','imposes_further_restrictions_on_exercise_of_agpl_granted_or_affirmed_rights')
        c['condition_explanation']='Distribute is distribution with further restrictions; Charge is charging for exercise of granted rights, not sale of copies or support. Patent litigation is an additional explicitly stated example retained in scope_note because the taxonomy lacks InitiateLitigation.'
    if lo==141:
        setc('PERMITTED',when='exercising_contributor_essential_patent_claims_over_contributor_version_contents')
        c['scope_note']+=' This patent-only grant does not override copyright conveyance conditions; further-modification-only claims are outside the essential-claims definition.'
    if lo==145:c['activities']=['Distribute']
    if lo==148:
        c['actor_role']='recipient_beneficiary_of_patent_license';c['C']['requires']='exercise_within_automatically_extended_patent_license_scope'
    if lo==150:
        triggers=c['C']['when']['all']
        triggers[-1]=allof({'not':'arrangement_entered_before_2007_03_28'}, {'not':'patent_license_granted_before_2007_03_28'})
        triggers.append({'any':['discriminatory_license_in_connection_with_conveyed_copies_or_copies_made_from_them',
                               'discriminatory_license_primarily_for_specific_products_or_compilations_containing_covered_work']})
        setc('CONDITIONALLY_PROHIBITED',{'all':triggers})
    if lo==166:
        c['C']['when']='exercising_section_14_license_version_choice'
        c['C']['requires']={'all':[c['C']['requires'],'comply_with_terms_of_validly_chosen_version']}
        c['scope_note']+=' This is a version-election scope rule, not a ban on use under an AGPL-only designation. An only designation does not satisfy the later-version option unless separately authorized.'
    if lo==168:
        c['C']['when']='exercising_proxy_authorized_future_version_choice'
        c['C']['requires']['all'].append('comply_with_terms_of_validly_chosen_version')
    if lo==170:
        setc('UNSPECIFIED',when='licensee_chooses_to_follow_later_agpl_version')
        c['condition_explanation']='No independent new activity permission is extracted from this descriptive boundary. Later versions may change permissions, but electing them adds no obligations to authors/holders; the actual later version must be supplied for further analysis.'
    return [c]

def main():
    before=json.loads((RUN/'before_corpus.json').read_text());lines=(ROOT/'许可证原文'/NAMES[0]).read_text().splitlines()
    rows=[x for x in json.loads(CHECKLIST.read_text())['items'] if x['license']=='AGPL-3.0-only']
    allclauses=[];changes=[];raw_failed=[]
    for lo,hi in RANGES:
        key=f'L{lo}-L{hi}';valid=RUN/'validated'/f'{key}.json'
        if valid.exists():data=json.loads(valid.read_text())['data']
        else:
            path=RUN/'responses'/f'{key}-attempt3.json'
            data=json.loads(extract_text(json.loads(path.read_text())))
            raw_failed.append({'chunk':key,'raw_response':str(path.relative_to(ROOT)),
                'reason':'Third response failed obligation-action validation; assistant reviewed corrections are separate from raw validation.'})
        for old in data['clauses']:
            edited=review(old)
            if edited!=[old]:changes.append({'original':old,'reviewed':edited,'reason':'Assistant source review against cited AGPL paragraph and definitions; not human expert adjudication'})
            allclauses.extend(edited)
    for c in allclauses:
        # Reuse source/schema validation with an empty ledger (semantic review separately below).
        check({'clauses':[c],'coverage_notes':[],'coverage_audit':[]},lines,58,179,[])
    rules=[]
    for name in NAMES:
        sid=next(s['source_id'] for s in before['sources'] if s['filename']==name)
        for c in allclauses:
            lo,hi=c['start_line'],c['end_line']
            for a in c['activities']:
                for obj in c['objects']:
                    asc={'A':a,'S':{'artifact':'$LICENSED_MATERIAL','kind':obj},'C':c['C']}
                    sig=json.dumps([name,lo,hi,asc,c['actor_role'],c['scope_note']],sort_keys=True)
                    rules.append({'rule_id':sid+'-agpl-v2-'+digest(sig.encode())[:16],
                        'license_source_id':sid,'license_id':name,'clause_id':f'L{lo}-L{hi}',
                        'clause_label':c['clause_label'],'ASC':asc,'actor_role':c['actor_role'],
                        'scope_note':c['scope_note'],'condition_explanation':c['condition_explanation'],
                        'source_excerpt':'\n'.join(lines[lo-1:hi]),'extraction_status':'LLM_EXTRACTED_ASSISTANT_REVIEWED',
                        'extraction_method':'gpt-6-luna full-text extraction plus explicitly logged assistant semantic corrections',
                        'review_status':'ASSISTANT_SOURCE_REVIEW_NOT_INDEPENDENT_EXPERT'})
    save(RUN/'reviewed_candidate.json',{'sources':[s for s in before['sources'] if s['filename'] in NAMES],
          'rules':rules,'clauses_before_activity_object_expansion':len(allclauses),
          'assistant_review_required_for_failed_chunks':raw_failed})
    save(RUN/'assistant_corrections.json',changes)
    # Same 21-unit checklist as baseline; conservative partial ratings remain.
    partial={1:'输出适用范围仍主要保留于注释，未建立独立输出对象。',
             11:'五种源码交付路径已分别建模；多个具体条件仍为文本谓词，尚无场景级独立验证。',
             12:'安装信息触发、ROM例外和格式已补；User Product定义仍依赖解释，拒绝网络接入动作超出既有taxonomy。',
             13:'附加条款类型、权限与通知已补；不同授权/添加活动仍有复合规则，尚未完全原子化。',
             14:'终止与30/60天恢复已补；终止者的新许可接收资格缺少独立A，留在解释中。',
             16:'自动许可、禁止附加限制已补；实体交易源码占有权及专利诉讼动作未独立建模。',
             17:'专利许可、三选一义务与日期例外已补；专利主体/版本与版权作用域仍需独立专家复核。',
             21:'版本与代理选择条件已补；采用Use承载版本选择，taxonomy无独立选择版本动作。'}
    audit=[]
    for x in rows:
        lo,hi=[int(v[1:]) for v in x['lines'].split('-')]
        linked=[c['clause_label'] for c in allclauses if c['start_line']<=hi and c['end_line']>=lo]
        assert linked,x['unit']
        audit.append({'unit':x['unit'],'topic':x['topic'],'before':x['status'],
            'after':'部分' if x['unit'] in partial else '完整','clause_labels':linked,
            'review_note':partial.get(x['unit'],'已对照对应原文确认主题要求与关键触发/例外得到表示；模型辅助判断，待独立专家复核。')})
    save(RUN/'coverage_comparison.json',{'reviewer':'assistant; checklist reused for repair, not held-out validation',
        'units':audit,'before':{'complete':0,'partial':1,'missing':20},
        'after':{'complete':13,'partial':8,'missing':0},
        'strict_thematic_coverage_before_pct':0,'strict_thematic_coverage_after_pct':61.90,
        'at_least_partial_before_pct':4.76,'at_least_partial_after_pct':100,
        'not_full_legal_recall':True})
    print(json.dumps({'reviewed_clauses':len(allclauses),'rules_per_alias':len(rules)//2,
         'correction_groups':len(changes),'assistant_repaired_failed_chunks':raw_failed},ensure_ascii=False))

if __name__=='__main__':main()
