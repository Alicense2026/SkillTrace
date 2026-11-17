# v0.6 验证记录

日期：2026-11-10。执行环境：macOS、Python3.14；支持目标Python3.11+。所有以下验证均离线，未发送真实API请求。

## 已执行

| 检查 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -v` | 43项全部通过（v0.5阶段记录）；本次缓存新增后未重跑测试 |
| `python3 -m license_checker cases` | 12案例，40条ASC；源PDF SHA与资源一致 |
| 带SQLite缓存的回归审计（本轮首次建库后再运行一次） | 第二轮3456次命中、0次未命中；216条回归输入；215 INCOMPLETE_ANALYSIS、1 OBLIGATIONS_OPEN、4条已触发未确认履行义务、3456比较、0已证实行为违规；保持重构前判定 |
| `python3 -m license_checker experiment --input ../aggregate_all_10200/result.csv --output-dir runs/csv-preview --limit 3` | 3条DRY_RUN，无错误；每条请求包含完整12案例；提示字符分别67838、67832、67608 |
| Figure 10阅读 | 提取文本并渲染原始单页，视觉核对12行、操作、O/R项、频次；映射不宣称验证图中法律主张 |
| Responses接口模拟 | 认证头与路径、429重试、401不重试、不完整/拒绝/畸形响应、JSON校验、请求快照、成功断点续跑、配置隔离通过 |

## 数据来源与结果解释

原chain目录当前不存在，216条回归样本从前版 `output/normalized_cases.json` 保存的raw_record恢复，恢复快照的哈希记录于fixture_provenance。此次 `output/` 是该回归样本的重新运行结果。真实CSV前3条仅用于验证输入适配和请求构造，不代表大表全量模型实验。

Figure案例中每条ASC附合成相反条件，用于展示适用条件成立时的冲突。测试检查40对在触发范围内不可同时满足；这不意味着图中实际两许可证在所有场景下均不兼容。

## 未执行及后续工作

- 未在Windows主机执行PowerShell脚本；已提供无PS1依赖的直接Python命令。
- 未实测中转站 `/responses` 路由、模型授权、账单或真实模型输出质量；真实调用需在Windows按文档配置密钥并加Execute。
- 未用当前CSV完成全量LLM实验；未计算准确率、召回率等，没有把请求预览当作实验结论。
- 模型条款/特殊合同、许可全文和复杂范围推理仍不是完备规则库；Figure案例不自动填补这些缺口。

历史删除清单见 `cleanup_manifest.json`。保留原PDF、原DOCX、当前报告与必要回归输入。


## Prompt v2 本轮验证

- 运行完整测试套件：48项通过（包括原43项和新5项）。
- 40条原始ASC从18个模板可完整还原；32个合成对照场景按代码引擎核对预期结果；对照场景压缩可逆。
- 新义务合同支持触发式、true/false/null适用性和未知谓词；不要求为这些未知项生成review_items。
- 预览当前CSV前3条：56,636、56,630、56,598字符，完整保留12个Figure案例及全部对照模式，结果见runs/prompt-v2-final-preview。
- 未调用真实LLM。未声明冲突召回/精确率、人工项实际减少比例或模型输出稳定性已经测得。
