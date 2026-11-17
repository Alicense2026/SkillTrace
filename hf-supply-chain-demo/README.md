# GitHub AI 供应链与许可证审计

输入一批 GitHub 仓库地址（及其声明的许可证），自动识别仓库**真正在用**的 AI 模型 / 数据集 / 工具，
判断是**代码层面集成**还是**远程服务调用**，并对仓库自身的许可证做一次独立审计，
输出 9 列表格与仓库总表。

本仓库只保留**可运行代码**和**最终数据集**；历史脚本、日志、汇报材料已清理。

| 指标 | 数值 |
|---|---|
| 已处理仓库 | **16,734** |
| 识别出的 AI 资产 | **23,206** |
| 批次 | 19 |
| 完成许可证审计的仓库 | 12,806 |
| Skill 类仓库 | 8,125 |

---

## 目录结构

```
hf-supply-chain-demo/
├── main.py                  ← 入口：处理单个 / 多个仓库
├── llm.py                   ← DeepSeek 调用封装（REST，OpenAI 兼容）
├── supply.py                ← 大模型裁决：资产是否真在用、属于 model/dataset/tool
├── astscan.py               ← 代码召回：Python AST、常量传播、配置信号
├── registries.py            ← 注册中心解析：模型/数据集/工具 → 官方 URL 与许可证
├── integration.py           ← 集成方式判定 + 是否修改上游源码
├── license_audit.py         ← 仓库许可证审计（根目录 + 子目录）
├── report.py                ← 输出 9 列 CSV / Markdown / Excel / JSON
├── merge_batch.py           ← 合并一个批次的 result.csv
├── _supervise5.py           ← 批次调度器（多 worker、失败重试、断点续跑）
├── _split_license.py        ← 汇总各批次 license_audit.csv
├── github/                  ← GitHub 访问层（克隆、zip 下载、许可证 API、限流）
├── huggingface/             ← Hugging Face 访问层（模型 / 数据集元数据）
├── requirements.txt
├── .env.example             ← 本地配置模板；复制为 .env 后填写
└── dataset/                 ← ★ 最终数据集
    ├── 仓库总表.xlsx
    ├── Skill供应链.xlsx
    └── license_report.json
```

---

## 数据集

### 1. `dataset/仓库总表.xlsx` — 全量结果（16,734 个仓库 / 23,206 个资产）

8 个工作表：

| 工作表 | 行数 | 内容 |
|---|---|---|
| **仓库总表** | 16,734 | 每仓库一行，16 列 |
| 批次统计 | 19 | 批次级成功数、失败数、资产数 |
| **资产明细** | 23,206 | 每资产一行：仓库、类型、名称、URL、许可证、调用方式、是否修改、证据 |
| 许可证分布 | 25 | 许可证家族计数 |
| 审计结论分布 | 6 | 未提供 / 已提供 / 无法确认 / 输入非 SPDX |
| 子目录许可证统计 | 47 | 按子目录路径汇总 |
| **子目录许可证明细** | 5,519 | 每个子目录许可证：仓库、子目录、许可证、依据文件 |
| 说明 | 21 | 口径注释 |

**仓库总表 16 列**

| 列 | 含义 |
|---|---|
| 序号 / 批次 | 行号与所属批次 |
| 仓库 / URL | `owner/name` 与完整地址 |
| 表格输入许可证 | 输入时声明的许可证 |
| **实际许可证** | 工具审计后的许可证（可能为 `unknown`） |
| 证据文件 | 依据文件（`LICENSE`、`README.md`、`pyproject.toml`；`(GitHub /license 接口)` 表示来自 API） |
| 审计结论 | 未提供 / 已提供 / 无法确认 / 输入非 SPDX |
| 子目录许可证数 / 子目录明细 | 仓库内子目录级许可证 |
| 状态 | 成功 / 失败（失败附带原因：无法获取仓库、超时等） |
| AI资产数 / 扫描文件数 / 候选数 | 处理统计 |
| tokens / 耗时秒 | 成本统计 |

**资产明细 8 列**：仓库、AI模型/数据集/工具名、类型、URL、许可证、调用方式
（`代码层面集成` / `远程服务调用`）、是否修改、调用证据。

