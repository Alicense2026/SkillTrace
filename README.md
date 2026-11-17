# AI 供应链与许可证合规研究：代码与数据

本仓库汇集论文配套的三个实验模块与一个数据集，覆盖 AI 资产供应链识别、基于行为的许可证合规检查、Skill 顺序调用冲突，以及 MCP / 预训练模型（PTM）的许可证元数据。

这是经过脱敏的研究归档。历史统计反映各模块的采集快照，不能将不同批次、仓库数、资产数和依赖关系数混用。已清理识别到的发布者本机身份信息与私有服务配置。

## 内容导航

| 目录                                 | 内容                                                         | 入口                                                |
| ---------------------------------- | ---------------------------------------------------------- | ------------------------------------------------- |
| `skill-sequential-conflict-repro/` | 8 个固定版本 Skill、6 条调用链、12 个正负对照任务；含结果、证据与日志扫描器               | [模块说明](skill-sequential-conflict-repro/README.md) |
| `hf-supply-chain-demo/`            | GitHub 仓库的模型、数据集和工具依赖识别，集成方式与许可证审计                         | [模块说明](hf-supply-chain-demo/README.md)            |
| `activity-license-compliance/`     | 基于 ⟨Activity, Subject, Constraint⟩ 的规则审计、LLM 实验与结构化 ASC 语料 | [模块说明](activity-license-compliance/README.md)     |
| `mcp-ptm-license-dataset/`         | Hugging Face / GitHub 的采集代码、处理后数据与许可证证据                    | [数据集说明](mcp-ptm-license-dataset/README.md)        |

## 主要数据

- **供应链数据**：`hf-supply-chain-demo/dataset/` 包含仓库总表、Skill 供应链表、审计 JSON 和 Skill 输入清单。该模块记录 16,734 个已处理仓库、23,206 个 AI 资产及 8,125 个 Skill 仓库。
- **合规数据**：`activity-license-compliance/aggregate_all_16927/` 为该实验批次的输入及汇总；`Skill-supply-chain.xlsx` 为 Skill 供应链输入；`data/` 保存结构化 ASC 与自定义许可证映射；`许可证原文/` 保存许可证证据；`runs/` 与 `output/` 保存筛选后的实验结果、审查记录和报告。目录中的数字是历史批次标识，行数以文件内容为准。
- **顺序调用数据**：`skill-sequential-conflict-repro/inputs/` 保存 Skill 固定版本、任务和许可证证据，`outputs/results.json` 保存单 Agent、单次回放结果。12/12 是该次回放结果，不代表跨模型统计结论。
- **MCP / PTM 数据**：`mcp-ptm-license-dataset/data/` 包含 6,394 条 Hugging Face 记录及 16,296 条 GitHub 记录，共 22,690 条。GitHub 许可证证据存于 `data/github/license_evidence.zip`。采集快照日期见模块说明。

# 

## 运行实验

各模块独立运行，建议分别创建虚拟环境，避免依赖混用。

### 供应链识别

```bash
cd hf-supply-chain-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py --repo https://github.com/zseven-w/openpencil --license MIT --no-llm
```

网络采集仍需要访问上游平台。启用 LLM 时在本地 `.env` 设置服务参数与密钥；可选 `GITHUB_TOKEN` / `HF_TOKEN` 提高访问配额。不要提交 `.env`。

### 行为合规实验

```bash
cd activity-license-compliance
python3 -m license_checker experiment --input aggregate_all_16927/result.csv --output-dir runs/public-preview --limit 1
```

默认仅生成请求预览。执行在线实验前，修改 `configs/experiment.toml` 中的 `base_url`、`responses_path`、`model`，通过 `LICENSE_API_KEY` 环境变量提供密钥，并显式增加 `--execute`。公开版的 `https://api.example.invalid` 是不可用的占位地址；保留的历史模型名称不是对当前服务可用性的保证。使用新输出目录，不要覆盖归档结果。

## 复现边界

离线校验能够验证已归档的数据结构和文件完整性，不会重演全部历史网络调用。LLM 输出具有随机性，上游仓库、模型服务和许可证可能变化；重新运行不保证得到相同结果。部分原始请求/响应被排除，无法据此重建所有历史传输细节。合规判断依赖证据与规则覆盖，未完成检查不等于违规或合规。
