# Activity License Compliance

Toolkit for license‑rule auditing and LLM‑driven experiments based on the ⟨A‑Activity, S‑Subject, C‑Constraint⟩ model. Offline rule checks and model experiments run independently. Requires Python 3.11+; core runtime and tests depend only on the Python standard library.

## Public Archive Assets

- `aggregate_all_16927/result.csv`: Batch‑processing input shipped with this package.
- `Skill‑supply‑chain.xlsx`: Skill supply‑chain input spreadsheet.
- `data/structured_asc_v1.json`, `data/structured_asc_custom_v1.json`: Structured ASC corpora.
- `data/custom_license_registry.json`, `license‑texts/`: License mappings and supporting evidence.
- `runs/`: Structured outputs, summaries and audit records from historical experiments; some intermediate artifacts have been excluded.
- `output/`: Offline regression reports and audit artifacts. Not all inputs have completed compliance validation.
- `license_checker/resources/`: Built‑in test cases and rule resources. Structured cases for Figure 10 are preserved; PDF excerpts containing identity information are omitted.

## Quick Validation & Preview

Run commands inside this directory:

```
python3 -m license_checker cases
python3 -m unittest discover -s tests -v
python3 -m license_checker experiment --input aggregate_all_16927/result.csv --output-dir runs/public-preview --limit 1
python3 -m license_checker audit --input tests/fixtures/chain_216.json --output-dir output/public-audit --no-license-cache
```

Preview operations work offline. Offline audits may return incomplete checks due to limited rule coverage. `tests/fixtures/chain_216.json` contains restored regression inputs (216 entries), not newly‑collected data.

## Online‑Experiment Configuration

Edit `configs/experiment.toml`: replace the placeholder `base_url` with your actual service endpoint, and verify `responses_path`, `model`, and service parameters. Secrets are read exclusively from the `LICENSE_API_KEY` environment variable; no `api.rtf` file is included.
Add the `--execute` flag for real execution and select a brand‑new output directory.

```
python3 -m license_checker experiment --input aggregate_all_16927/result.csv --output-dir runs/public-live --limit 1 --execute
```

This package does not guarantee that historical services or model versions remain functional. **Never commit real credentials to Git.**

## Methodology & Historical Documentation

- [File Responsibilities](docs/FILE_GUIDE.md)
- [Prompt Design](docs/PROMPT_DESIGN.md)
- [Figure 10 ASC](docs/FIGURE10_ASC.md)
- [Running on macOS](docs/MACOS_EXPERIMENT.md)
- [Running on Windows](docs/WINDOWS_EXPERIMENT.md)
- [Public Archive Notes](../release/README.md)

Remaining documents under `docs/` record historical methodology and validation. They may reference removed local files or old input batches and do **not** serve as an integrity manifest for the public release. This README defines the official entry points.
Hashes in historical manifest files retain their original experimental meaning; for desensitized files, refer to `SHA256SUMS` at repository root.

The offline workflow supports `--human‑input`; usage examples are located under `examples/`. Model outputs constitute review‑only suggestions and are **not** automatically adopted as audited rules.
