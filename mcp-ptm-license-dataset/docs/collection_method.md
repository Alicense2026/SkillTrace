# Collection method

## Scope

The dataset targets MCP projects and pretrained models on two public platforms:

- Hugging Face models;
- GitHub repositories.

Collection dates:

- Hugging Face: 20 October 2026
- GitHub: 22 October 2026

## Hugging Face

Topic groups:

- MCP: `mcp`, `mcp-server`, `mcp-client`, `model-context-protocol`
- PTM: `pretrained`, `foundation-model`, `pretraining`, `from-scratch`, `pretrain`

Sort strategies include downloads, last modification, and likes in ascending or descending order.
The crawler follows pagination cursors, deduplicates by `model_id`, filters language-code false
positives, and records the source topic for every retained model.

For each model, the collector preserves:

- API tags and card metadata;
- a README-derived description;
- API license identifiers and links;
- license-file names and evidence;
- a license-body excerpt and paths to archived unusual-license text;
- source topic, sorting strategy, timestamps, and model metadata.

The retained dataset has 6,394 models:

- 6,132 PTM
- 262 MCP

## GitHub

Search topics:

- `mcp`
- `mcp-server`
- `mcp-client`
- `model-context-protocol`
- `pretrained`
- `foundation-model`
- `pretraining`

Each topic is searched in repository names and descriptions under updated and stars orderings.
Results are deduplicated by `full_name`. Forks, archived repositories, and list/awesome-style
aggregators are filtered according to the collector rules.

The license scan combines:

1. GitHub API license metadata;
2. repository filenames containing `license` or `licence`;
3. content-based SPDX matching where a license file is available.

The retained dataset has 16,296 repositories:

- 9,778 MCP
- 6,518 PTM

## Cross-source evidence

`license_cross_check` reports whether license evidence came from:

- API metadata only;
- repository file only;
- both sources;
- neither source.

For GitHub, `license_spdx_agree` additionally records matching, mismatching, absent, unknown, and
not-applicable SPDX evidence. The dataset preserves disagreements for downstream review.

## Known limitations

- Topic search is not a complete platform census.
- Search ranking, API quotas, deletions, and repository changes affect future reruns.
- License filenames are evidence of a declaration, not proof of legal scope.
- Content heuristics can classify custom or combined licenses incorrectly.
- The GitHub evidence archive reflects the collection date shown in `stats.json`.
