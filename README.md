# AI Supply‑Chain and License Compliance Research: Code and Datasets

This repository collects three experimental modules and one dataset accompanying the paper. It covers AI asset supply‑chain identification, behavior‑based license compliance inspection, Skill sequential invocation conflicts, as well as license metadata for MCP / Pre‑Trained Models (PTMs).

This is a desensitized research archive. Historical statistics reflect snapshots of each collection batch. Metrics such as repository count, asset count, and dependency count from different batches **cannot be mixed**. Native publisher identity information and private service configurations identified have been removed.

## Table of Contents

| Directory                          | Content                                                                                                                      | Entry Link                                                                                    |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `skill‑sequential‑conflict‑repro/` | 8 fixed‑version Skills, 6 invocation chains, 12 positive/negative control tasks; including results, evidence and log scanner | [Module Documentation](https://www.doubao.com/chat/skill-sequential-conflict-repro/README.md) |
| `hf‑supply‑chain‑demo/`            | Model, dataset and tool dependency identification for GitHub repositories, integration patterns and license auditing         | [Module Documentation](https://www.doubao.com/chat/hf-supply-chain-demo/README.md)            |
| `activity‑license‑compliance/`     | Rule‑based auditing under ⟨Activity, Subject, Constraint⟩, LLM experiments and structured ASC corpus                         | [Module Documentation](https://www.doubao.com/chat/activity-license-compliance/README.md)     |
| `mcp‑ptm‑license‑dataset/`         | Collection scripts, processed datasets and license evidence from Hugging Face / GitHub                                       | [Dataset Documentation](https://www.doubao.com/chat/mcp-ptm-license-dataset/README.md)        |

## Primary Datasets

- **Supply‑chain data**: `hf‑supply‑chain‑demo/dataset/` contains the repository master table, Skill supply‑chain table, audit JSON files and Skill input manifest. This module records 16,734 processed repositories, 23,206 AI assets and 8,125 Skill repositories.
- **Compliance data**: `activity‑license‑compliance/aggregate_all_16927/` holds inputs and summaries for this experimental batch; `Skill‑supply‑chain.xlsx` is the Skill supply‑chain input file; `data/` stores structured ASC corpora and custom license mappings; `license‑texts/` preserves license evidence; `runs/` and `output/` store filtered experimental results, audit records and reports. Numeric identifiers in directory names denote historical batch IDs. Refer to file contents for actual row counts.
- **Sequential‑invocation data**: `skill‑sequential‑conflict‑repro/inputs/` stores fixed Skill versions, tasks and license evidence. `outputs/results.json` stores single‑Agent single‑replay outcomes. The 12/12 result corresponds to this replay run and **does not represent cross‑model statistical conclusions**.
- **MCP / PTM data**: `mcp‑ptm‑license‑dataset/data/` includes 6,394 Hugging Face records and 16,296 GitHub records, totalling 22,690 entries. GitHub license evidence is archived inside `data/github/license_evidence.zip`. Collection snapshot dates are documented in each module’s readme.

## Running Experiments

Modules operate independently. It is recommended to create separate virtual environments for each module to avoid dependency conflicts.

### Supply‑Chain Identification

```
cd hf-supply-chain-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py --repo [https://github.com/zseven-w/openpencil](https://github.com/zseven-w/openpencil) --license MIT --no-llm
```

Network collection requires access to upstream platforms. When enabling LLM features, configure service parameters and secrets in the local `.env` file. `GITHUB_TOKEN` / `HF_TOKEN` are optional for higher rate‑limits. **Never commit the `.env` file**.

### Behavior‑Driven Compliance Experiments

```
cd activity-license-compliance
python3 -m license_checker experiment --input aggregate_all_16927/result.csv --output-dir runs/public-preview --limit 1
```

By default, only request previews are generated. Before running live online experiments, modify `base_url`, `responses_path`, and `model` inside `configs/experiment.toml`. Provide API keys via the `LICENSE_API_KEY` environment variable, and explicitly add the `--execute` flag. The placeholder address `[https://api.example.invalid](https://api.example.invalid)` in the public release is non‑functional. Retained historical model names do not guarantee ongoing service availability. Always use fresh output directories; do not overwrite archived results.

## Reproducibility Boundaries

Offline validation can verify archived data structure and file integrity, but cannot replay all historical network calls. LLM outputs are non‑deterministic. Upstream repositories, model services and license terms may change over time. Re‑execution does not guarantee identical results. Portions of original request‑response payloads have been excluded; full reconstruction of historical network interactions is impossible. A failed compliance check outcome **does not equal a definitive violation or formal compliance status**, conclusions depend on available evidence and rule coverage.
