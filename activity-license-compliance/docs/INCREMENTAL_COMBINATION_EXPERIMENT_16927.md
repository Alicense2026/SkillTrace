# 16927 组合增量实验

## 输入和方法

输入固定为 `aggregate_all_16927/许可证组合统计.csv`（413 组、23,112 条代表关系），不直接读取明细 `result.csv`。运行入口是 `scripts/run_combination_incremental.py`。

调用现有 `prepare_llm_case`、`build_request`、Responses 客户端和 `parse_result`；新请求携带完整 Figure 10 的 12 个案例、冲突模式、相关 ASC 条款及输出合同。模型配置来自 `configs/experiment.toml`，密钥从本地配置读取，不写入运行记录。本次本地输入长度限制设为 400,000 字符，实际请求不裁剪条款或示例。

## 复用口径

历史目录：`runs/license-combination-asc-2026-11-10-network`。仅复用通过输出合同校验的 SUCCESS 结果，不复用历史网络错误或格式错误。

匹配键为：有方向的上游和下游原文文件名、各原文 SHA-256、调用方式及代码修改状态。许可证版本须解析为相同原文；调用方式或修改状态不同不可复用。仓库名称、输入位置、标签大小写和组合数量不影响结果匹配。

原始请求、响应和结果逐字节复制至 `reused_originals/<历史case_id>/`。供新表使用的派生结果只替换 case_id、对象标识、证据引用及组合权重，保留原结论。`reference_remapping` 记录替换规则，`original_asc_sha256` 保留原语料版本；`reuse_audit.json` 验证原始记录一致性。`requests/` 中复用组的文件是用于匹配和映射的当前任务，不表示已发送请求，实际历史请求见 `reused_originals`。

用户要求复用历史已检测关系，因此旧结论不会因为本次语料新增而自动重跑。研究报告必须区分旧结论复用与新模型调用，不能把全部结果描述为采用新增 ASC 统一重测。

## 输出和统计

- `results/`：每组的处理状态、来源、权重和完整结构化结果。
- `responses/`：新增调用的原始模型响应，含格式校验失败响应。
- `three_outputs/license_license/`：许可证—许可证检测。
- `three_outputs/license_activity/`：许可证—行为检测。
- `three_outputs/obligations/`：义务集合。
- `prior_failures/`：沙箱网络失败等被显式重试前的记录。
- `results_overview.csv`：所有组合的处理状态索引。
- `conflict_statistics.json`、`summary.json`、`final_report.md`：统计及报告。

跳过和失败组保留带状态的三类输出占位记录（output=null），不伪造模型结果。无 ASC 原文映射的组合跳过；UNKNOWN 履行状态不能解释为未履行。冲突统计同时报告条款发现次数、去重组合数和组合代表关系数，避免把同组多条发现当成多条供应链。

## 运行

```sh
python3 scripts/run_combination_incremental.py
python3 scripts/run_combination_incremental.py --execute
```

第一条准备请求与复用结果，不调用 API。第二条执行未完成的新组；单行错误保存后继续，已有成功和已记录错误默认不重试。若确认网络条件已改变，可显式使用 `--retry-network-errors` 重试网络错误；原失败记录会归档。不要同时运行多个实例。

新增校验位于 `tests/test_incremental_reuse.py`，涵盖方向、原文哈希、集成方式、无损标识映射和新增平台标题适配。
