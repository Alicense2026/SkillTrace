# GitHub AI Supply‑Chain and License Auditing

Given a list of GitHub repository URLs together with their declared licenses, this tool automatically identifies AI models, datasets and tools **actually used** within each repository.
It distinguishes **in‑code integration** from **remote service invocation**, performs independent license auditing for the repository itself, and exports nine‑column tables plus a repository summary sheet.

This repository retains only runnable source code and final datasets. Legacy scripts, logs and presentation materials have been removed.

| Metric                                    | Value      |
| ----------------------------------------- | ---------- |
| Processed repositories                    | **16,734** |
| Detected AI assets                        | **23,206** |
| Batches                                   | 19         |
| Repositories with completed license audit | 12,806     |
| Skill‑type repositories                   | 8,125      |

## Directory Layout

```
hf-supply-chain-demo/
├── main.py                  ← Entrypoint: process single / multiple repositories
├── llm.py                   ← DeepSeek API wrapper (REST, OpenAI‑compatible)
├── supply.py                ← LLM judgment: whether assets are actively used; classify as model/dataset/tool
├── astscan.py               ← Code retrieval: Python AST, constant propagation, configuration signals
├── registries.py            ← Registry resolver: map models/datasets/tools to official URLs & licenses
├── integration.py           ← Integration‑pattern classification + upstream source‑code modification detection
├── license_audit.py         ← Repository license auditor (root‑level and sub‑directory scope)
├── report.py                ← Export outputs: 9‑column CSV / Markdown / Excel / JSON
├── merge_batch.py           ← Merge `result.csv` files from one processing batch
├── _supervise5.py           ← Batch scheduler: multi‑worker, failure retry, resume‑from‑checkpoint
├── _split_license.py        ← Aggregate `license_audit.csv` across batches
├── github/                  ← GitHub access layer: clone, zip download, license API, rate‑limiting
├── huggingface/             ← Hugging Face access layer: model / dataset metadata
├── requirements.txt
├── .env.example             ← Local configuration template; copy to `.env` and populate values
└── dataset/                 ← ★ Final datasets
    ├── Repository_Summary.xlsx
    ├── Skill_Supply_Chain.xlsx
    └── license_report.json
```

## Datasets

### 1. `dataset/Repository_Summary.xlsx` — Full results (16 734 repositories / 23 206 assets)

8 worksheets:

| Worksheet                         | Rows   | Content                                                                                                               |
| --------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------- |
| **Repository Summary**            | 16 734 | One row per repository; 16 columns total                                                                              |
| Batch Statistics                  | 19     | Per‑batch success, failure and asset counts                                                                           |
| **Asset Details**                 | 23 206 | One row per asset: repository, type, name, URL, license, invocation pattern, modification status, supporting evidence |
| License Distribution              | 25     | Count of occurrences per license family                                                                               |
| Audit Verdict Distribution        | 6      | Not‑provided / Provided / Cannot‑confirm / Input‑non‑SPDX                                                             |
| Sub‑directory License Statistics  | 47     | Aggregation grouped by sub‑directory paths                                                                            |
| **Sub‑directory License Details** | 5 519  | Per‑sub‑directory license entries: repository path, sub‑directory path, license, source file                          |
| Notes                             | 21     | Terminology and scope annotations                                                                                     |

**16 columns in Repository Summary sheet**

| Column                                                | Description                                                                                                    |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Index / Batch                                         | Row index and originating batch ID                                                                             |
| Repository / URL                                      | `owner/name` identifier and full remote URL                                                                    |
| Declared‑Input‑License                                | License stated in user input                                                                                   |
| **Actual‑Audited‑License**                            | License concluded by the auditor; may be `unknown`                                                             |
| Evidence‑File                                         | Source artifact (`LICENSE`, `README.md`, `pyproject.toml`; `(GitHub /license API)` denotes API‑sourced result) |
| Audit‑Verdict                                         | Not‑provided / Provided / Cannot‑confirm / Input‑non‑SPDX                                                      |
| Sub‑dir‑License‑Count / Sub‑dir‑Details               | Sub‑directory‑level license metadata for the repository                                                        |
| Status                                                | Success / Failure (failures include reason: repository unreachable, timeout, etc.)                             |
| AI‑Asset‑Count / Scanned‑File‑Count / Candidate‑Count | Processing statistics                                                                                          |
| Tokens‑Consumed / Elapsed‑Seconds                     | Cost metrics                                                                                                   |

**8 columns in Asset Details sheet**: repository, AI‑model/dataset/tool name, asset type, URL, license, invocation pattern (`in‑code‑integration` / `remote‑service‑call`), upstream‑modified‑flag, invocation‑evidence.

