# 运行产物索引

本次输入为许可证组合统计.csv：413组、23,112条代表关系。已结束，未留下运行中的实验进程。

- final_report.md：结果统计、三例分析、实验口径与局限。
- results_overview.csv：413组逐行状态及跳过/失败原因。
- conflict_statistics.csv / .json：按类别、状态统计发现条数、去重组合数和关系数。
- results：292组成功、115组跳过、6组失败的完整记录。
- three_outputs：license_license、license_activity、obligations三个子目录各413个文件；其中292个为成功内容、121个为明确标记状态的空占位，不能把占位计为无冲突。
- responses：113次新增检测的原始响应，包括6次格式校验失败的响应。
- reused_originals：历史复用请求、响应、结果原样保存；results中的reference_remapping记录新旧标识对应。
- requests：当前组的任务构造；其中185组仅用于匹配/映射，并未发送API请求，其真实旧请求位于reused_originals。
- prior_failures：重试前的沙箱网络错误记录，不计为最终新增检测结果。
- verification.json、reuse_audit.json、reuse_effective_asc_audit.json、reuse_prompt_audit.json：数量、输出合同、历史内容及复用依据一致性核验。
- qualitative_review_notes.json：两处已识别的原始输出一致性问题，保留模型输出并注明研究解释。

检测成功只表示响应通过输出合同，不能直接等同于完整合规结论。13组成功响应仍报告INCOMPLETE_ANALYSIS，报告已单列。
