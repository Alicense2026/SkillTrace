# Activity License Compliance

基于 `<A 行为, S 对象, C 约束>` 的许可证规则审计与 LLM 实验工具。离线规则检查与模型实验独立运行。Python 3.11+，核心运行和测试只依赖标准库。

## 公开归档入口

- `aggregate_all_16927/result.csv`：本包附带的批量输入。
- `Skill-supply-chain.xlsx`：Skill 供应链输入。
- `data/structured_asc_v1.json`、`data/structured_asc_custom_v1.json`：结构化 ASC 语料。
- `data/custom_license_registry.json`、`许可证原文/`：许可证映射与证据。
- `runs/`：历史实验的结构化结果、汇总及审查记录；部分中间产物已排除。
- `output/`：离线回归报告与审查产物，不代表所有输入都已完成合规核验。
- `license_checker/resources/`：内置案例和规则资源；Figure 10 的结构化案例仍在，带有身份信息的 PDF 摘录未收录。

## 快速验证与预览

在本目录执行：

```bash
python3 -m license_checker cases
python3 -m unittest discover -s tests -v
python3 -m license_checker experiment --input aggregate_all_16927/result.csv --output-dir runs/public-preview --limit 1
python3 -m license_checker audit --input tests/fixtures/chain_216.json --output-dir output/public-audit --no-license-cache
```

预览不联网；离线审计可能因规则覆盖不足返回未完成检查。`tests/fixtures/chain_216.json` 是恢复的 216 条回归输入，不是新采集数据。

## 在线实验配置

编辑 `configs/experiment.toml`，将占位 `base_url` 改为实际服务地址，并确认 `responses_path`、`model` 和服务参数。默认仅从 `LICENSE_API_KEY` 环境变量获取密钥，不附带 `api.rtf`。正式执行增加 `--execute`，并选择全新的输出目录。

```bash
python3 -m license_checker experiment --input aggregate_all_16927/result.csv --output-dir runs/public-live --limit 1 --execute
```

本包不验证历史服务和模型目前是否可用。不要把真实凭据提交到 Git。

## 方法与历史记录

- [文件职责](docs/FILE_GUIDE.md)
- [Prompt 设计](docs/PROMPT_DESIGN.md)
- [Figure 10 ASC](docs/FIGURE10_ASC.md)
- [macOS 运行](docs/MACOS_EXPERIMENT.md)
- [Windows 运行](docs/WINDOWS_EXPERIMENT.md)
- [公开归档说明](../release/README.md)

`docs/` 其余文档为历史方法和验证记录，可能引用已排除的本地文件或旧输入批次。它们不是公开包完整性清单；当前入口以本 README 为准。历史 manifest 中的哈希保留其原始实验含义；脱敏后文件以仓库根目录的 `SHA256SUMS` 为准。

离线入口支持 `--human-input`，示例见 `examples/`。模型输出仅为待核验建议，不会自动成为已审核规则。
