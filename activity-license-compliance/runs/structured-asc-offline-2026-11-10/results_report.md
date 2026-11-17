# 供应链 ASC 冲突检查结果（离线）

运行方式：本机未配置 `LICENSE_API_KEY`，因此结果由离线引擎直接读取 `structured_asc_v1.json` 计算；没有调用 LLM，也不作为 GPT-6-luna 实验输出。Figure 10 的冲突模式按 `docs/FIGURE10_ASC.md` 作为提示/检查参考，实际判定引用本地 ASC 记录。

## 输入与覆盖

- 输入关系：17,289 行；排除 LGPL：25 行；实际分析：17,264 行。
- 检测中至少有一组 L-L 条款比较：0 行；至少有一条 L-A 条款检查：14,110 行。
- 唯一上下游许可原文配对：210。

## 整体判定

| 判定 | 供应链关系数 |
|---|---:|
| INCOMPLETE_ANALYSIS | 3237 |
| NO_CONFLICT_IN_CHECKED_SCOPE | 2549 |
| OBLIGATIONS_OPEN | 10387 |
| VIOLATION | 1091 |

## License-License 条款比较

| 条款比较结果 | 比较数 |
|---|---:|
| 无配对检查 | 0 |

已证实许可证冲突：**0**；作用范围未被输入确认，因此不会仅凭许可名称差异把潜在发现升格为已证实冲突。结构化条件模型提示的潜在冲突比较：**0**。

## License-Activity 检查

| 条款/行为状态 | 检查数 |
|---|---:|
| APPLICABILITY_UNKNOWN | 8806 |
| CONDITION_UNKNOWN | 1043 |
| OBLIGATION_OPEN | 36921 |
| SATISFIED_IN_MAPPED_SCOPE | 3118 |
| VIOLATION | 1091 |

明确行为违规：**1091**。

## 义务与限制集合

本轮共输出 **45,067** 条来自两侧许可证相关 ASC 条款的义务、条件许可前置项或禁止约束。每条记录保留活动、对象、触发式、履行状态、待定谓词及条款来源；同一关系的义务输出在 `obligations.jsonl`。

## 未匹配的许可标签

这些标签在本地原文/ASC 数据中没有可用映射，按未映射处理，不当作许可：

| 侧别与标签 | 行数 |
|---|---:|
| upstream:unknown | 2480 |
| downstream:unknown | 1554 |
| upstream:proprietary | 208 |
| upstream:other | 206 |
| downstream:LicenseRef-Custom | 148 |
| downstream:BUSL-1.1 | 96 |
| downstream:Elastic-2.0 | 67 |
| downstream:PolyForm-Noncommercial-1.0.0 | 55 |
| downstream:GPL-2.0 | 37 |
| downstream:Sustainable-Use | 28 |
| upstream:GPL-2.0 | 18 |
| downstream:Unlicense | 15 |
| upstream:Unlicense | 8 |
| downstream:LicenseRef-FIM-One | 7 |
| downstream:LicenseRef-doc2md-Desktop | 7 |

## 案例分析

### 输入第1行：agent-framework / gpt-4o

- 结论：`OBLIGATIONS_OPEN`；上下游原文：`['OpenAI.txt', 'LICENSE-MIT.txt']`。
- 完成 0 组同活动条款比较、1 项 license-activity 检查，汇总 1 项义务/限制。
- 潜在冲突 0，已证实行为违规 0。潜在冲突若为 0，表示本轮结构化条款中未发现可报告的相反约束，不等于完整许可兼容性证明。
### 输入第2行：agent-framework / claude-sonnet-4-5-20250929

- 结论：`OBLIGATIONS_OPEN`；上下游原文：`['ANTHROPIC.txt', 'LICENSE-MIT.txt']`。
- 完成 0 组同活动条款比较、2 项 license-activity 检查，汇总 2 项义务/限制。
- 潜在冲突 0，已证实行为违规 0。潜在冲突若为 0，表示本轮结构化条款中未发现可报告的相反约束，不等于完整许可兼容性证明。
### 输入第3行：agent-framework / nvidia/Nemotron-3-Embed-1B-BF16

- 结论：`INCOMPLETE_ANALYSIS`；上下游原文：`[None, 'LICENSE-MIT.txt']`。
- 完成 0 组同活动条款比较、0 项 license-activity 检查，汇总 0 项义务/限制。
- 潜在冲突 0，已证实行为违规 0。潜在冲突若为 0，表示本轮结构化条款中未发现可报告的相反约束，不等于完整许可兼容性证明。

## 可复现产物

逐关系三类原始结果分别见 `license_license.jsonl`、`license_activity.jsonl` 和 `obligations.jsonl`；合并索引见 `three_outputs_by_relation.jsonl`。运行指纹、输入/ASC 哈希及方法记于 `manifest.json`。

## 解释边界

本批是结构化 ASC 数据上的离线筛查，不是 LLM 实验或完整法律意见。ASC 首轮抽取仅覆盖命中的条款模式；原文范围、派生作品认定和未映射许可证可能改变结论。远程调用不自动证明权重转移、分发或组合产品；输入也没有收费、终端分发或义务履行证据。仅对输入和当前 ASC 覆盖范围作结论，不把“未发现已证实冲突/违规”表述为全量合规。
