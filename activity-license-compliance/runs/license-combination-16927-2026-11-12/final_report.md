# 16927 数据集供应链 ASC 冲突检测实验报告

输入：`aggregate_all_16927/许可证组合统计.csv`。组合为检测单位，数量列仅用于加权，不是重复实验或额外法律证据。

共 413 组，代表 23112 条关系；复用历史成功结果 185 组，新增模型检测成功 107 组。

按有方向的上下游原文文件与哈希、调用方式和修改状态匹配历史结果；忽略仓库、标签大小写、数量。旧请求、响应及结果原样保存于 reused_originals；新请求使用当前 ASC、既有提示词和 Figure 10 全部12个案例。未使用离线判定引擎。

|处理状态|组合数|代表关系数|
|---|---:|---:|
|SUCCESS|292|16573|
|SKIPPED|115|6468|
|ERROR|6|71|

运行配置：GPT-6-luna；reasoning_effort=medium；每次最多 8,192 输出 token；3 路并发；每个新请求保留全部 12 个 Figure 10 案例。实际返回模型名保存在各结果 reported_model 字段。

## 冲突数量与类型统计

发现条数可包含同组的多个条款；组合数和关系数在每种状态内去重，各类型不能直接相加。

|类别|状态|发现条数|去重组合数|代表关系数|
|---|---|---:|---:|---:|
|License–License|CONDITIONS_INCLUDED|1|1|1|
|License–License|CONDITIONS_TO_INHERIT|5|5|9|
|License–License|CONSTRAINT_CONFLICT|0|0|0|
|License–License|NO_CONFLICT_IN_CHECKED_SCOPE|2|2|6|
|License–License|POTENTIAL_CONFLICT|1|1|1|
|License–License|SCOPE_REVIEW_REQUIRED|0|0|0|
|License–License|VIOLATION|0|0|0|
|License–Activity|CONSTRAINT_CONFLICT|0|0|0|
|License–Activity|NOT_APPLICABLE|20|19|453|
|License–Activity|OBLIGATIONS_OPEN|4|3|6|
|License–Activity|POTENTIAL_CONFLICT|0|0|0|
|License–Activity|SCOPE_REVIEW_REQUIRED|0|0|0|
|License–Activity|VIOLATION|0|0|0|

两类检测合并去重：确定冲突/违规 0 组（0 条代表关系）；潜在冲突 1 组（1 条代表关系）。分母仅为成功完成检测的 292 组、16573 条代表关系。

复用一致性审计：185 组的实际 ASC 条款、系统提示词、Figure 10 案例和冲突模式均与当前任务一致（忽略任务标识和标签大小写）；全局语料哈希不同来自其他新增许可证，未改变这些组的实际输入条款。

## 总体判定和义务集合

|总体状态|组合数|代表关系数|
|---|---:|---:|
|INCOMPLETE_ANALYSIS|13|1092|
|NO_CONFLICT_IN_CHECKED_SCOPE|20|1560|
|OBLIGATIONS_OPEN|259|13921|

### 组级汇总分类

分类由原始状态确定，不更改模型原始输出。义务履行未知本身不自动转为人工核查。

|分类|组合数|代表关系数|
|---|---:|---:|
|检查范围内未检出冲突（保留义务）|278|15480|
|需要核查或分析不完整|14|1093|

义务条目状态：{'UNKNOWN': 446}。UNKNOWN 不代表未履行或违规。
含人工核查项的成功组合：0。

## 案例分析

### 案例 1：BSD-3-Clause → CC-BY-4.0

