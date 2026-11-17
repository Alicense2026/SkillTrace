# 供应链许可证冲突检测实验报告

- 运行模式：LIVE；模型：gpt-6-luna
- 输入记录：17289；本次选中：17264；已处理：34
- 成功：33；失败：1；LGPL排除：25
- ASC语料 SHA-256：e9112293cd1a04504609eb732817020d7d8606735db162a1f01aa7853b596857
- 方法：逐行输入可信供应链事实、匹配的许可证原文与结构化 ASC；每个请求注入 Figure 10 的 12 个案例和冲突模式。未调用离线冲突判定引擎。
- 状态说明：只有 SUCCESS 响应纳入统计；ERROR、未运行行不计为合规或无冲突。结构化 ASC 的原文匹配仍标记 FIRST_PASS_REVIEW_REQUIRED。

## 冲突数量与类型统计

| 输出类别 | 类型/状态 | 数量（成功响应） |
|---|---|---:|
| License-License | CONSTRAINT_CONFLICT | 0 |
| License-License | POTENTIAL_CONFLICT | 0 |
| License-License | CONDITIONS_TO_INHERIT | 0 |
| License-Activity | VIOLATION | 0 |
| License-Activity | POTENTIAL_CONFLICT | 0 |
| License-Activity | SCOPE_REVIEW_REQUIRED | 0 |
| 义务集合 | NOT_FULFILLED | 0 |
| 义务集合 | UNKNOWN | 28 |
| 义务集合 | FULFILLED | 0 |
| 总体判定 | INCOMPLETE_ANALYSIS | 9 |
| 总体判定 | NO_CONFLICT_IN_CHECKED_SCOPE | 8 |
| 总体判定 | OBLIGATIONS_OPEN | 16 |

## 冲突案例分析

当前成功结果中没有可供分析的已报告冲突；若成功结果数为零，本报告不构成检测结论。

## 完整性限制

本次未完成全量输入检查：处理 34 / 选中 17264 行，失败 1 行。未处理行不得解释为无冲突。
