# aggregate_all_10200 全量离线基线报告

## 实验性质与结论边界

本报告是 `activity_license_compliance` **离线规则引擎基线**，不是 GPT-6-luna 的模型实验。当前会话没有可用的 API 调用；因此没有模型生成的 ASC 抽取结果或模型原始响应。全量逐案离线输出、失败的单样本请求预览，以及数据/许可原文匹配索引均独立保存。该基线不能作为“GPT-6-luna 检测到零冲突”的论文结论。模型主实验需要通过真实模型接口运行并重新统计。

## 数据与处理

输入文件 `../aggregate_all_10200/result.csv` 共 **17,289** 行。按要求跳过资产许可或 GitHub 许可含 LGPL 的记录 **25** 行，纳入离线分析 **17,264** 条供应链关系。保留了输入原始行号。主要接入关系为远程 LINK 17,215 条（99.72%）和代码 BUNDLE 49 条（0.28%）。

离线规则引擎执行 276,224 次 activity 级 License-License 比较，即每条关系比较16类活动。比较复用本次输出目录中的 SQLite 结果缓存：命中 272,640 次、未命中 3,584 次、共存储 3,584 个不同结果，缓存命中率 **98.70%**。License-Behavior 检查覆盖同一批关系。

## 结果

| 逐案主状态 | 关系数 | 占纳入关系比例 |
|---|---:|---:|
| INCOMPLETE_ANALYSIS | 17,238 | 99.85% |
| OBLIGATIONS_OPEN | 26 | 0.15% |
| CONSTRAINT_CONFLICT | 0 | 0.00% |
| VIOLATION | 0 | 0.00% |
| NO_CONFLICT_IN_CHECKED_SCOPE | 0 | 0.00% |
| **合计** | **17,264** | **100.00%** |

| Activity 级比较结果 | 次数 | 占全部比较 |
|---|---:|---:|
| UNMAPPED_OR_UNSPECIFIED | 204,342 | 74.00% |
| SCOPE_REVIEW_REQUIRED；条件关系为 CONDITIONS_INCLUDED | 59,808 | 21.65% |
| SCOPE_REVIEW_REQUIRED；联合义务为 JOINT_CONDITIONS_TO_INHERIT | 12,074 | 4.37% |
| CONSTRAINT_CONFLICT / 不可满足约束 | 0 | 0.00% |
| **合计** | **276,224** | **100.00%** |

引擎报告 confirmed constraint conflicts **0**、potential license conflicts **0**、License-Behavior violations **0**。以上是当前部分规则与范围模型下的检测数；`UNMAPPED_OR_UNSPECIFIED` 占比较的74.00%，且所有关系都至少含一个人工审查项。因此这些零计数**不能解释为许可证总体兼容或已完成合规核验**。

引擎生成 active obligations 84 项，其中履行状态 UNKNOWN 的 84 项；条件义务 275,165 项。产生人工审查项的关系为 17,264/17,264（100%），按审查类型计数如下。该人工队列属于既有离线规则引擎，不是新 Prompt 的 `review_items` 结果。

| 离线审查类型 | 关系数 |
|---|---:|
| 规则覆盖缺口（RULE_COVERAGE） | 17,264 |
| 共同对象范围未确定（OBJECT_SCOPE） | 17,264 |
| 活动事实待定（ACTIVITY_FACTS） | 16,127 |
| 旧版条款抽象（CLAUSE_ANNOTATION） | 1,713 |
| 条件履行待定（FULFILLMENT） | 26 |

## 代表性关系分析

本次离线引擎没有输出已确认冲突，因此不能提供“已确认冲突案例”。以下三例用于说明为什么当前零冲突结果仍不能作为合规结论。

### 例1：Qwen/Qwen2.5-1.5B-Instruct（Apache-2.0）→ AI-Research-SKILLs（MIT）

源数据第7行。对 `Copy`，上游 Apache-2.0 在现有 ASC 规则中为 PERMITTED；下游 MIT 要求保留版权声明并附 MIT 许可证副本。符号比较结果为 CONDITIONS_INCLUDED，未发现不可共同满足条件。由于对象图的 `scope_shared` 为 null，离线引擎将结果标作 SCOPE_REVIEW_REQUIRED；全案仍因13个未映射活动槽与若干未查明事实进入 INCOMPLETE_ANALYSIS。该例是可履行条件的关系，不是冲突。

### 例2：sentence-transformers/all-MiniLM-L6-v2（Apache-2.0）→ beam（BSD-3-Clause）

源数据第24行。对 `Copy`，两侧现有规则均为 PERMITTED；比较结果 CONDITIONS_INCLUDED。引擎没有构造出互斥要求，但对象范围未知，其他活动也存在未映射规则，因此不判定为“已检查范围内无冲突”。这是“规则覆盖/对象范围限制”导致的不确定结果，不是一个冲突实例。

### 例3：gpt-4o（proprietary）→ agent-framework（MIT）

源数据第1行。上游标签为 proprietary，离线 ASC 规则库没有相应厂商条款映射；虽然本地已新增 OpenAI 原文，离线基线并未将该原文自动解析为 ASC。该关系有21个未映射规则槽，License-License 比较落入 UNMAPPED_OR_UNSPECIFIED，故无法支持冲突或兼容结论。此例说明应由模型或经审核的结构化提取补齐原文规则，再复用规则缓存运行比较。

## 许可证原文与 ASC 复用数据

本目录当前收录 40 份 `.txt` 许可证原文。按资产 URL/名称与标签匹配后，排除 LGPL 记录后，5620条 proprietary 资产记录中 5,412 条匹配到本地原文，208 条仍缺少本地原文。缺口集中在若干尚未加入原文目录的平台和无法确定具体版本的 Llama 资产；逐URL数量见 `license_source_match_index.json`。

`structured_asc_cache.json` 保存现有规则库中8种许可的 ASC 展开、规则版本、适用来源文件及其 SHA-256，状态明确标记为 `EXISTING_RULES_ONLY_NOT_NEW_LLM_EXTRACTION`。它可以帮助复用已有部分规则，但并不代表本次对40份原文全部完成结构化提取。新增原文与每条记录的匹配、哈希可在 `license_source_match_index.json` 追溯。

## 论文使用建议

可将本报告作为“离线规则引擎基线及覆盖率诊断”结果，不能将零冲突写成 GPT-6-luna 检测结论。主实验结果应在 API 可用后完成：对本地有原文的条款提取 ASC 并纳入可版本化缓存，排除 LGPL，针对17,264条记录逐条请求，保留原始响应，最后按**冲突条数、受影响供应链关系数、冲突活动/条款类型、规则覆盖、模型失败数**分别统计。两种计数（冲突 finding 与含冲突的关系）应分开展示。

## 产物

- `summary.json`、`analysis.json`、`decisions.json`：总体与逐案离线结果。
- `license_license.json`、`license_behavior.json`、`obligations_by_activity.json`、`review_queue.json`：模块输出。
- `pair-cache.sqlite3`：本次比较缓存，可用于后续复用。
- `license_source_match_index.json`：按记录匹配的许可证原文及来源哈希索引。
- `structured_asc_cache.json`：现有部分结构化 ASC 规则快照。
- `report.html`：浏览器查看的离线报告。
- `../luna-live-smoke/`：一次失败的真实请求预览/错误记录；没有模型响应体。
