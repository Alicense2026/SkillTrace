# MCP 与 PTM 许可证数据集

本仓库包含 MCP 项目与预训练模型（PTM）许可证元数据研究的采集代码、处理后数据集、统计结果和
许可证证据。数据快照覆盖 Hugging Face 和 GitHub，采集日期分别为 2026 年 10 月 20 日和
2026 年 10 月 22 日。

仓库以可复现为目标。最终表格和原始 API 元数据保留在主目录中；体积较大的 GitHub 许可证原文
证据则集中保存为一个 ZIP 文件。

## 数据组成

| 平台 | 类别 | 去重记录数 | 过滤前原始记录数 |
|---|---|---:|---:|
| Hugging Face | PTM | 6,132 | 19,917 条 Hugging Face 原始记录 |
| Hugging Face | MCP | 262 | 包含在上方统计中 |
| GitHub | PTM | 6,518 | 21,000 条 GitHub 原始记录 |
| GitHub | MCP | 9,778 | 包含在上方统计中 |
| **合计** |  | **22,690** | **40,917** |

类别根据 `search_topic` 字段划分：

- MCP 主题：`mcp`、`mcp-server`、`mcp-client`、`model-context-protocol`。
- PTM 主题：`pretrained`、`pretraining`、`pretrain`、`from-scratch`、`foundation-model`。

## 仓库结构

```text
.
├── README.md
├── requirements.txt
├── Makefile
├── LICENSE-NOTE.md
├── NOTICE.md
├── SECURITY.md
├── SHA256SUMS
├── .github/workflows/validate.yml
├── scripts/
│   ├── collect_hf.py
│   ├── collect_github.py
│   ├── build_manifest.py
│   ├── sanitize_local_paths.py
│   ├── generate_checksums.py
│   └── validate_dataset.py
├── data/
│   ├── summary.json
│   ├── manifest.json
│   ├── hf/
│   │   ├── hf_dataset.csv
│   │   ├── all_models_v1.json
│   │   ├── license_crosscheck.csv
│   │   ├── timestamps.csv
│   │   ├── lang_code_suspects.csv
│   │   ├── stats.json
│   │   ├── raw_api_responses/
│   │   └── license_other_raw/
│   └── github/
│       ├── github_dataset.csv
│       ├── all_repos_v2.json
│       ├── license_crosscheck.csv
│       ├── timestamps.csv
│       ├── stats.json
│       ├── raw_api_responses/
│       └── license_evidence.zip
└── docs/
    ├── collection_method.md
    └── data_dictionary.md
```

## 主要结果文件

`data/hf/hf_dataset.csv`

- 6,394 条去重后的 Hugging Face 模型。
- 包含模型元数据、搜索来源、API 许可证、许可证文件证据、交叉核验状态、README 描述，以及
  特殊许可证原文的存档路径。

`data/github/github_dataset.csv`

- 16,296 条去重后的 GitHub 仓库。
- 包含仓库元数据、API 许可证、仓库文件许可证证据、SPDX 一致性结果和搜索来源。

`data/*/license_crosscheck.csv`

- 专门汇总仅有 API、仅有文件、双来源和无证据等许可证证据状态的表。

`data/*/all_*.json`

- 完整的处理后 JSON 记录，可通过 `--from-json` 重建 CSV。

`data/*/stats.json`

- 采集日期、查询数量、过滤总量、API 使用量、交叉核验分布和部分示例。

`data/github/license_evidence.zip`

- 从 GitHub 收集的 10,613 份仓库许可证文件。
- 压缩包内包含 `license_files_v2/` 和 `license_other_raw/`。
- 使用 `license_file_path` 或 `license_raw_path` 中的路径前，先将压缩包解压到
  `data/github/`。

`data/manifest.json`

- 所有公开数据文件的 SHA-256 和字节大小。

`data/summary.json`

- 记录数、唯一标识数、主题数、类别总量和交叉核验总量。

