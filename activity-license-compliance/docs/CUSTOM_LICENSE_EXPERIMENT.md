# 自定义许可证 ASC 与供应链检测

本流程与标准许可证组合实验分开统计。原始输入是 `aggregate_all_16927/result.csv`，选取任一侧许可证标签包含 `LicenseRef-` 的明细行；不以此前组合统计表替代原始关系，不把所有 `LicenseRef-Custom` 当作同一许可证。

## 文件及职责

- `许可证原文/_licenseref_full/licenseref_full.json`：用户提供的仓库、许可证标签、原文及采集元数据。
- `许可证原文/_licenseref_full/texts/<sha256>.txt`：从映射中逐字节导出的原文；同内容去重。
- `data/custom_license_registry.json`：完整仓库名、标签、原文文件及哈希之间的对应关系。
- `scripts/structure_custom_licenses.py`：调用现有提取提示词，按原文行号分块提取 ASC；保留请求、响应、覆盖说明；将完成的来源加入主语料，并单独输出自定义语料。
- `scripts/normalize_custom_asc.py`：仅对新增自定义条款应用已有的模态与条件规范化规则，保留变更审计和规范化前语料。
- `scripts/verify_custom_asc.py`：核对原文哈希、逐字引文与行号、ASC 合法性及历史条款未改变，生成核验记录和原文索引。
- `data/structured_asc_custom_v1.json`：仅涉及自定义映射来源的 ASC、仓库映射和覆盖说明；其中可包含按哈希复用的已有标准文本。
- `license_checker/llm/custom_licenses.py`：按完整 GitHub URL 和标签精确解析自定义原文，禁止只按短名或泛化 LicenseRef 标签匹配。
- `license_checker/llm/license_sources.py`：统一原文解析入口，现支持自定义映射及递归来源清单。
- `scripts/run_custom_license_experiment.py`：逐明细行构造事实、注入原有提示词和 Figure 10 案例、调用 GPT-6-luna、保存三类输出并生成独立统计。
- `scripts/verify_custom_experiment.py`：完成后按输入逐行核验身份、原始响应、三类输出及12个 Figure 10 案例，重新生成统计报告；执行 `python3 -m scripts.verify_custom_experiment`，不调用 API。
- `tests/test_custom_licenses.py`：验证仓库身份、标签隔离、fork 不推断、空原文和已有原文复用。

## ASC 提取

```sh
python3 scripts/structure_custom_licenses.py
python3 scripts/structure_custom_licenses.py --execute
python3 scripts/normalize_custom_asc.py
python3 scripts/verify_custom_asc.py
```

第一条生成原文与提取请求，不发送 API 请求。第二条发送请求；已有相同请求哈希且已验证的提取结果可直接复用。结构化条款只引用实际提供的原文行，不根据名称补写完整许可证。空原文及没有可抽取条款的来源保留显式状态和覆盖说明。分块失败不等于许可证没有义务。

当前总语料保留历史标准条款，新条款以 `repository_custom` 标识，旧实验输出不覆盖。不要运行历史 `finalize_asc_extension.py` 重建整个语料；该脚本已有新增来源保护。

## 检测与统计

ASC 提取完成后再运行：

```sh
python3 scripts/run_custom_license_experiment.py
python3 scripts/run_custom_license_experiment.py --execute
```

调用配置使用现有 `configs/experiment.toml`，密钥只由客户端读取。每个新请求包含全部12个 Figure 10 案例；格式校验失败保留原始响应，记录后继续。已有检测结果默认保留，避免重复请求。运行期间不要修改输入、注册表或 ASC 语料；哈希变化会拒绝断点续跑。

检测目录为 `runs/custom-license-16927-2026-11-12`：

- `custom_relationship_results.csv`：逐行结果及原 CSV 行号（表头计为第一行）。
- `custom_repository_statistics.csv`：按仓库和自定义标签单独统计。
- `custom_conflict_statistics.csv`：两类冲突的发现条数、去重关系数和仓库数。
- `results/`、`requests/`、`responses/`：完整结果、请求、原始模型响应。
- `three_outputs/{license_license,license_activity,obligations}/`：每条关系的三类输出；跳过和失败使用显式空占位，不能计为无冲突。
- `final_report.md`：方法、统计、案例及覆盖范围。

同一原文可以被多个仓库引用，但自定义许可证的适用对象与主体仍按各行分别保留。未确认仓库映射、空文本、未知资产许可证、无有效 ASC 及失败响应均单列，不从同名仓库或常识推断许可。已有义务没有履行证明时保留条件，不自动判为违规。
