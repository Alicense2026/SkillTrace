# 冲突检测 Prompt v2：Figure10模式、正反对照、义务优先

本版已替换工具实际请求使用的系统提示，并调整案例组装和输出校验。目标是提高有依据的冲突检出能力与结果可复查性；尚未进行真实模型A/B实验，因此不报告检出率或准确率提升。

## 直接阅读和修改

| 文件 | 内容 |
|---|---|
| [llm_system.txt](../license_checker/resources/llm_system.txt) | 实际发送的完整系统Prompt，可直接人工修改 |
| [figure10_cases.json](../license_checker/resources/figure10_cases.json) | 原Figure10的12行、40条ASC映射及来源说明，保留原始存档 |
| [conflict_patterns.json](../license_checker/resources/conflict_patterns.json) | 9种图示模式+3种扩展，合计32个有预期结果的合成对照场景 |
| [casebook.py](../license_checker/llm/casebook.py) | 把40条映射归并为18个条款模板；对照场景通过规则引用去重 |
| [prompting.py](../license_checker/llm/prompting.py) | 将系统Prompt、案例、对照、合同与当前任务装成实际请求 |
| [schema.py](../license_checker/llm/schema.py) | 八个顶层输出字段；义务加入触发、适用性和未知谓词校验 |

## 为什么调整

旧版给每条图示规则重复添加相反条件，但没有充分展示“冲突”和“可补充履行”的区别，容易使模型从许可证名字直接推断冲突。旧提示还要求未知范围进入待审查，使人工任务过多。

新版采用固定步骤：对齐活动与对象 → 扫描Figure10模式 → 比较约束/检查行为 → 给出最小判据 → 合并条件义务。每次仍发送12行全部40条映射，通过引用模板完整还原；去掉频次对判断的影响，避免把高频组合当作当前样本标签。

系统Prompt要求结论依据为：`A/S；上游要求；下游相反要求或实际行为；触发事实；矛盾点；来源`。它要求简洁可复查的依据，不要求输出长篇思考过程。

## 案例展示方式

每个Figure行保存原始组合、操作和条款引用，模板保存ASC和来源边界。对照示例另设 `synthetic=true`，明确为教学场景；不得把相反条款冒充成图中另一许可证原文。

| 主要模式 | 检测重点 | 近邻对照 |
|---|---|---|
| O2 许可副本 | 要求保留副本与明确禁止保留冲突 | 下游未写这一要求时，通常应继承义务 |
| O3 材料链接 | 要求提供链接与明确禁止提供冲突 | 未知是否提供归义务；不把图中文字升级为完整源码披露 |
| O5 同许可/共享方式 | 明确相反的再许可要求 | 两个许可证名称不同本身不足以证明逻辑互斥 |
| O6 归属标识 | 必须展示与禁止展示冲突 | 展示情况未知归义务 |
| O7 限制传递 | 必须传递与明确剥除限制冲突 | 可以附加满足的限制归继承义务 |
| R1 用途政策 | 明确受禁止用途且实际实施 | 用途未分类归条件义务 |
| R2 非商业 | 商用事实已真且违反非商业约束 | 只知收费不能自动令商用为真 |
| R2 规模门槛 | 已达适用门槛且明确未取得必要授权 | 门槛未知归条件义务；提出申请不等于获准 |
| R4 输出训练 | 当前版本确有条款且所有限制条件成立 | 竞争性/输出来源未知保留条件；不同版本不能套用 |
| 扩展1 必须做/禁止做 | 同范围、已触发的强制行为与禁止冲突 | 明确不同对象/范围不冲突 |
| 扩展2 网络触发 | 原文明示的独立网络义务 | 单纯远程调用不等于满足全部触发条件 |
| 扩展3 OR授权路径 | 全部可用授权路径都失败才违规 | 满足一个完整路径，不要求其他路径同时成立 |

### 同一模式的三种结果（合成O2场景）

令 `p=已提供所需许可副本`，同一受约束对象为S：

```text
上游：<Distribute, S, CONDITIONALLY_PERMITTED(requires=p)>

对照1 下游：<Distribute, S, CONDITIONALLY_PERMITTED(requires=not p)>
→ 若相同范围且分发条件适用，p与not p不能同时成立：CONSTRAINT_CONFLICT。

对照2 下游：<Distribute, S, PERMITTED>
→ 下游没有明确排斥p；可以继承上游条件：CONDITIONS_TO_INHERIT + 保留许可副本义务。

对照3 已分发，但是否提供副本未知
→ fulfillment_status=UNKNOWN，归义务集合；不能当作已违规，review_items=[]。
```

