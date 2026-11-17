# Data dictionary

## Hugging Face: `hf_dataset.csv`

- `model_id`: Hugging Face model identifier.
- `downloads`: download count reported at collection.
- `search_topic`: topic that discovered the model.
- `search_sort`: search ordering that discovered the model.
- `hf_last_modified`, `hf_created_at`, `collected_at`: platform and collection timestamps.
- `tags_count`: number of model tags.
- `pipeline_tag`: Hugging Face pipeline category.
- `description`: normalized README-derived description.
- `license_spdx`: license identifier reported by model metadata.
- `license_name`, `license_link`: card-data license name and URL.
- `found_by_count`: number of search combinations that found the model.
- `hf_url`: public model URL.
- `license_has_api`: whether an API license declaration was present.
- `license_has_file`: whether a license file was found.
- `license_file_names`: discovered license filenames.
- `license_file_path`: archived/relative license-file path.
- `license_file_source`: evidence source for the file verdict.
- `license_cross_check`: API/file evidence combination.
- `license_body_excerpt`: excerpt from license text.
- `license_raw_path`: path for archived `other`, `unknown`, or `unspecified` license text.
- `matched_by`: metadata or content rule that identified the license.
- `likes`, `trending_score`, `library_name`, `gated`: additional model metadata.

## GitHub: `github_dataset.csv`

- `full_name`: GitHub `owner/repository` identifier.
- `stars`: star count at collection.
- `search_topic`: topic query that discovered the repository.
- `search_sort`: search ordering that discovered the repository.
- `github_updated_at`, `github_created_at`, `collected_at`: platform and collection timestamps.
- `description`: repository description.
- `language`: primary repository language.
- `license_spdx`: license identifier reported by the GitHub API.
- `found_by_count`: number of search combinations that found the repository.
- `html_url`: public repository URL.
- `license_has_api`: whether API license metadata was present.
- `license_has_file`: whether a license file was found.
- `license_file_names`: discovered license filenames.
- `license_file_path`: archived/relative license-file path.
- `license_file_source`: source used to scan the repository tree.
- `license_file_spdx`: SPDX value inferred from license-file evidence.
- `license_cross_check`: API/file evidence combination.
- `license_spdx_agree`: agreement between API and file SPDX values.

## Cross-check tables

`license_crosscheck.csv` contains the license-focused subset of each main table. Columns vary by
platform and are documented by the main-table definitions above.

## Statistics

`stats.json` records collection dates, request counts, raw and retained totals, filtering decisions,
cross-check distributions, and selected examples. `summary.json` provides a normalized compact
summary generated from the packaged CSV files.

## Category mapping

`search_topic` is mapped to an artifact category:

- MCP when the base topic is `mcp`, `mcp-server`, `mcp-client`, or `model-context-protocol`;
- PTM otherwise.

The exact topic counts are stored in `summary.json`.
