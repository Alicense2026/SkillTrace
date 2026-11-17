# 当前许可证原文缺口清单

核对日期：2026-11-11。范围：`aggregate_all_10200/许可证组合统计.csv` 的 414 组、17,289 条代表关系；核对 `activity_license_compliance/许可证原文/`、`data/structured_asc_v1.json` 及当前匹配代码。

本清单为本地文件和映射覆盖审计，没有下载新文本，也没有修改映射、ASC 或实验结果。原文是否存在与原文完整性分别说明；不代表对所有现有文件进行了法律完整性审查。

统计口径：同一许可证标签在一行任一侧出现，该行只计一次；数量取输入“数量”列。同一行可能同时缺两侧许可证，因此跨表、跨许可证的数量不可直接相加。表格统计包含用户已排除的 LGPL 行；本次实验实际跳过记录另见下文。

## 需要补充的具名许可证原文

| 输入标签 | 涉及组合组数 | 代表关系数 | 缺口/处理方式 |
|---|---:|---:|---|
| BUSL-1.1 | 13 | 96 | Business Source License 1.1；还需具体项目的授权参数、额外使用许可及变更日期等。 |
| Elastic-2.0 | 17 | 67 | Elastic License 2.0。 |
| PolyForm-Noncommercial-1.0.0 | 14 | 55 | PolyForm Noncommercial License 1.0.0。 |
| GPL-2.0 | 13 | 52 | GNU GPL version 2；不能用现有 GPL-3.0 原文替代。 |
| GPL-2.0-or-later | 2 | 2 | GPL version 2 原文，并保留项目允许后续版本的授权声明；与 GPL-2.0 共用基础原文，但标签含义不应合并。 |
| Sustainable-Use | 8 | 28 | 对应项目适用的 Sustainable Use License，核对具体版本及附加条款。 |
| PolyForm-Small-Business-1.0.0 | 5 | 5 | PolyForm Small Business License 1.0.0。 |
| CC-BY-NC-ND-4.0 | 3 | 4 | CC Attribution-NonCommercial-NoDerivatives 4.0 的完整法律文本。 |
| PolyForm-Internal-Use-1.0.0 | 4 | 4 | PolyForm Internal Use License 1.0.0。 |
| PolyForm-Perimeter-1.0.1 | 4 | 4 | PolyForm Perimeter License 1.0.1。 |
| CDLA-Permissive-2.0 | 2 | 2 | Community Data License Agreement – Permissive 2.0。 |
| MulanPSL-2.0 | 2 | 2 | 木兰宽松许可证第 2 版。 |
| odc-by | 2 | 2 | 对应资产所用的 Open Data Commons Attribution License；当前标签未注明版本。 |
| gemma | 3 | 3 | 缺主许可 Gemma Terms of Use；现有 Gemma Prohibited Use Policy.txt 仅是禁止用途政策，虽已结构化，不能视为主许可齐全。 |

## 需要补充的平台服务条款

| 输入标签 | 涉及组合组数 | 代表关系数 | 缺口/处理方式 |
|---|---:|---:|---|
| Proprietary（docs.cohere.com；本地原文未匹配） | 9 | 78 | Cohere：补对应服务/API 的适用条款；本地未发现对应原文。 |
| Proprietary（platform.moonshot.cn；本地原文未匹配） | 11 | 74 | Moonshot/月之暗面：补对应开放平台/API 的适用协议。 |
| Proprietary（cloud.baidu.com；本地原文未匹配） | 3 | 24 | 百度智能云：补对应资产服务的适用协议；不能仅凭域名确定具体产品条款。 |

## 需要先恢复许可证身份或项目原文

| 输入标签 | 涉及组合组数 | 代表关系数 | 缺口/处理方式 |
|---|---:|---:|---|
| LicenseRef-Custom | 15 | 148 | 自定义许可证占位标签；可能对应多个不同项目，不能用一份通用原文覆盖全部。 |
| LicenseRef-doc2md-Desktop | 5 | 7 | 需要 doc2md Desktop 对应项目的实际许可文件及版本。 |
| LicenseRef-FIM-One | 5 | 7 | 需要 FIM-One 对应项目的实际许可文件及版本。 |
| LicenseRef-RNA-TPSAL-1.0 | 1 | 1 | 需要对应项目的 RNA-TPSAL-1.0 原文。 |
| unknown | 69 | 3727 | 许可证身份未识别；需要回溯具体仓库/资产，无法据此标签确定该下载哪份许可。 |
| other | 9 | 206 | 未明确具体许可证；需要回溯资产许可信息。 |

## 已有文本但匹配或完整性仍需处理

| 输入标签 | 涉及组合组数 | 代表关系数 | 缺口/处理方式 |
|---|---:|---:|---|
| creativeml-openrail-m | 1 | 3 | 已有 CreativeML-OpenRAIL-M.txt，且 ASC 状态为 INCLUDED；匹配表仅登记 openrail-m，未登记输入中的这个别名。属于映射缺口。 |
| openrail++ | 1 | 1 | 已有 openRAIL++-M License.txt，且已结构化；匹配表仅登记 openrail++-m。文本含 [year]、[authors]、[project/org name] 等占位符，是模板，还需核实具体资产采用的最终版本。 |