### 2. `dataset/Skill_Supply_Chain.xlsx` — Skill‑repository supply‑chain dataset (8 125 repositories / 8 618 dependency edges)

| Worksheet                    | Rows  | Content                                                                                                                                    |
| ---------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| ① Supply‑Chain‑Edges         | 8 618 | Each dependency edge: dependent repository, upstream name, upstream license, invocation pattern, modification flag, evidence, upstream URL |
| ② Skill‑Repository‑Inventory | 8 125 | Each Skill repository: source channel, repo license, risk level, upstream‑dependency count, set of upstream licenses, GitHub stars         |
| ③ Zero‑Upstream‑Dependencies | 5 567 | Skill repositories where no upstream dependencies were detected                                                                            |
| ④ Nested‑Subdir‑Licenses     | 4 078 | Sub‑directory‑scoped license records                                                                                                       |
| ⑤ Statistical‑Summary        | 53    | Aggregated numeric statistics                                                                                                              |

> License columns are row‑aligned against the main summary sheet; 100 % consistency holds for repositories successfully processed.

### 3. `dataset/license_report.json` — Raw license‑audit outputs (12 806 repositories)

Fields: `repo`, `license`, `evidence{file, method, snippet}`, `nested[]` (sub‑directory licenses), `verdict`.

### 4. `dataset/skill_repos.csv` — Input inventory of Skill repositories (8 125 rows)

Input manifest for reproducing Skill supply‑chain analysis, usable directly with flag `--repos‑file`:

| Column           | Description                                                                    |
| ---------------- | ------------------------------------------------------------------------------ |
| `repo`           | `owner/name` repository identifier                                             |
| `channel`        | Origin channel: SkillsMP (4 909)｜GitHub (3 209)｜MCP Registry (4)｜Unlabeled (3) |
| `license`        | Auditor‑resolved repository license                                            |
| `risk`           | Assigned risk tier                                                             |
| `upstream_count` | Number of detected upstream dependencies                                       |
| `stars`          | GitHub star count                                                              |

### Key Statistics

Total Skill repositories: **8 125** (used as denominator for percentages):

| Category                                                               | Count | Ratio   |
| ---------------------------------------------------------------------- | ----- | ------- |
| License present                                                        | 5 353 | 65.9 %  |
| No‑license (audited confirmation)                                      | 1 196 | 14.7 %  |
| Processing failure (1 536 retrieval failures + 40 pipeline exclusions) | 1 576 | 19.4 %  |
| Total                                                                  | 8 125 | 100.0 % |

- Among failed repositories, 139 still expose license metadata via GitHub API. These are **not** counted as “license‑present” because full file‑level auditing could not complete.
- For the 1 196 “no‑license” entries, manual full‑file review of a 200‑sample subset yields a false‑positive rate of **0.5 %** (1 out of 199; 95 % CI: 0.1–2.8 %).

## How to Run

### 1. Environment Setup

```
cd hf-supply-chain-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # requests / python‑dotenv / pandas / openpyxl
```

Copy `.env.example` to `.env` locally and populate your LLM API key:

```
DEEPSEEK_API_KEY=sk‑xxxxxxxx
```

Requires the `git` command‑line; clone failures automatically fall back to ZIP download.
Optional environment variables: `LLM_BASE_URL`, `LLM_MODEL`, `GITHUB_TOKEN` (raise API rate limits), `HF_TOKEN`.

### 2. Process a Single Repository

```
python main.py --repo https://github.com/zseven-w/openpencil --license MIT
python main.py https://github.com/zseven-w/openpencil MIT   # positional‑argument syntax
python main.py                                             # interactive prompt
```

表格

| Argument                       | Function                                                         |
| ------------------------------ | ---------------------------------------------------------------- |
| `--repo URL --license NAME`    | Repeatable; process multiple repositories                        |
| `--repos-file FILE`            | Batch‑read input file (each line: `URL LICENSE` or `owner/name`) |
| `--out PATH`                   | Output file path; default `result.csv`                           |
| `--workdir DIR`                | Local clone directory; default `repos/`                          |
| `--max-artifacts N`            | Upper bound of assets processed per repository; default 12       |
| `--no‑llm`                     | Skip LLM judgment; static retrieval only                         |
| `--audit‑only`                 | Run license audit without asset discovery                        |
| `--force‑clone` / `--no‑cache` | Force fresh clone / ignore existing cache                        |
| `--quiet`                      | Suppress verbose logging                                         |

### 3. Execute a Full Batch

```
$env:REPO_LIST="_targets_6001_6500.txt"   # input manifest, one `owner/name [license]` per line
$env:OUT_DIR="output_6001_6500"           # output directory
$env:WORKERS="12"                         # parallel‑worker count
$env:LOG_DIR="logs_local"
python _supervise5.py
```