### 2. `dataset/Skill供应链.xlsx` — Skill 仓库供应链（8,125 个仓库 / 8,618 条依赖边）

| 工作表 | 行数 | 内容 |
|---|---|---|
| ① 供应链明细 | 8,618 | 仓库 → 上游依赖的每条边：依赖名、上游许可证、调用方式、是否修改、证据、URL |
| ② 技能仓库清单 | 8,125 | 每个 Skill 仓库：来源渠道、仓库许可证、风险等级、上游依赖数、上游许可证集合、stars |
| ③ 无上游依赖 | 5,567 | 未识别出上游依赖的 Skill 仓库 |
| ④ 嵌套上游许可证 | 4,078 | 子目录级许可证记录 |
| ⑤ 统计摘要 | 53 | 汇总数字 |

> 许可证列已与总表逐行对齐：工具成功处理的仓库 100% 一致。

### 3. `dataset/license_report.json` — 许可证审计原始结果（12,806 个仓库）

字段：`repo`、`license`、`evidence{file, method, snippet}`、`nested[]`（子目录许可证）、`verdict`。

### 4. `dataset/skill_repos.csv` — Skill 仓库输入清单（8,125 行）

复现 Skill 供应链所需的输入清单，可直接喂给 `--repos-file`：

| 列 | 含义 |
|---|---|
| `repo` | `owner/name` |
| `channel` | 来源渠道：SkillsMP 4,909 ｜ GitHub 3,209 ｜ MCP Registry 4 ｜ 未标注 3 |
| `license` | 工具审计后的许可证 |
| `risk` | 风险等级 |
| `upstream_count` | 识别出的上游依赖数 |
| `stars` | GitHub stars |

### 关键统计

Skill 仓库 8,125 个，分母统一为 8,125：

| 分类 | 数量 | 占比 |
|---|---|---|
| 有许可证 | 5,353 | 65.9% |
| 无许可证（已审计确认） | 1,196 | 14.7% |
| 失败（1,536 检索失败 + 40 未进入管线） | 1,576 | 19.4% |
| 合计 | 8,125 | 100.0% |

- 失败仓库中有 139 个仍可从 GitHub API 读到许可证值；因未经文件审计，不计入「有许可证」。
- 1,196 个「无许可证」经 200 个样本的全文件复核，误报率 **0.5%**（1/199，95% CI 0.1–2.8%）。

---

## 如何运行

### 1. 环境准备

```powershell
cd hf-supply-chain-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # requests / python-dotenv / pandas / openpyxl
```

复制 `.env.example` 为 `.env`，在本地填入 LLM 密钥：

```ini
DEEPSEEK_API_KEY=sk-xxxxxxxx
```

需要 `git` 命令行（克隆失败会自动回退到下载 zip）。可选环境变量：
`LLM_BASE_URL`、`LLM_MODEL`、`GITHUB_TOKEN`（提高 API 限额）、`HF_TOKEN`。

### 2. 处理单个仓库

```powershell
python main.py --repo https://github.com/zseven-w/openpencil --license MIT
python main.py https://github.com/zseven-w/openpencil MIT   # 位置参数写法
python main.py                                             # 交互式输入
```

| 参数 | 作用 |
|---|---|
| `--repo URL --license NAME` | 可重复，处理多个仓库 |
| `--repos-file FILE` | 从文件批量读入（每行 `URL 许可证` 或 `owner/name`） |
| `--out PATH` | 输出文件（默认 `result.csv`） |
| `--workdir DIR` | 克隆目录（默认 `repos/`） |
| `--max-artifacts N` | 单仓库最多处理资产数（默认 12） |
| `--no-llm` | 跳过 LLM 裁决，只做静态召回 |
| `--audit-only` | 只做许可证审计，不识别资产 |
| `--force-clone` / `--no-cache` | 强制重新克隆 / 忽略缓存 |
| `--quiet` | 安静模式 |

### 3. 跑一个批次

