# 新增许可证 ASC 结构化：2026-11-12

本轮处理新加入“许可证原文”目录的 17 份文件（16 个 TXT、1 个 Markdown），由配置中的 GPT-6-luna 对 30 个覆盖全文的重叠文本块提取。原始模型输出、请求、校验数据和修订记录均保留。本轮只做条款结构化，没有执行供应链冲突检测。

新增 1,367 条展开 ASC，保留旧有 1,104 条记录不变，合计 2,471 条。来源库现有 57 份文件：56 份纳入，1 份 LGPL 按此前要求排除。ASC 数量是活动/对象展开记录数，不等于独立法律条款数。

## 输出文件

- `data/structured_asc_v1.json`：已合并、供后续提示词读取的完整 ASC 数据。
- `data/structured_asc_v1_summary.json`：最新覆盖统计。
- `runs/asc-extension-2026-11-12/new_rules.json`：仅新增来源、ASC 及逐文本块覆盖说明。
- `runs/asc-extension-2026-11-12/by_license/`：逐许可证的独立 JSON 文件，含规则与范围说明。
- `runs/asc-extension-2026-11-12/requests/`、`responses/`、`validated/`：提取请求、原始响应与结构校验后的条款。
- `runs/asc-extension-2026-11-12/before_extension.json`：本轮开始前的完整 ASC 快照。
- `runs/asc-extension-2026-11-12/new_rules_before_review.json`：规范化与重点审阅前的新增记录。
- `runs/asc-extension-2026-11-12/normalization_audit.json`、`activity_normalizations.json`：可追溯的形式化修订和活动名转换。

## 每份原文的记录数

| 原文 | ASC 条数 |
|---|---:|
| BUSL-1.1.txt | 74 |
| CC-BY-NC-ND-4.0.txt | 37 |
| CDLA-Permissive-2.0.txt | 13 |
| COCL-1.0.txt | 97 |
| Cohere+Legal+Terms+%26amp%3Bamp%3B+Policies.txt | 158 |
| ELASTIC-LICENSE-2.0.txt | 86 |
| GPL-2.0-or-later.txt | 79 |
| Kimi+%E5%BC%80%E6%94%BE%E5%B9%B3%E5%8F%B0%E6%9C%8D%E5%8A%A1%E5%8D%8F%E8%AE%AE.txt | 24 |
| MulanPSL-2.0.txt | 19 |
| ODC-By-1.0.txt | 89 |
| PolyForm+Internal+Use+1.0.0.txt | 77 |
| PolyForm+NonCommercial+1.0.0.txt | 150 |
| PolyForm+Perimeter+1.0.1.txt | 93 |
| PolyForm+Small+Business+1.0.0.txt | 58 |
| Sustainable+Use+License+v1.0.md | 70 |
| blockscout.txt | 26 |
| 百度智能云.txt | 217 |

## 表示与校验

每条记录的 ASC 仍严格使用 A、S、C 三元组。A 使用既有活动词表；S 使用四种对象类型；C 使用七种模态，并在 when 中记录适用触发条件、requires 中记录条件或义务内容。condition_explanation 解释符号化条件。主体角色、适用产品/协议范围及原文证据保存在三元组之外。

已逐条校验新增 ASC 形状、规范活动名、条件表达式、原文摘录与行号的一致性、来源 SHA-256 和新增规则 ID 唯一性；已验证旧来源与旧规则和快照完全相同。文本块覆盖所有源文件行，不代表所有法律意义均已穷尽提取。

针对模型输出进行了记录在案的形式化修订：有条件的禁止使用 CONDITIONALLY_PROHIBITED，避免 requires 被绝对禁止语义忽略；将已写在 scope_note 中的义务内容绑定到 C.requires 的命名谓词；核对 CC-BY-NC-ND 的“可非商业改编但不可分享改编材料”、COCL 商用触发条件及 Kimi 标识修改限制。商标权未授予不被等同于禁止一切软件使用。该审阅由本会话助手完成，不宣称经过人工法律审核。

百度文本的一块初次两次响应使用规范外活动 Deploy/Install；保留两次原始输出，最终将第二次响应的 Install 依原文“安装、使用”归入 Use 并去重后通过校验。30 个文本块均获得有效结构化结果。

## 适用范围与仍存边界

- Blockscout：新增原文为服务 Terms of Use。已提取服务使用约束，但未将其自动绑定到 GitHub 的 LicenseRef-Blockscout；仍需要证明该文本确为仓库软件许可，或补对应仓库 LICENSE。
- Cohere：同一文件包含 Client License Agreement、North 产品附表和 Commercial SaaS Agreement。全部已提取；直接 API 匹配仅选 Commercial SaaS Agreement（当前原文第 179 行起）的 ASC，避免伙伴安装产品的内部使用限制误用于 API。
- 百度：所给文件包含用户服务协议与线上订购协议。保留范围及条件；这些原文不自动代表已经包含所有千帆/文心产品专项协议。
- BUSL：变更日期、Change License、Additional Use Grant 等项目参数仍须来自实际项目，未擅自填入。
- GPL-2.0 与 GPL-2.0-or-later：共用所给 GPL v2 文本来源，输入标签仍保留；是否允许后续版本不能仅由文件名推断。
- Gemma 主许可及先前未识别的自定义项目原文未在这 17 份新增文件中出现，本轮不假定这些缺口已补齐。
- 旧语料保持原样，未在本轮重新审查其全部条款。新增记录的 LLM_EXTRACTED_SOURCE_VALIDATED 表示来源与格式校验，不是法律结论认证。

## 代码与复现

- `scripts/extend_asc_corpus.py`：识别新增 TXT/MD、分块提取、保存原始输出、校验并增量合并。已有文件内容改变时停止，避免覆盖历史身份。
- `scripts/finalize_asc_extension.py`：针对本次快照的确定性规范化与重点条款修订，保存审计记录。
- `license_checker/llm/license_sources.py`：新增标签/平台映射、Markdown 来源清单、Cohere API 章节范围。
- `license_checker/llm/prompting.py`：将条件解释传给后续判断，按来源章节范围选择 ASC。
- `scripts/build_asc_corpus.py`：发现增量数据时拒绝用旧稀疏模板覆盖。

后续新增原文可运行 `python3 scripts/extend_asc_corpus.py --execute`。本次已有数据的审阅重现使用 `python3 scripts/finalize_asc_extension.py`；它固定针对 2026-11-12 快照，不应当作为未来其他批次的通用覆盖脚本。


## 验证补充

58 项单元测试通过。对 Cohere、百度、Kimi 与 MIT 的代表性提示词做了不联网构造检查；共享条款的条件解释只保存一次，全部 ASC 项仍保留。长许可证组合可能仍触发既有输入长度限制，后续全量实验应先预检；程序不会静默删掉条款。