此处的“下游禁止p”是假设条件，不是对Apache、MIT或任何图中另一许可证的事实描述。

## 判定与人工输出

| 情况 | 输出位置和结论 |
|---|---|
| 两条已确定适用的相反要求，无法共同满足 | `license_license_findings`：CONSTRAINT_CONFLICT |
| 已找到相反要求，但范围或触发尚未知 | 同上：POTENTIAL_CONFLICT；具体适用条件归义务集合 |
| 条件不包含，但仍能共同履行 | 同上：CONDITIONS_TO_INHERIT；上游条件归义务集合 |
| 活动已发生、条款适用、明确违反条件 | `license_behavior_findings`：VIOLATION；同时保留未履行义务 |
| 是否商用/分发/获准或履行情况未知 | `obligations`：条件、适用性、未知谓词；不生成重复人工任务 |
| 没有足够条款映射 | `limitations`：覆盖缺口；不制造“补文档”的法律义务 |
| 决定性条款歧义，无法用条件分支表达 | `review_items`：仅保留这一类必要人工核验 |

`review_items` 默认空数组，不设机械截断上限。减少复核任务通过重新组织输出实现，不以隐藏违规或抹去歧义实现。条件待定不等于已履行；明确违规不会仅被改写成待办。

整体状态采用固定优先级：VIOLATION → CONSTRAINT_CONFLICT → OBLIGATIONS_OPEN → INCOMPLETE_ANALYSIS → NO_CONFLICT_IN_CHECKED_SCOPE。后者仅指已检查范围，覆盖不足仍保留在limitations。

## 新义务输出示例

以下为合成样本；所有标识与引用在实际输出中必须取自当前task：

```json
{
  "activity": "Use",
  "subject": {"artifact": "example:upstream", "kind": "OriginalArtifact"},
  "requirement": "使用该受约束材料须满足非商业限制",
  "trigger": "activity:Use",
  "applicability": true,
  "fulfillment_status": "UNKNOWN",
  "unresolved_predicates": ["commercial_use"],
  "source_refs": ["rule:example"]
}
```

已发生Use而商用状态未知时，以上对象进入obligations，review_items可以为空。若Use本身未知，applicability为null。强制实施行为的trigger不应把该行为“已经发生”作为门槛。OR表达式保留一个候选路径集合，不拆成多个必须履行的事项。

八个顶层字段保持为case_id、asc_rules、license_license_findings、license_behavior_findings、obligations、review_items、overall_status、limitations。非空义务对象新增trigger、applicability、unresolved_predicates三个必填字段；解析器按 `llm-analysis-2.0` 校验。

## 结构化 ASC 与版本隔离

每条请求从 `data/structured_asc_v1.json` 按供应链两侧匹配许可证原文文件，再将匹配条款和原文摘录映射到当前关系对象。模型需基于原文核对候选 ASC，不能把第一轮抽取标记视为人工确认。每次请求携带 Figure 10 的 12 个案例及冲突模式。

逐行 LLM 实验不调用离线冲突判定引擎；模型独立输出 License-License、License-Activity 和义务集合。成功响应保存在 `responses/`，三类输出分别保存于 `three_outputs/`；统计报告只纳入成功响应。结构化 ASC、Figure 数据、系统 Prompt 和输出合同进入实验指纹，发生变化时必须使用新输出目录。

本次修改作用于LLM实验提示与结构校验；离线审计中的人工队列仍是代码引擎原有输出，不因编辑Prompt自动改变。

## 验证及运行

49项测试全部通过，其中包括40条ASC可还原、32个合成场景结果、结构化ASC请求注入、三类输出验证、密钥读取和服务错误脱敏。

当前CSV前3条的请求预览分别为56,636、56,630、56,598字符；原预览为67,838、67,832、67,608字符。首条减少约16.5%，同时增加32个对照场景。这里统计的是序列化请求字符，包含转义，不是token用量。

```powershell
py -3 -m license_checker experiment --input "..\aggregate_all_10200\result.csv" --output-dir "runs\prompt-v2-new" --limit 3
```

已保存的预览：[summary.json](../runs/prompt-v2-final-preview/summary.json)，具体请求在同目录requests下。没有调用付费API；32场景的逻辑检查不是LLM检出率评测。若要衡量改进，后续需在同一人工标注样本上比较旧/新Prompt的冲突召回、误报、重复义务及人工项数量，并固定模型与参数。