## 按当前实验要求跳过，不列入优先补充

| 输入标签 | 涉及组合组数 | 代表关系数 | 缺口/处理方式 |
|---|---:|---:|---|
| Unlicense | 12 | 23 | 本地未发现 Unlicense 原文；按用户本次实验要求跳过。此标签有独立含义，不能自动与 unknown 等同。 |
| LGPL-3.0 | 11 | 20 | 本地已有 LGPL-3.0.txt，ASC 标记 EXCLUDED_BY_USER；不需补充或分析。 |
| LGPL-2.1 | 2 | 5 | 本地未发现该版本原文，但用户已排除所有 LGPL，当前不需补充。 |

## 与上一轮实验的对应关系

上述缺口与排除规则覆盖上一轮全部 203 个“未知/未结构化许可证”跳过组，合计 4,503 条代表关系；另有 13 个 LGPL 组、25 条关系按用户要求排除。203 组并非都缺原文，包含标签未识别、映射缺口和主许可未齐全等情况。

当前原文文件夹有 40 个 TXT 文件，全部已有 ASC 来源记录：39 个 INCLUDED，1 个 LGPL-3.0 为 EXCLUDED_BY_USER。未发现“原文已经放入该文件夹、但完全没有 ASC 来源记录”的新增文件。

OpenAI、Anthropic/Claude、DeepSeek、Gemini、阿里云百炼、智谱和 Mistral 均已有对应原文与 ASC；Llama 2、3、3.1、3.2、3.3、4 也均已有原文与 ASC。输入中 6 个 Llama 版本未识别组、32 条代表关系已按用户要求映射至 Llama 4，不列为缺失。

上一轮的 13 个执行失败组属于请求超时或输出格式校验失败，不能据此推断许可证原文缺失。

## 回溯索引

以下为输入 CSV 的数据行序号（不含表头），用于精确定位；不重新读取 result.csv 作为本次统计输入。

- BUSL-1.1：56, 75, 79, 88, 106, 114, 225, 226, 227, 287, 288, 289, 290。
- Elastic-2.0：70, 107, 118, 125, 126, 152, 238, 239, 240, 309, 310, 311, 312, 313, 314, 315, 316。
- PolyForm-Noncommercial-1.0.0：89, 90, 130, 159, 172, 207, 208, 378, 379, 380, 381, 382, 383, 384。
- GPL-2.0：93, 119, 121, 127, 134, 189, 241, 317, 318, 319, 320, 321, 398。
- GPL-2.0-or-later：322, 323。
- Sustainable-Use：112, 131, 141, 256, 394, 395, 396, 397。
- PolyForm-Small-Business-1.0.0：389, 390, 391, 392, 393。
- CC-BY-NC-ND-4.0：231, 298, 299。
- PolyForm-Internal-Use-1.0.0：374, 375, 376, 377。
- PolyForm-Perimeter-1.0.1：385, 386, 387, 388。
- CDLA-Permissive-2.0：307, 308。
- MulanPSL-2.0：372, 373。
- odc-by：273, 362。
- gemma：271, 283, 360。
- Proprietary（docs.cohere.com；本地原文未匹配）：45, 63, 103, 143, 167, 315, 344, 352, 411。
- Proprietary（platform.moonshot.cn；本地原文未匹配）：40, 69, 176, 216, 290, 295, 316, 320, 330, 382, 392。
- Proprietary（cloud.baidu.com；本地原文未匹配）：86, 129, 179。
- LicenseRef-Custom：42, 49, 62, 65, 77, 109, 196, 249, 250, 251, 340, 341, 342, 343, 344。
- LicenseRef-doc2md-Desktop：197, 345, 346, 347, 348。
- LicenseRef-FIM-One：198, 349, 350, 351, 352。
- LicenseRef-RNA-TPSAL-1.0：353。
- unknown：2, 8, 10, 13, 17, 19, 21, 26, 28, 48, 49, 50, 51, 71, 78, 82, 88, 90, 96, 98, 99, 103, 117, 118, 119, 132, 133, 137, 141, 142, 160, 164, 171, 173, 174, 175, 176, 177, 184, 198, 203, 204, 209, 218, 235, 257, 258, 259, 260, 275, 276, 302, 331, 337, 348, 363, 367, 383, 393, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407。
- other：24, 30, 72, 154, 175, 188, 229, 239, 381。
- creativeml-openrail-m：200。
- openrail++：407。
- Unlicense：161, 170, 210, 260, 261, 277, 332, 408, 409, 410, 411, 412。
- LGPL-3.0：139, 212, 247, 248, 253, 335, 336, 337, 338, 339, 401。
- LGPL-2.1：168, 400。
