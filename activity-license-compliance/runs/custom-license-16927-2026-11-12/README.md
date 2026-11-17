# 自定义许可证实验产物索引

本目录与标准许可证组合实验独立，不合并计数。

- [结果报告](final_report.md)：方法、覆盖率、状态与冲突统计、三个案例及限制。
- [逐关系结果](custom_relationship_results.csv)：195条关系，保留源CSV记录位置与原文身份。
- [按仓库统计](custom_repository_statistics.csv)：56个仓库，成功/失败/跳过与冲突、义务数量。
- [冲突类型统计](custom_conflict_statistics.csv)：两类检测的原始状态计数。
- [核验记录](verification.json)：输入身份、原始响应重新解析及三类输出完整性。
- [运行摘要](summary.json)、[运行指纹](manifest.json)：机器可读汇总及输入/语料/配置哈希。
- `requests/`：113个完整请求，包含工具提示词及12个Figure 10案例。
- `responses/`：113个未改写的原始API响应，包括9个格式校验失败响应。
- `results/`：195个逐关系结果；104 SUCCESS、9 ERROR、82 SKIPPED。
- `three_outputs/license_license/`、`three_outputs/license_activity/`、`three_outputs/obligations/`：每个目录均195个文件；104个有效结果，其余91个为明确失败/跳过的空占位。文件数量不能当作成功检测数量。

ASC来源与提取记录见 `../custom-asc-2026-11-12/asc_report.md`；全部代码与复现命令见 `../../docs/CUSTOM_LICENSE_EXPERIMENT.md`。

本次113个可检测关系均已处理完毕，程序已退出；没有后台实验继续运行。9个格式失败保留原因并跳过，没有自动改写或伪造合规结果。
