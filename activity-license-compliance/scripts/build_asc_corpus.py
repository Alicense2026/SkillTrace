"""Build a provenance-linked first-pass ASC corpus from the checked-in source texts.

This is an extraction/serialization utility, not a legal interpreter. Rule templates
are deliberately sparse: each emitted ASC points to a literal source passage.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from license_checker.asc import validate_triple
from license_checker.taxonomy import normalize_activity

SOURCE_DIR = ROOT / "许可证原文"
OUT = ROOT / "data" / "structured_asc_v1.json"

# Each template is (source-id family, locator regex, clause label, activities,
# object kinds, modality, condition, actor note, scope note). Regexes locate an
# exact source paragraph; they never manufacture quoted wording.
P = []
def add(family, rx, clause, acts, objs=("OriginalArtifact",), kind="CONDITIONALLY_PERMITTED",
        requires=True, actor="licensee", scope=""):
    P.append(dict(family=family, rx=rx, clause=clause, activities=acts, objects=objs,
                  kind=kind, requires=requires, actor=actor, scope=scope))

SOFTWARE_PERMISSIVE = {"LICENSE-BSD 2-Clause.txt", "LICENSE-BSD 3-Clause.txt",
                       "OFFIS License.txt", "LICENSE-WTFPL.txt"}
add("isc", r"Permission to use, copy, modify, and /or distribute this software.*?\n", "permission grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED",
    "retain_applicable_notices", scope="Broad grant; source-specific notice conditions are represented only when present in the cited grant passage.")
add("zerobsd", r"Permission to use, copy, modify, and/or distribute this software for\s+any purpose with or without fee is hereby granted\.", "0BSD permission grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PERMITTED", True,
    scope="0BSD grant expressly allows use with or without fee; no notice condition is stated in this grant.")
add("postgres", r"Permission to use, copy, modify, and distribute this software and its documentation.*?\n", "permission grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "preserve_copyright_notice_and_permission_paragraph",
    scope="PostgreSQL grant expressly says without fee and includes a notice condition.")
add("software_permissive", r"Redistribution and use in source and binary forms.*?permitted", "permission grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "retain_applicable_notices",
    scope="BSD-style redistribution grant; notice obligations are separately cited when available.")
add("software_permissive", r"free access is hereby granted as a license to use.*?(?:\.|\n)", "permission grant",
    ["Use", "Copy", "Modify", "CreateDerivative"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "CONDITIONALLY_PERMITTED", "retain_copyright_notice", scope="OFFIS grant wording is separately scoped; no commercial grant inferred beyond the cited text.")
add("software_permissive", r"Everyone is permitted to copy and distribute verbatim or modified.*?\n", "permission grant",
    ["Copy", "Modify", "CreateDerivative", "Distribute", "Publish"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "PERMITTED", True, scope="WTFPL grant as worded; other liability/disclaimer text is outside this permission clause.")

add("bsl", r"Permission is hereby granted.*?\n", "grant and time-limited restriction",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "include_license_and_notices",
    scope="BSL grant is subject to its Change License and other terms; the transition date/Additional Use Grant is not encoded here.")
add("bsl", r"The copyright notices in the Software.*?\n", "copy notice obligation",
    ["Copy", "Distribute", "Publish"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "OBLIGATORY", True,
    scope="Notice-preservation condition for copies, in whole or part.")

add("apache", r"2\. Grant of Copyright License.*?(?=\n\s*\n|$)", "2. Grant of Copyright License",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PERMITTED", True, scope="Copyright grant; patent rights are not represented in this ASC set.")
add("apache", r"You may reproduce and Distribute copies of the Work or Derivative Works thereof.*?(?=\n\s*\n|$)", "4. Redistribution",
    ["Copy", "Distribute", "Publish", "SellCopies"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork", "CombinedProduct"),
    "CONDITIONALLY_PERMITTED", "include_license_and_preserve_notices", scope="Redistribution requirements are a conjunction in the referenced section; verify source/binary-specific subclauses.")

add("mit", r"Permission is hereby granted, free of charge.*?\n", "permission grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "Sublicense", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "include_copyright_and_permission_notice",
    scope="MIT/MIT-0 text matched separately; MIT-0 has no attribution condition and is corrected below.")
add("mit", r"The above copyright notice and this permission notice shall be included.*?\n", "notice condition",
    ["Copy", "Distribute", "Publish", "Sublicense", "SellCopies"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "OBLIGATORY", True,
    scope="MIT notice condition.")
add("mit", r"Permission is hereby granted, free of charge.*?Software.*?deal in the Software without restriction.*?\n", "MIT permission grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Sublicense", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "include_copyright_and_permission_notice",
    scope="MIT grant; the notice condition is set out in the following sentence.")
add("mit0", r"Permission is hereby granted, free of charge.*?deal in the Software without restriction.*?\n", "MIT-0 permission grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Sublicense", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PERMITTED", True,
    scope="MIT-0 grant; no attribution condition is imposed by this grant text.")

add("cc", r"You are granted the Licensed Rights.*?(?:\.|\n)", "2(a) Grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "within_license_scope",
    scope="Creative Commons grant is limited to Licensed Rights and material covered by copyright/similar rights; database rights may also apply.")
add("cc", r"the Licensor hereby grants You a worldwide, royalty-free.*?(?=\n\s*\n|$)", "2(a)(1) Grant of Licensed Rights",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "comply_with_CC_license_conditions",
    scope="CC legal-code grant; applicable attribution, noncommercial, or share-alike terms are separately represented where extracted.")
add("cc0", r"Affirmer hereby overtly, fully, permanently,.*?for any purpose whatsoever.*?(?=\n\s*\n|$)", "2. Waiver",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PERMITTED", True,
    scope="CC0 waiver text; fallback license and liability provisions are separate clauses.")
add("cc0", r"Should any part of the Waiver for any reason be judged legally invalid or ineffective.*?(?=\n\s*\n|$)", "3. Public License Fallback",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PERMITTED", True,
    scope="CC0 fallback public license; scope is limited by the rights and terms in the cited clause.")
add("cc", r"You may not exercise any of the Licensed Rights.*?(?:\.|\n)", "2(a) limitations",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "CONDITIONALLY_PROHIBITED", "outside_license_scope", scope="Only the literal limitation passage is mapped; it does not imply a general prohibition.")
add("cc", r"You may not exercise any of the Licensed Rights for.*?NonCommercial.*?(?:\.|\n)", "2(a) NonCommercial limitation",
    ["CommercialUse", "Charge", "SellCopies", "OfferPaidAccess"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "PROHIBITED", True, scope="CC BY-NC variants; exact definition of NonCommercial must be reviewed in full source context.")
add("cc", r"You must.*?indicate.*?modifications.*?(?:\.|\n)", "3 Attribution / modification notice",
    ["Distribute", "Publish"], ("ModifiedArtifact", "DerivativeWork"), "OBLIGATORY", True,
    scope="Attribution marking obligation; see full clause for required information and exceptions.")
add("cc", r"You must.*?offer.*?Adapted Material.*?same License.*?(?:\.|\n)", "3 ShareAlike condition",
    ["Distribute", "Publish", "Sublicense"], ("DerivativeWork",), "OBLIGATORY", True,
    scope="CC BY-SA / BY-NC-SA share-alike obligation when sharing Adapted Material.")

add("gpl", r"You may convey verbatim copies of the Program's source code.*?(?=\n\s*\n|$)", "4. Conveying Verbatim Copies",
    ["Copy", "Distribute", "Publish", "SellCopies"], ("OriginalArtifact",), "CONDITIONALLY_PERMITTED", "provide_license_and_notices",
    scope="Verbatim conveyance terms; source-code provision details in the same section apply.")
add("gpl", r"You may convey a work based on the Program.*?(?=\n\s*\n|$)", "5. Conveying Modified Source Versions",
    ["Modify", "CreateDerivative", "Distribute", "Publish", "SellCopies"], ("ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED",
    "license_whole_work_under_GPL_and_provide_source", scope="GPL copyleft obligations; scope is a covered work based on the Program.")
add("gpl", r"You may convey a covered work in object code form.*?(?=\n\s*\n|$)", "6. Conveying Non-Source Forms",
    ["Distribute", "Publish", "SellCopies", "ProvideSource"], ("ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED",
    "provide_corresponding_source_by_allowed_method", scope="Object-code conveyance; source method and duration are specified in full clause.")
add("agpl", r"if you modify the Program, your modified version must prominently offer all users.*?(?=\n\s*\n|$)", "13. Remote Network Interaction",
    ["ProvideNetworkService", "RemoteInteraction", "ProvideSource"], ("ModifiedArtifact", "DerivativeWork"), "OBLIGATORY",
    "offer_corresponding_source_to_remote_users", scope="AGPL network source-offer obligation for a modified version supporting remote interaction.")

add("mpl", r"Each Contributor hereby grants You a world-wide.*?(?=\n\s*\n|$)", "2.1 Contributor Grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PERMITTED", True, scope="MPL grants are subject to this License and limited to Covered Software/Contribution rights.")
add("mpl", r"You may create and distribute Larger Works.*?(?=\n\s*\n|$)", "3.3 Distribution of a Larger Work",
    ["Combine", "Bundle", "Distribute", "Publish"], ("CombinedProduct",), "CONDITIONALLY_PERMITTED", "comply_for_covered_software_files",
    scope="Larger Work may be under different terms; Covered Software remains subject to MPL obligations.")

add("epl", r"Subject to the terms of this Agreement, each Contributor hereby grants.*?(?=\n\s*\n|$)", "2.1 Copyright Grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PERMITTED", True, scope="EPL grant subject to agreement; file-level reciprocity clauses remain separately applicable.")
add("epl", r"When the Program is Distributed as source code.*?(?=\n\s*\n|$)", "3.1 Contributions",
    ["Distribute", "Publish", "ProvideSource"], ("ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "provide_source_and_license_notice",
    scope="EPL source distribution obligations; see the complete section for exact requirements.")

add("eupl", r"Subject to the terms and conditions of this Licence, the Licensor hereby grants.*?(?=\n\s*\n|$)", "5. Scope of the rights granted",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "comply_with_EUPL_conditions",
    scope="EUPL licensed rights; downstream distribution conditions require full-clause review.")
add("eupl", r"The Licensor hereby grants You a worldwide, royalty-free, non-exclusive.*?(?=\n\s*\n|$)", "2. Scope of the rights granted",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "comply_with_EUPL_conditions",
    scope="Article 2 grant; distribution and copyleft conditions remain relevant.")

add("openrail", r"Subject to the terms and conditions of this License.*?grants.*?(?=\n\s*\n|$)", "Grant",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "comply_with_use_restrictions_and_attribution",
    scope="OpenRAIL grant does not cancel use-based restrictions; mapped use restrictions require the corresponding restriction clauses.")
add("openrail", r"You agree not to use the Model.*?(?:\n\s*\n|$)", "Use-based restrictions",
    ["Use", "CommercialUse", "ProvideNetworkService", "RemoteInteraction"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "CONDITIONALLY_PROHIBITED", "use_is_listed_restricted_use", scope="OpenRAIL restrictions are use-case prohibitions; do not construe as a blanket commercial-use ban.")

add("llama", r"You are granted a non-exclusive, worldwide, non-transferable.*?license.*?(?=\n\s*\n|$)", "1(a) Grant of Rights",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "comply_with_Llama_agreement",
    scope="Llama Materials grant; product/user thresholds and naming obligations vary by version and are not generalized here.")
add("llama", r"You are granted a non-exclusive, worldwide, non-\s*transferable and royalty-free limited license.*?(?=\n\s*\n|$)", "1(a) Grant of Rights (Llama 2 wording)",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "CommercialUse", "Charge", "SellCopies"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "comply_with_Llama_agreement",
    scope="Llama 2-specific grant wording; the additional commercial threshold is version-specific.")
add("llama", r"If you distribute or make available the Llama Materials.*?(?=\n\s*\n|$)", "1(b) Redistribution and Use",
    ["Distribute", "Publish", "Sublicense", "Bundle"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork", "CombinedProduct"),
    "OBLIGATORY", "provide_agreement_and_required_notices", scope="Redistribution conditions; exact duties differ by version and recipient/product scenario.")
add("llama", r"If you distribute or make the Llama Materials, or any derivative works thereof, available to a third party.*?(?=\n\s*\n|$)", "1(b)(i) Redistribution (Llama 2 wording)",
    ["Distribute", "Sublicense", "Bundle"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork", "CombinedProduct"),
    "OBLIGATORY", "provide_agreement_and_required_attribution", scope="Llama 2 redistribution duties as written; recipient conditions remain source-specific.")

add("baichuan", r"您可以.*?(?:使用|复制|修改|分发).*?(?:模型|许可).*?(?:\n|。)", "许可授权",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute", "Publish", "CommercialUse", "Charge"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "comply_with_Baichuan_license",
    scope="仅按命中的具体授权条款映射；分发、托管服务可能按协议定义归入分发。")
add("baichuan", r"根据本许可协议的条款和条件，许可方特此授予您.*?(?=\n\s*\n|$)", "许可授权及非商业用途边界",
    ["Use", "Copy", "Modify", "CreateDerivative"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "CONDITIONALLY_PERMITTED", "non_commercial_use_or_prior_written_commercial_authorization",
    scope="Baichuan 2 grant; commercial model use requires prior written authorization, separately encoded below.")
add("baichuan", r"如果您计划将 Baichuan 2 模型及模型衍生品用作商业用途.*?(?=\n\s*\n|$)", "商业用途事先书面授权",
    ["CommercialUse", "Charge", "SellCopies", "OfferPaidAccess"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "CONDITIONALLY_PERMITTED", "prior_written_authorization_from_licensor", scope="Commercial use is not categorically barred; it requires prior written authorization.")
add("baichuan", r"您修改 Baichuan 2 模型得到模型衍生品，必须以显著的方式说明修改的内容.*?(?=\n\s*\n|$)", "修改标注及限制传递",
    ["Modify", "CreateDerivative", "Distribute"], ("ModifiedArtifact", "DerivativeWork"), "OBLIGATORY", True,
    scope="Mark modifications and do not enable breach of the license restrictions.")
add("baichuan", r"您不得出于任何军事或非法目的使用、复制、修改.*?(?=\n\s*\n|$)", "军事或非法用途限制",
    ["Use", "Copy", "Modify", "CreateDerivative", "Distribute"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "CONDITIONALLY_PROHIBITED", "military_or_illegal_purpose", scope="Prohibition is limited to the specified purposes.")

add("provider_terms", r"(?:gives|grants) (?:Customer|you).*?permission to use the Services.*?(?:\.|\n)", "service access grant",
    ["Use", "RemoteInteraction", "ProvideNetworkService"], ("OriginalArtifact",), "CONDITIONALLY_PERMITTED", "comply_with_service_terms",
    actor="customer", scope="Service access only; it is not a grant to copy/modify/distribute provider software or model weights.")
add("provider_terms", r"We grant you a right to access and use the Services.*?(?=\n\s*\n|$)", "service access grant",
    ["Use", "RemoteInteraction", "ProvideNetworkService"], ("OriginalArtifact",), "CONDITIONALLY_PERMITTED", "comply_with_service_terms",
    actor="customer", scope="DeepSeek Open Platform API service access; not a model-weight redistribution grant.")
add("provider_terms", r"You are granted a limited, non-exclusive.*?license.*?(?:\.|\n)", "service/product license grant",
    ["Use", "RemoteInteraction", "ProvideNetworkService"], ("OriginalArtifact",), "CONDITIONALLY_PERMITTED", "comply_with_service_terms",
    actor="customer", scope="Commercial vendor terms; do not infer redistribution or modification rights from service access.")
add("provider_terms", r"You may not use the Services to develop models that compete.*?(?:\.|\n)", "model competition restriction",
    ["Use", "Modify", "CreateDerivative"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PROHIBITED", True,
    actor="customer", scope="Gemini API restriction; competing-model definition/context remains source-defined.")
add("provider_terms", r"(?:without our permission|without prior written consent).*?(?:distribute|resell|sublicense|make available).*?(?:\.|\n)", "redistribution restriction",
    ["Distribute", "Publish", "Sublicense", "OfferPaidAccess"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"), "PROHIBITED", True,
    actor="customer", scope="Only applies if the matched paragraph expressly restricts redistribution/resale.")
add("provider_terms", r"Customer will pay.*?(?:Fees|fees).*?(?:\.|\n)", "service fee obligation",
    ["Charge"], ("OriginalArtifact",), "OBLIGATORY", "service_fees_are_due_under_order_form", actor="customer",
    scope="Direction is customer-to-provider payment; this is not evidence that customer may charge its downstream users.")
add("provider_terms", r"You shall clearly disclose to your end users that the Output content is generated by AI.*?(?:\.|\n)", "AI output disclosure obligation",
    ["ProvideNetworkService", "RemoteInteraction"], ("OriginalArtifact",), "OBLIGATORY", True, actor="customer",
    scope="DeepSeek end-user disclosure rule for outputs supplied through the service.")

add("policy", r"You may not use nor allow others to use.*?(?:\n|:)", "prohibited use policy",
    ["Use", "CommercialUse", "ProvideNetworkService", "RemoteInteraction"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "CONDITIONALLY_PROHIBITED", "use_falls_within_policy_prohibition", scope="AUP is a use restriction, not a general license grant.")

add("policy", r"you shall not.*?(?:\n|。)", "禁止用途条款",
    ["Use", "CommercialUse", "ProvideNetworkService", "RemoteInteraction"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "CONDITIONALLY_PROHIBITED", "conduct_matches_prohibited_use", actor="user", scope="Chinese provider terms: only a matched explicit prohibition is included.")
add("policy", r"您不得.*?(?:\n|。)", "明确禁止条款",
    ["Use", "Modify", "CreateDerivative", "Distribute", "CommercialUse", "Charge", "OfferPaidAccess"],
    ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork", "CombinedProduct"), "CONDITIONALLY_PROHIBITED",
    "conduct_matches_prohibition_in_excerpt", actor="user", scope="A source-local Chinese prohibition; inspect full paragraph for target and exceptions.")
add("policy", r"您仅可以非商业的、个人研究学习的方式使用.*?(?:\n|。)", "non-commercial-use limit",
    ["CommercialUse", "Charge", "SellCopies", "OfferPaidAccess"], ("OriginalArtifact", "ModifiedArtifact", "DerivativeWork"),
    "PROHIBITED", True, actor="user", scope="智谱 free-feature limitation; paid-feature authorization is a separate clause.")
add("policy", r"您可以在按照.*?支付费用后.*?商业化使用.*?(?:\n|。)", "paid commercial-use authorization",
    ["CommercialUse", "Charge", "OfferPaidAccess"], ("OriginalArtifact", "DerivativeWork"), "CONDITIONALLY_PERMITTED", "pay_required_fee_and_follow_product_rules",
    actor="user", scope="智谱 paid feature/model use; authorization is tied to product rules and payment.")

FAMILIES = {
    "software_permissive": SOFTWARE_PERMISSIVE, "isc": {"LICENSE-ISC.txt"},
    "zerobsd": {"0BSD.txt"}, "postgres": {"PostgreSQL License.txt"},
    "cc0": {"LICENSE-CC0-1.0.txt"},
    "bsl": {"BSL-1.0.txt"}, "apache": {"LICENSE-APACHE.txt"},
    "mit": {"LICENSE-MIT.txt"},
    "mit0": {"LICENSE-MIT-0.txt"},
    "cc": {"LICENSE-CC-BY-4.0.txt", "CC-BY-NC-4.0.txt", "LICENSE-CC-BY-NC-SA-4.0.txt", "LICENSE-CC-BY-SA-4.0.txt"},
    "gpl": {"LICENSE-GPL-3.0.txt"}, "agpl": {"LICENSE-AGPL-3.0-only.txt", "LICENSE-AGPL-3.0-or-later.txt"},
    "mpl": {"LICENSE-MPL-2.0.txt"}, "epl": {"LICENSE-EPL-2.0.txt"}, "eupl": {"LICENSE-EUPL-1.2.txt"},
    "openrail": {"CreativeML-OpenRAIL-M.txt", "openRAIL++-M License.txt"},
    "llama": {"LLAMA 2 COMMUNITY LICENSE AGREEMENT.txt", "LLAMA 3 COMMUNITY LICENSE AGREEMENT.txt", "LLAMA 3.1 COMMUNITY LICENSE AGREEMENT.txt", "LLAMA 3.2 COMMUNITY LICENSE AGREEMENT.txt", "LLAMA 3.3 COMMUNITY LICENSE AGREEMENT.txt", "LLAMA 4 COMMUNITY LICENSE AGREEMENT.txt"},
    "baichuan": {"Baichuan2-community-license.txt"},
    "provider_terms": {"ANTHROPIC.txt", "DeepSeek.txt", "Gemini API Additional Terms of Serv.txt", "OpenAI.txt", "mistral+license.txt"},
    "policy": {"Gemma Prohibited Use Policy.txt", "aliyun.txt", "bigmodel 智谱用户协议.txt"},
}

def paragraphs(text):
    # Keep line structure, but merge wrapped source paragraphs; retain line spans.
    blocks=[]; lines=text.splitlines(); start=None; buf=[]
    for n,line in enumerate(lines,1):
        if line.strip():
            if start is None: start=n
            buf.append(line.rstrip())
        elif buf:
            blocks.append((start,n-1,"\n".join(buf)))
            start=None; buf=[]
    if buf: blocks.append((start,len(lines),"\n".join(buf)))
    return blocks

def main():
    if OUT.exists() and json.loads(OUT.read_text(encoding='utf-8')).get('extensions'):
        raise SystemExit('Corpus contains incremental extractions. Use extend_asc_corpus.py; refusing to overwrite them with sparse templates.')
    sources=[]; rules=[]; skipped=[]
    for path in sorted(SOURCE_DIR.glob("*.txt")):
        raw=path.read_bytes(); text=raw.decode("utf-8",errors="replace")
        sha=hashlib.sha256(raw).hexdigest(); name=path.name
        source_id="src-"+sha[:12]
        family=next((fam for fam,names in FAMILIES.items() if name in names), None)
        status="EXCLUDED_BY_USER" if name=="LGPL-3.0.txt" else ("INCLUDED" if family else "UNCLASSIFIED_SOURCE")
        first=next((line.strip() for line in text.splitlines() if line.strip()), "")
        sources.append({"source_id":source_id,"filename":name,"sha256":sha,"bytes":len(raw),
                        "first_nonempty_line":first[:240],"family":family,"status":status})
        if name=="LGPL-3.0.txt":
            skipped.append({"source_id":source_id,"reason":"用户指示 LGPL 不纳入后续分析；原文留存并登记，不提取活动条款。"})
            continue
        if not family: continue
        blocks=paragraphs(text)
        for template in P:
            if template["family"] != family: continue
            rx=re.compile(template["rx"],re.I|re.S)
            found=next(((lo,hi,b) for lo,hi,b in blocks if rx.search(b+"\n")),None)
            if not found: continue
            lo,hi,excerpt=found
            excerpt=excerpt[:5000]
            clause_id=f"L{lo}-L{hi}"
            for activity in dict.fromkeys(normalize_activity(a) for a in template["activities"]):
                for obj in template["objects"]:
                    c={"kind":template["kind"]}
                    if template["kind"].startswith("CONDITIONALLY_"): c["requires"]=template["requires"]
                    triple={"A":activity,"S":{"artifact":"$LICENSED_MATERIAL","kind":obj},"C":c}
                    validate_triple(triple)
                    rules.append({"rule_id":f"{source_id}-{clause_id}-{activity}-{obj}","license_source_id":source_id,
                                  "license_id":name,"clause_id":clause_id,"clause_label":template["clause"],
                                  "ASC":triple,"actor_role":template["actor"],"scope_note":template["scope"],
                                  "source_excerpt":excerpt,"extraction_status":"FIRST_PASS_REVIEW_REQUIRED"})
    populated={r["license_id"] for r in rules}
    for source in sources:
        if source["status"]=="INCLUDED" and source["filename"] not in populated:
            source["status"]="INCLUDED_NO_RULE_MATCHED"
    data={"schema_version":"asc-corpus-1.0","created_by":"scripts/build_asc_corpus.py",
          "method":"Sparse clause-linked ASC extraction; only exact-matched passages yield rules; no default permission inferred.",
          "sources":sources,"rules":rules,"excluded_sources":skipped,
          "limitations":["This is a first-pass structured corpus, not a legal opinion or exhaustive clause-by-clause certification.",
                         "Every rule retains its literal source excerpt and line locator; validate clause boundaries and the stated condition against the full clause before automated conflict adjudication.",
                         "Commercial/API terms and model/community licenses are separate source identities and may have different subject matter and parties.",
                         "No ASC record means extraction has not established a rule; it must not be treated as PERMITTED."]}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    counts={}
    for r in rules: counts[r["license_id"]]=counts.get(r["license_id"],0)+1
    report={"source_count":len(sources),"included_sources":sum(s["status"] in {"INCLUDED","INCLUDED_NO_RULE_MATCHED"} for s in sources),
            "excluded_sources":len(skipped),"unclassified_sources":sum(s["status"]=="UNCLASSIFIED_SOURCE" for s in sources),
            "sources_with_rules":len(populated),"sources_without_rule_match":sum(s["status"]=="INCLUDED_NO_RULE_MATCHED" for s in sources),
            "rule_count":len(rules),"rules_per_source":counts,"output":str(OUT.relative_to(ROOT))}
    (ROOT/"data"/"structured_asc_v1_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
