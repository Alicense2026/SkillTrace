# 自定义许可证供应链 ASC 实验报告

本报告按 LicenseRef 标签单独统计自定义许可证关系，不与此前组合实验混合计数。标签表示数据集分类，不保证每份原文均为实质非标准条款。输入为 `aggregate_all_16927/result.csv`，筛选任一侧含 LicenseRef 的关系；按原始明细行检测，保留原始 CSV 行号。不同仓库的 LicenseRef-Custom 不共享许可身份。

共 195 条关系、56 个仓库；处理状态：{'SKIPPED': 82, 'SUCCESS': 104, 'ERROR': 9}。

## 方法与来源

根据 `_licenseref_full/licenseref_full.json` 的完整仓库名、许可证标签及原文 SHA-256 精确匹配；不按仓库短名推断 fork 或继承关系。相同原文字节可复用 ASC，但每条供应链关系均保留自己的仓库、资产和行为证据。新增提取使用 GPT-6-luna，保留原文行号、分块请求、原始响应和覆盖说明；只有完成的来源被纳入。新冲突请求使用工具现有提示词及 Figure 10 全部12个案例，不运行离线判定引擎。

模型：GPT-6-luna，reasoning_effort=medium；输出上限8192 token。未确认分发、商用收费、网络提供修改版本等事实不会补写；可履行条件放入义务集合。

## 冲突类型统计

同一关系可能产生多项条款发现；关系数在各状态内去重，类型间不可直接相加。

|类别|状态|发现条数|关系数|仓库数|
|---|---|---:|---:|---:|
|License-License|CONSTRAINT_CONFLICT|0|0|0|
|License-License|POTENTIAL_CONFLICT|0|0|0|
|License-License|SCOPE_REVIEW_REQUIRED|0|0|0|
|License-License|VIOLATION|0|0|0|
|License-Activity|CONSTRAINT_CONFLICT|0|0|0|
|License-Activity|OBLIGATIONS_OPEN|1|1|1|
|License-Activity|POTENTIAL_CONFLICT|0|0|0|
|License-Activity|SCOPE_REVIEW_REQUIRED|0|0|0|
|License-Activity|VIOLATION|0|0|0|

## 总体状态与义务

|总体状态|关系数|
|---|---:|
|INCOMPLETE_ANALYSIS|6|
|NO_CONFLICT_IN_CHECKED_SCOPE|7|
|OBLIGATIONS_OPEN|91|

## 处理覆盖率

|处理结果|关系数|占筛选关系比例|
|---|---:|---:|
|SUCCESS|104|53.33%|
|ERROR|9|4.62%|
|SKIPPED|82|42.05%|

|调用方式|筛选关系|成功|失败|跳过|
|---|---:|---:|---:|---:|
|远程服务调用|195|104|9|82|

检测告警数仅统计成功响应；没有告警不等于全部条款完整覆盖。若成功样本均为远程调用，结论不能外推到代码集成、修改或分发。分析不完整的关系及跳过、失败关系均不作为确定的无冲突样本。

义务条目共 186 条；包含显式人工核查项的关系 0 条。UNKNOWN 履行状态不等同于未履行。

## 案例分析

### 案例 1：https://github.com/nirdiamant/agents-towards-production

原始CSV第 893 行，`chain-0892-12efd82cbf53`；LicenseRef-Custom / proprietary；远程服务调用；总体状态 INCOMPLETE_ANALYSIS。
未报告冲突告警，作为检测范围和义务继承的对照案例，不作为冲突正例。
- 范围限制：已确认的活动是通过 API 远程调用并使用上游 gpt-4o；这不证明下游仓库内容被使用、修改、分发或与模型权重合并。
- 范围限制：下游 LicenseRef-Custom 摘录仅授予并限制对仓库 Licensed Material 的使用等权利，未证明该材料就是本次 API 调用所使用的对象，因此不能将其非商业、署名或商业授权条款套用于本次远程调用。

### 案例 2：https://github.com/YaoApp/yao

原始CSV第 908 行，`chain-0907-84e65d764dde`；LicenseRef-Custom / proprietary；远程服务调用；总体状态 OBLIGATIONS_OPEN。
未报告冲突告警，作为检测范围和义务继承的对照案例，不作为冲突正例。
- 义务：使用下游Yao Engine时，保留品牌和版权信息（除非已获指定授权），并维持证书验证系统；若组织达到任一企业门槛，还须取得Infinite Wisdom Software商业许可。（UNKNOWN）
- 范围限制：OpenAI.txt仅匹配到客户向OpenAI付款的条款摘录，未提供适用于本次API调用的其他条款；不能据此推断其许可或使用条件。
- 范围限制：下游许可证摘录称其余权利和限制参照Apache License 2.0，但未提供相应文本；未对未映射条款作结论。

### 案例 3：https://github.com/nanbingxyz/5ire

原始CSV第 2251 行，`chain-2250-db4a601ce7ac`；LicenseRef-Custom / mit；远程服务调用；总体状态 INCOMPLETE_ANALYSIS。
未报告冲突告警，作为检测范围和义务继承的对照案例，不作为冲突正例。
- 范围限制：可信记录确认的是对 Xenova/bge-m3 的远程调用及 API 链接；未证明下游复制、修改、分发或再许可该模型，故不触发 MIT 关于副本/分发的通知义务。
- 范围限制：MIT 摘录将版权及许可通知置于副本或实质部分中；结构化 Use 条款将其概括为使用条件，但现有事实未证明发生复制，不能据此认定未履行或形成冲突。

## 缺口与解释边界

跳过原因：{'MISSING_REPOSITORY_MAPPING': 31, 'NO_USABLE_ASC': 51}。格式/请求失败：{'Invalid obligation values': 7, 'Invalid obligation applicability': 1, 'Unknown evidence reference': 1}。

缺失映射、空原文、无有效 ASC、未知上游许可证及响应失败均不计为无冲突。仅提供名称或外部协议引用的原文不被扩写为完整许可证。结果属于基于给定材料的模型检测，未经人工金标准验证，不报告精确率或召回率。