## 环境配置

建议使用 Python 3.10 或更高版本。

```bash
python -m venv .venv
```

Windows：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

采集脚本优先使用 `curl_cffi`，未安装时回退到 `requests`。

## 验证数据集

```bash
python scripts/validate_dataset.py
```

预期输出：

```text
PASS
HF: 6394 records (MCP 262, PTM 6132)
GitHub: 16296 records (MCP 9778, PTM 6518)
```

验证脚本会检查记录标识、行数、类别总量、文件清单哈希、ZIP 完整性，以及是否存在意外凭据。

公开版本已将原始元数据中的本机绝对路径替换为 `data/hf/` 和 `data/github/` 相对路径。
相关处理脚本位于 `scripts/sanitize_local_paths.py`。

每次正式更新数据后，重新生成仓库级校验和：

```bash
python scripts/generate_checksums.py
```

## 重建摘要和数据清单

有意替换或新增数据集文件后运行：

```bash
python scripts/build_manifest.py
python scripts/validate_dataset.py
```

## 采集 Hugging Face 数据

如需更高请求配额，先设置令牌：

```powershell
$env:HF_TOKEN = "<your-token>"
python scripts/collect_hf.py --dry-run
python scripts/collect_hf.py --group all --max-requests 4000
```

Bash：

```bash
export HF_TOKEN="<your-token>"
python scripts/collect_hf.py --dry-run
python scripts/collect_hf.py --group all --max-requests 4000
```

不设置令牌时，脚本会以匿名模式运行，并自动增加请求间隔。结果写入 `data/hf/`。

常用参数：

- `--group mcp|ptm|all`
- `--total N`
- `--pages N`
- `--max-requests N`
- `--no-detail`、`--no-readme`、`--no-license-body`
- `--resume`
- `--from-json`
- `--shard N/M`

## 采集 GitHub 数据

完整采集需要 `GITHUB_TOKEN`，因为脚本会通过核心 API 扫描仓库许可证文件：

```powershell
$env:GITHUB_TOKEN = "<your-token>"
python scripts/collect_github.py --dry-run
python scripts/collect_github.py
```

Bash：

```bash
export GITHUB_TOKEN="<your-token>"
python scripts/collect_github.py --dry-run
python scripts/collect_github.py
```

结果写入 `data/github/`。不要把令牌写入源码、Notebook、提交到 Git 的配置文件或 Shell 历史。

常用参数：

- `--total N`
- `--pages N`
- `--topics "mcp in:name,description,..."`
- `--license-scan auto|contents|tree|off`
- `--no-license-content`
- `--no-license-text`
- `--from-json`

## 许可证证据流程

两个采集器在适用时都会组合以下两类证据：

1. 平台 API 元数据，例如 Hugging Face tags/card data 和 GitHub 的 `license` 字段。
2. 仓库或模型内容中发现的许可证文件。

数据集保留来源之间的不一致，不会静默消除冲突。`license_cross_check` 区分仅文件、仅 API、
双来源和双缺失；`license_spdx_agree` 区分匹配、不匹配、缺失、未知和不适用。

详细说明见 `docs/collection_method.md` 和 `docs/data_dictionary.md`。

## 安全说明

公开版 `collect_github.py` 只从 `GITHUB_TOKEN` 环境变量读取令牌，不再包含硬编码凭据。
发布分支或重新采集前请阅读 `SECURITY.md`。

原始采集脚本曾包含硬编码令牌。该令牌应被视为已泄露，必须立即在 GitHub 设置中撤销并重新生成。

## 许可证

采集代码和派生数据集尚未选择项目级许可证。公开发布前应补充：

1. 代码所使用的 `LICENSE`；
2. 数据集的授权声明；
3. 与上游平台条款兼容的署名和再分发说明。

收集的仓库和许可证原文仍受各自原始条款约束。署名和再分发条件请参阅 `NOTICE.md` 及上游仓库。
