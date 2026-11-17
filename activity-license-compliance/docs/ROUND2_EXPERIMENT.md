# 第二轮修复与补充实验

执行脚本：`scripts/run_supplement_round2.py`；核对脚本：`scripts/verify_supplement_round2.py`。
本轮固定输出目录：`runs/supplement-repair-2026-11-12-round2/`。历史实验与论文冻结统计不覆盖。

## 运行

在工具目录执行：

```sh
python3 scripts/run_supplement_round2.py --phase prepare
python3 scripts/run_supplement_round2.py --phase execute
python3 scripts/verify_supplement_round2.py
```

网络调用复用 `configs/experiment.toml` 和已有密钥读取机制，不在请求文件中保存 Authorization。`prepare` 只读取工作簿、导出完整原文、保存输入快照和清单；`execute` 才调用 API 并更新自定义映射及 ASC 语料。`report` 可单独重建统计，不发送请求。

## 范围与方法

- **修复组**：旧组合实验的6个失败任务及旧自定义实验的9个失败任务，合计80条供应链关系。保留原始任务、响应和错误，将字段诊断与原输出反馈给模型；原任务的12个 Figure 10案例、事实与ASC保持不变。第一轮反馈仍不通过校验时最多再反馈一次；网络失败记录后继续其他任务。
- **补充组**：工作簿的8个精确仓库映射、FIM One、RNA-TPSAL，以及数据集中的3个 Cognis 仓库。Cognis→COCL 使用本次用户明确确认的对应关系。只对数据集精确仓库名匹配，不对无关 LicenseRef-Custom 共享授权。共43条原始关系，保留CSV记录位置。
- **ASC**：复用已有 COCL；10份新增原文使用既有逐行来源提取提示词和校验器。只规范化新增规则，保留所有原始响应及规范化前后记录。新旧原文分别保留，不覆盖原有仅含名称/元数据的文本。
- **冲突检测**：使用已有 `build_request`，包括完整12个 Figure 10案例；结果通过原有严格校验器后才记SUCCESS。没有运行离线冲突判定引擎。
- **统计**：组任务按关系权重展开，补充任务按单行计数。全量合并优先采用补充结果，其次修复结果，再保留历史结果。未知许可证继续跳过；格式正确、未检出冲突、已证明合规是不同概念。

## 主要文件

|文件/目录|作用|
|---|---|
|`manifest.json`|输入哈希、映射、受影响CSV行、15个修复任务及权重|
|`before_*.json`、`baseline_ledger.json`|修改前语料、映射与全量统计快照|
|`asc/requests`、`asc/responses`、`asc/validated`|新增原文的模型提取输入、原始输出与通过校验的条款|
|`asc/by_license`|按原文SHA256汇总的新增/复用ASC|
|`asc/normalization_audit.json`|新增规则的既有表示规范化差异|
|`repair/original_outputs`|旧错误响应、旧请求、错误诊断的完整副本|
|`repair/requests`、`repair/responses`|每次修复尝试的输入与原始响应|
|`supplement/requests`、`supplement/responses`|补充关系逐行检测的输入与原始响应|
|两组的`results`|执行状态、严格校验后的分析、模型返回名称与使用量|
|两组的`three_outputs`|许可证—许可证、许可证—行为、义务集合；跳过/失败占位文件的output为null|
|`全部关系执行明细.csv`|23206条关系逐行合并结果，不重复累计历史失败|
|`第二轮任务明细.csv`|任务级处理状态、关系权重、义务数量|
|`修复前后差异.csv`|总体判定、义务数量、ASC及发现数量的前后变化|
|`冲突类型统计.csv`|任务级和关系级的类型统计；同一关系可落入多个类型|
|`补充仓库与原文映射.csv`|13个仓库的原文、ASC和检测覆盖|
|`verification.json`|原始响应重解析、三类输出一致性、源文件哈希和旧ASC不变性核验|

## 断点约束

已保存的任务结果（含ERROR和SKIPPED）不自动覆盖，成功提取分块按请求哈希复用。再次执行本轮不会无限重试失败任务。若需更换输入、修改提示词或开启第三轮，应新建版本目录，并保存新的来源快照；不要删除旧失败响应来伪装首次成功。当前固定目录主要服务本次实验，不是任意输入的通用运行器。
