# MCP and PTM License Dataset

This repository contains scraping scripts, post‑processed datasets, statistical outputs and license‑evidence files for research on MCP project and Pre‑Trained Model (PTM) license metadata.
Snapshots cover Hugging Face and GitHub, collected **2026‑10‑20** and **2026‑10‑22** respectively.

Reproducibility is a core design goal. Final tables and raw API metadata reside in top‑level directories. Large‑volume GitHub license‑text evidence is packaged within one ZIP archive.

## Dataset Composition



| Platform     | Category | Deduplicated Records | Pre‑filter Raw Record Count     |
| ------------ | -------- | -------------------- | ------------------------------- |
| Hugging Face | PTM      | 6 132                | 19 917 raw Hugging‑Face records |
| Hugging Face | MCP      | 262                  | Included in statistics above    |
| GitHub       | PTM      | 6 518                | 21 000 raw GitHub records       |
| GitHub       | MCP      | 9 778                | Included in statistics above    |
| **Total**    |          | **22 690**           | **40 917**                      |

Categories are assigned by the `search_topic` field:

- MCP topics: `mcp`, `mcp‑server`, `mcp‑client`, `model‑context‑protocol`.
- PTM topics: `pretrained`, `pretraining`, `pretrain`, `from‑scratch`, `foundation‑model`.

## Repository Layout

```
.
├── README.md
├── requirements.txt
├── Makefile
├── LICENSE‑NOTE.md
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

## Key Output Files

`data/hf/hf_dataset.csv`

- 6 394 deduplicated Hugging‑Face model entries.
- Includes model metadata, search provenance, API‑reported licenses, license‑file evidence, cross‑check status, README excerpts and archive paths for special license texts.

`data/github/github_dataset.csv`

- 16 296 deduplicated GitHub repository entries.
- Contains repository metadata, API‑declared licenses, license‑file evidence from repository contents, SPDX compliance results and search provenance.

`data/*/license_crosscheck.csv`

- Summary table classifying evidence states: API‑only, file‑only, dual‑source evidence, no evidence.

`data/*/all_*.json`

- Full post‑processing JSON records; CSV artifacts can be regenerated using `--from‑json`.

`data/*/stats.json`

- Collection timestamps, query volumes, filter statistics, API consumption metrics, cross‑check distributions and sample entries.

`data/github/license_evidence.zip`

- 10 613 repository license documents scraped from GitHub.
- Inside archive: `license_files_v2/` and `license_other_raw/`.
- Before accessing paths stored under `license_file_path` or `license_raw_path`, extract this ZIP into `data/github/`.

`data/manifest.json`

- SHA‑256 checksums and byte‑size for every public data file.

`data/summary.json`

- Record counts, unique identifiers, topic counts, category totals and cross‑check aggregates.

## Environment Setup

Python 3.10 or newer is recommended.

```
python -m venv .venv
```

Windows:

```
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux / macOS:

```
source .venv/bin/activate
pip install -r requirements.txt
```

Scrapers prefer `curl_cffi`; they fall back to `requests` if it is unavailable.

## Validate Datasets

```
python scripts/validate_dataset.py
```

Expected output:

```
PASS
HF: 6394 records (MCP 262, PTM 6132)
GitHub: 16296 records (MCP 9778, PTM 6518)
```

The validator checks record identifiers, row counts, category totals, file hashes, ZIP archive integrity and accidental credential leakage.
Absolute local filesystem paths present in original metadata are replaced with relative paths pointing to `data/hf/` and `data/github/`; this transformation is implemented in `scripts/sanitize_local_paths.py`.

Regenerate repository‑level checksums after every official dataset update:

```
python scripts/generate_checksums.py
```

## Rebuild Summaries & File Manifests

Run after replacing or adding dataset files:

```
python scripts/build_manifest.py
python scripts/validate_dataset.py
```

## Scrape Hugging‑Face Data

Set your token for higher request quotas:

```
$env:HF_TOKEN = "<your‑token>"
python scripts/collect_hf.py --dry-run
python scripts/collect_hf.py --group all --max-requests 4000
```

Bash:

```
export HF_TOKEN="<your‑token>"
python scripts/collect_hf.py --dry-run
python scripts/collect_hf.py --group all --max-requests 4000
```

Without a token, scripts run anonymously with automatically extended request delays. Outputs are written to `data/hf/`.

Common arguments:

- `--group mcp|ptm|all`
- `--total N`
- `--pages N`
- `--max‑requests N`
- `--no‑detail`, `--no‑readme`, `--no‑license‑body`
- `--resume`
- `--from‑json`
- `--shard N/M`

## Scrape GitHub Data

Full collection requires `GITHUB_TOKEN`, because scripts scan repository license files via core GitHub APIs:

```
$env:GITHUB_TOKEN = "<your‑token>"
python scripts/collect_github.py --dry-run
python scripts/collect_github.py
```

Bash:

```
export GITHUB_TOKEN="<your‑token>"
python scripts/collect_github.py --dry-run
python scripts/collect_github.py
```

Results are saved under `data/github/`. **Never write tokens into source code, notebooks, git‑tracked configs or shell history.**

Common arguments:

- `--total N`
- `--pages N`
- `--topics "mcp in:name,description,..."`
- `--license‑scan auto|contents|tree|off`
- `--no‑license‑content`
- `--no‑license‑text`
- `--from‑json`

## License‑Evidence Workflow

Both scrapers combine two evidence classes when applicable:

1. Platform API metadata (e.g. Hugging Face tags / card metadata, GitHub `license` field).
2. License files found within repository or model contents.

The dataset preserves inconsistencies across sources and does not silently resolve conflicts. `license_cross_check` categorizes evidence status: file‑only, API‑only, dual‑source, no‑evidence. `license_spdx_agree` classifies pairwise outcomes: match, mismatch, missing, unknown, not‑applicable.

Full definitions in `docs/collection_method.md` and `docs/data_dictionary.md`.

## Security Notes

Public release of `collect_github.py` reads tokens **only** from the `GITHUB_TOKEN` environment variable; hard‑coded secrets have been removed.
Read `SECURITY.md` before cutting release branches or rerunning collection jobs.
Hard‑coded tokens present in old scraper versions must be considered compromised; revoke and regenerate them within your GitHub account settings immediately.

## Licensing

No top‑level license has yet been selected for scraping code or derived datasets. Before public release add:

1. A `LICENSE` file applying to source code;
2. Attribution terms governing dataset redistribution;
3. Attribution and redistribution clauses compatible with upstream platform terms.

Scraped repositories and license texts remain bound under their original respective licenses. See `NOTICE.md` and upstream repositories for attribution and redistribution requirements.
