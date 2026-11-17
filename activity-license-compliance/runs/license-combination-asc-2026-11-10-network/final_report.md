# 供应链许可证冲突检测实验报告

- 运行模式：LIVE；模型：gpt-6-luna
- 输入记录：414；本次选中：198；已处理：198
- 成功：185；失败：13；未知/未结构化许可证排除：203；LGPL排除：13
- 代表供应链关系：17289；成功覆盖：12509；未知/未结构化许可证跳过：4503；LGPL跳过：25
- ASC语料 SHA-256：e9112293cd1a04504609eb732817020d7d8606735db162a1f01aa7853b596857
- 方法：以许可证组合统计 CSV 为输入，对具有完整已纳入 ASC 原文的分组逐组分析；同组数量仅作代表关系数用于加权统计，不作为法律证据。每个请求注入 Figure 10 的 12 个案例和冲突模式。未调用离线冲突判定引擎或许可证对缓存。
- 状态说明：只有 SUCCESS 响应纳入统计；ERROR、未运行行不计为合规或无冲突。结构化 ASC 的原文匹配仍标记 FIRST_PASS_REVIEW_REQUIRED。

## 冲突数量与类型统计

| 输出类别 | 类型/状态 | 数量（成功响应） |
|---|---|---:|
| License-License | CONSTRAINT_CONFLICT | 0 |
| License-License | POTENTIAL_CONFLICT | 1 |
| License-License | CONDITIONS_TO_INHERIT | 4 |
| License-Activity | VIOLATION | 0 |
| License-Activity | POTENTIAL_CONFLICT | 0 |
| License-Activity | SCOPE_REVIEW_REQUIRED | 0 |
| 义务集合 | NOT_FULFILLED | 0 |
| 义务集合 | UNKNOWN | 245 |
| 义务集合 | FULFILLED | 0 |
| License-License其他状态 | NO_CONFLICT_IN_CHECKED_SCOPE | 2 |
| License-Activity其他状态 | NOT_APPLICABLE | 16 |
| 总体判定 | INCOMPLETE_ANALYSIS | 10 |
| 总体判定 | NO_CONFLICT_IN_CHECKED_SCOPE | 19 |
| 总体判定 | OBLIGATIONS_OPEN | 156 |

### 按代表供应链关系数加权

| 输出类别 | 类型/状态 | 关系数 |
|---|---|---:|
| License-License | CONSTRAINT_CONFLICT | 0 |
| License-License | POTENTIAL_CONFLICT | 1 |
| License-License | CONDITIONS_TO_INHERIT | 8 |
| License-Activity | VIOLATION | 0 |
| License-Activity | POTENTIAL_CONFLICT | 0 |
| License-Activity | SCOPE_REVIEW_REQUIRED | 0 |
| 义务集合 | NOT_FULFILLED | 0 |
| 义务集合 | UNKNOWN | 23500 |
| 义务集合 | FULFILLED | 0 |

## 冲突案例分析

### 案例 1：chain-0291-efa3b2f6e135（代表 1 条关系）
- **POTENTIAL_CONFLICT / Use**：Use/两份原始材料；BSD 许可摘录允许使用并要求保留适用通知；CC-BY-4.0 授予对许可材料行使权利的许可，但要求遵守该许可条件。已知事实仅为远程服务调用及API关联，未证明两份许可约束同一对象或下游产品包含上游材料；若范围重合，保留通知与遵守CC许可条件可共同履行，未见相反要求。来源：两份本地许可文本的结构化条款摘录及可信链记录。


## 完整性限制

本次未完成全量输入检查：处理 198 / 选中 198 行，失败 13 行。未处理行不得解释为无冲突。