远程服务调用（修改不适用）；代表 1 条关系；来源 REUSED；编号 `chain-0297-43a032907f77`；总体判定 OBLIGATIONS_OPEN。
- POTENTIAL_CONFLICT / Use：Use/两份原始材料；BSD 许可摘录允许使用并要求保留适用通知；CC-BY-4.0 授予对许可材料行使权利的许可，但要求遵守该许可条件。已知事实仅为远程服务调用及API关联，未证明两份许可约束同一对象或下游产品包含上游材料；若范围重合，保留通知与遵守CC许可条件可共同履行，未见相反要求。来源：两份本地许可文本的结构化条款摘录及可信链记录。
- 结果一致性检查：原始标签为 POTENTIAL_CONFLICT，但原始理由明确称两项条件可共同履行、未见相反要求。该项仅作为模型原始告警统计，不能写作已验证的许可证冲突；按现有理由应更接近条件继承/义务待履行。为忠实复用历史实验，本报告保留原始标签并单列此问题，未覆盖模型输出。
- 义务：若两许可共同适用于所使用的材料或产品，应保留BSD适用通知并遵守CC-BY-4.0许可条件。（UNKNOWN）
- 范围限制：条款结构化抽取标记为FIRST_PASS_REVIEW_REQUIRED；现有摘录仅涵盖许可授予/使用条件及BSD通知要求，未提供完整条件、例外或完整上下游范围映射。
- 范围限制：对象图确认API链接和远程调用，但依赖、打包、修改副本及合并产品关系均未知；因此不能将两份许可确定为共同约束同一对象。

### 案例 2：Apache-2.0 → BUSL-1.1

代码层面集成（修改：是）；代表 1 条关系；来源 NEW；编号 `chain-0293-c9823b13815c`；总体判定 OBLIGATIONS_OPEN。
未报告确定冲突或潜在冲突，作为无冲突对照案例。
- 义务：若scope_shared，则修改及相关使用须限于非生产用途，并符合当时适用的BUSL要求；若属生产用途，须有适用的Additional Use Grant明确允许。（UNKNOWN）
- 范围限制：BUSL摘录说明其许可范围为Licensed Work及其修改、衍生作品，但现有对象图未确定该BUSL范围是否与Apache上游对象重合；继承要求因此附带scope_shared条件。
- 范围限制：未提供BUSL具体版本对应的Additional Use Grant或实际用途性质，不能判断是否属于生产用途，也不能推定其已获生产使用许可。
- 实验口径：BUSL-1.1按用户指定的模板分析；上述用途限制作为条件义务保留，不要求补充许可参数，也不将参数未填写单独计为违规或人工核查项。

### 案例 3：AGPL-3.0 → MIT

代码层面集成（修改：是）；代表 1 条关系；来源 REUSED；编号 `chain-0359-5b89953c210c`；总体判定 OBLIGATIONS_OPEN。
未报告确定冲突或潜在冲突，作为无冲突对照案例。
- 义务：Include the copyright notice and permission notice in copies or substantial portions of the software.（UNKNOWN）
- 义务：If the modified version supports remote interaction and users interact with it remotely through a computer network, prominently offer those users access to the Corresponding Source at no charge.（UNKNOWN）
- 范围限制：上游 AGPL 第13条摘录针对被修改程序支持远程交互、且用户通过网络与该修改版本交互的情形。已知代码集成修改及远程调用，但现有事实不能确定下游是否向用户提供该修改版本作为网络服务，也不能确定条款的触发条件已成立；因此保留条件义务，不认定违反。
- 范围限制：MIT 摘录支持复制、修改的许可及通知条件；通知是否已随副本保留未知。对象图中的代码纳入不等于已发布打包物，未推定发生分发。
- 事实一致性检查：输入只确认代码集成及修改，未确认网络交互。原始理由中的“已知……远程调用”不受本行输入支持，不能作为已发生事实；AGPL网络源码义务只能保留为条件义务。原始结果不作覆盖修改。

## 研究范围与限制

本报告是 ASC 摘录与可信行为事实下的模型检测结果；没有人工金标准，不能据此计算精确率或召回率。跳过和响应失败不计为无冲突。历史复用沿用旧 ASC 版本和原始结论，不能表述为全部使用新增语料重新分析。分发、收费等未确认事实不会补写为已发生；可履行条件保留在义务集合。