| Environment Variable       | Default                  | Explanation                                             |
| -------------------------- | ------------------------ | ------------------------------------------------------- |
| `REPO_LIST`                | `_targets_6001_6500.txt` | Input repository manifest                               |
| `OUT_DIR`                  | `output_6001_6500`       | Output root directory                                   |
| `WORKERS`                  | 12                       | Concurrent worker processes                             |
| `LOG_DIR`                  | `logs_local`             | Log storage folder                                      |
| `SHARD_TAG`                | `w`                      | Shard label identifier                                  |
| `IDLE_LIMIT` / `MAX_FAILS` | 3600 / 3                 | Idle timeout (seconds) / maximum retries per repository |
| `RETRY_STATE`              | `.retry_state.json`      | Checkpoint file for resume‑on‑restart                   |
| `CLONE_DIR`                | `repos`                  | Local repository clone folder                           |
| `REPO_HARD_TIMEOUT`        | —                        | Per‑repository hard timeout in seconds                  |

Merge partial outputs once batch completes:

```
$env:SRC="output_6001_6500"; $env:OUT="output_6001_6500_final"
python merge_batch.py
```

### 4. Rebuild License Report

```
python _split_license.py
# Aggregate per‑batch license_audit.csv → dataset/license_report.json
```

## Processing Pipeline

```
GitHub URL + declared license
   │
   ├─ 1. Fetch repository        github/clone.py      git clone; fallback ZIP download upon failure
   ├─ 2. Resolve repo‑license    github/license.py     Read LICENSE file → GitHub API → LLM assistance
   ├─ 3. Static asset retrieval  astscan.py           Python AST / constant propagation / configuration signals
   ├─ 4. LLM classification     supply.py            Filter truly‑used assets; tag as model/dataset/tool
   ├─ 5. Registry lookup        registries.py        Resolve official upstream URLs and licenses
   ├─ 6. Integration‑mode detect integration.py       vendored = in‑code integration; else remote invocation
   ├─ 7. Upstream modification  integration.py       upstream comment analysis + file diff + LLM judgment
   └─ 8. Export artifacts        report.py            9‑column CSV / Markdown / Excel / JSON outputs
```

## Reproducibility

What you can and cannot achieve when you obtain this codebase:

| Objective                                                    | Reproducible                 | Procedure                                                                                                                      |
| ------------------------------------------------------------ | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Identify AI assets used inside your own repository           | ✅ Yes                        | `python main.py --repo <your‑repo‑url> --license MIT` to obtain nine‑column results                                            |
| Batch‑process your custom repository inventory               | ✅ Yes                        | Prepare `repos.txt` (one `owner/name` per line); use `--repos‑file` or `_supervise5.py`                                        |
| Run without supplying an LLM key                             | ✅ Yes                        | `--no‑llm` activates pure static retrieval; auto‑fallback to ZIP if git unavailable                                            |
| Re‑run the paper’s Skill supply‑chain analysis (8 125 repos) | ✅ Yes                        | Use `dataset/skill_repos.csv` as input; run `_supervise5.py` then `merge_batch.py`                                             |
| Recover paper license statistics (5 353 / 1 196 / 1 576)     | ✅ Yes                        | Directly read `dataset/Repository_Summary.xlsx`, or recompute statistics after re‑execution                                    |
| One‑click rebuild of `Repository_Summary.xlsx`               | ⚠️ Requires custom scripting | Iterate across `*_final/` folders joining `run_summary.csv` + `result.csv` + `license_audit.csv`. No dedicated script shipped. |

> Note: Column 7 and 8 within `result.csv` (upstream‑modified flag, invocation evidence) rely on LLM judgments.
> When running `--no‑llm` without API keys, static outputs are produced and these two columns will be incomplete or degraded.

## Known Limitations

1. **Only AI‑specific dependencies are extracted**: Generic dependency manifests like `requirements.txt` and `Dockerfile` are **not parsed**. Some upstream call relationships may be missed.
2. Hard cap of **12 assets per repository**: 95 repositories were truncated by this limit.
3. No license conclusion for failed jobs: 1 576 Skill repositories (19.4 %) cannot be audited due to download failure, timeout or pipeline exclusion. These must **not** be interpreted as “no‑license”.
4. Certain license records originate purely from GitHub API without local file inspection (when repository download fails).
5. Snapshot drift: Spot‑checking shows 34 repositories have been deleted (HTTP 404). Re‑running will yield slightly different totals.

## Additional Notes

Folders `repos/` (clone cache) and `logs_local/` are created at runtime and may be safely deleted at any time.