```powershell
$env:REPO_LIST="_targets_6001_6500.txt"   # 输入清单，每行 owner/name [许可证]
$env:OUT_DIR="output_6001_6500"           # 输出目录
$env:WORKERS="12"                         # 并发数
$env:LOG_DIR="logs_local"
python _supervise5.py
```

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `REPO_LIST` | `_targets_6001_6500.txt` | 输入清单 |
| `OUT_DIR` | `output_6001_6500` | 输出目录 |
| `WORKERS` | 12 | 并发 worker 数 |
| `LOG_DIR` | `logs_local` | 日志目录 |
| `SHARD_TAG` | `w` | 分片标记 |
| `IDLE_LIMIT` / `MAX_FAILS` | 3600 / 3 | 空闲上限（秒）/ 单仓库最多重试 |
| `RETRY_STATE` | `.retry_state.json` | 断点状态（可续跑） |
| `CLONE_DIR` | `repos` | 克隆目录 |
| `REPO_HARD_TIMEOUT` | — | 单仓库硬超时（秒） |

批次跑完后合并：

```powershell
$env:SRC="output_6001_6500"; $env:OUT="output_6001_6500_final"
python merge_batch.py
```

### 4. 重建许可证报告

```powershell
python _split_license.py
# 汇总各批次 license_audit.csv → dataset/license_report.json
```

---

## 处理流程

```
GitHub URL + 许可证
   │
   ├─ 1. 拉取仓库        github/clone.py      git clone → 失败回退下载 zip
   ├─ 2. 仓库许可证      github/license.py    LICENSE 正文 → GitHub API → 大模型
   ├─ 3. 召回            astscan.py           Python AST / 常量传播 / 配置信号
   ├─ 4. 大模型裁决      supply.py            哪些真在用，属于 model/dataset/tool
   ├─ 5. 注册中心解析    registries.py        → 官方 URL 与许可证
   ├─ 6. 集成方式        integration.py       vendored → 代码层面集成，否则远程调用
   ├─ 7. 修改判定        integration.py       上游注释 + 文件清单比对 + 大模型
   └─ 8. 输出            report.py            9 列 CSV / Markdown / Excel / JSON
```

---

## 可复现性

别人拿到这个仓库，能做到什么、做不到什么：

| 目标 | 能否复现 | 做法 |
|---|---|---|
| 自己的仓库在用什么 AI 资产 | ✅ 可以 | `python main.py --repo <你的仓库> --license MIT`，直接得到 9 列结果 |
| 批量处理自己的仓库清单 | ✅ 可以 | 写一个 `repos.txt`（每行 `owner/name`），`--repos-file` 或 `_supervise5.py` |
| 不配 LLM 也能跑 | ✅ 可以 | `--no-llm` 走纯静态召回（git 不可用时自动回退下载 zip） |
| 复现本仓库的 Skill 供应链（8,125 仓库） | ✅ 可以 | 用 `dataset/skill_repos.csv` 作输入，跑 `_supervise5.py` → `merge_batch.py` |
| 复现论文里的许可证数字（5,353 / 1,196 / 1,576） | ✅ 可以 | 直接读 `dataset/仓库总表.xlsx`，或重跑后统计 |
| 一键重建 `仓库总表.xlsx` | ⚠️ 需自己写 | 需遍历各批次 `*_final/`（`run_summary.csv` + `result.csv` + `license_audit.csv`）汇总；本仓库未附带该脚本 |

**注意**：`result.csv` 里的第 7、8 列（是否修改、调用证据）依赖 LLM 判定；
不配 key 时 `--no-llm` 只能给出静态召回结果，这两列会缺失或降级。

---

## 已知限制

1. **只抽取 AI 类型依赖**：不解析 `requirements.txt`、`Dockerfile` 等通用依赖清单，下游对上游的调用关系可能有遗漏。
2. **单仓库资产上限 12 个**：95 个仓库因此被截断。
3. **失败仓库不可判定**：1,576 个 Skill 仓库（19.4%）因下载失败、超时或未进入管线而无法审计，不能视为「无许可证」。
4. **部分许可证来自 GitHub API**：未经文件核验（仓库无法下载时）。
5. **快照漂移**：抽样复核发现 34 个仓库已被删除（404），复现时数量会略有差异。

---

## 附注

- 运行时会自动创建 `repos/`（克隆缓存）与 `logs_local/`，可随时删除。
