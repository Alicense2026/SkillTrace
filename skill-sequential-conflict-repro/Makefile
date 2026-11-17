.PHONY: verify fetch report log test skilltrace checksums

verify:
	python scripts/verify_repro.py

fetch:
	python scripts/fetch_repos.py
	python scripts/verify_repro.py

report:
	python scripts/build_report.py

log:
	python scripts/export_task_log.py

test:
	python -m unittest discover -s tests -v

skilltrace:
	python scripts/skilltrace_logscan.py examples/skilltrace/sample_codex_c1.jsonl

checksums:
	python scripts/generate_checksums.py
